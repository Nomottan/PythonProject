"""
Окна работы с подписантами (сотрудниками).

Содержит два класса:
    StaffWindow    — список сотрудников: ФИО, должность, удаление,
                     добавление.
    StaffAddDialog — диалог создания сотрудника: ФИО, должность,
                     валидация, кнопка «Готово».

Роль в программе:
    Открываются из MainWindow через выпадающий список «Справочники».
    Работают через parent.sellers_brands_service
    (get_signers_objects / set_signers_objects), конфиг — config.json.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QDialog
from PySide6.QtCore import Qt

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
    ListWidgetFactory, InputWidgetFactory,
)
from ui.styles import ColorCalculator, WindowStyle
from ui.windows.message_dialog import MessageDialog
from models.models import Signer
from utils.text_utils import TextUtils
from utils.validations import Validations

class StaffWindow(BaseEditDialog):
    """Окно со списком сотрудников.

    Назначение:
        Показать список подписантов. Строка: [×] [ФИО] [должность].
        Снизу — круглая кнопка «+», открывает StaffAddDialog.

    Роль в программе:
        Открывается из MainWindow. Изменения (добавление, удаление)
        пишутся в config.json сразу после подтверждения действия —
        при закрытии окна ничего не сохраняется.
    """

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow (от него берём сервис и фон).
            log_manager_v2 — LogManagerV2 или None. Не используется:
                             логирование для этого окна отключено.
        """
        self.main_window = parent
        self.log_manager_v2 = log_manager_v2

        self.signers = []
        if parent is not None and hasattr(parent, "sellers_brands_service"):
            self.signers = parent.sellers_brands_service.get_signers_objects()

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 20,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b + 20,
            alpha=0.95,
        )

        super().__init__(
            parent=parent, title="Сотрудники",
            bg_color=self.bg_color,
            width=330, height=200,
            close_button=True, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=False, center=True,
            on_close=None,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    # ---------- Построение ----------

    def _build_content(self, layout) -> None:
        """Строит список сотрудников и кнопку добавления.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: scroll-контейнер со строками + центрированная «+».
        """
        scroll, self.rows_widget, self.rows_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll)

        self.add_btn = ButtonFactory.create_add_button(
            self, self._on_add_clicked,
        )
        LayoutFactory.add_centered_widget(layout, self.add_btn)

        for signer in self.signers:
            self._add_row(signer)

    def _add_row(self, signer: Signer) -> None:
        """Добавляет строку сотрудника в список.

        Вход: signer — Signer.
        Роль: [×] [ФИО растяжение 2] [должность растяжение 1].
              Ссылка на signer сохраняется в атрибуте строки —
              по ней строка находится при удалении.
        """
        label_bg = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - 15,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b - 15,
            alpha=0.9,
        )

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda checked=False, s=signer: self._on_delete(s),
            size=(24, 24),
        )
        name_lbl = LabelFactory.create_label(
            self, signer.name,
            bg_color=label_bg, border_radius=5,
            fixed_height=24,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        role_lbl = LabelFactory.create_label(
            self, signer.role,
            bg_color=label_bg, border_radius=5,
            fixed_height=24,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )

        row = QWidget(self.rows_widget)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)
        row_layout.addWidget(del_btn)
        row_layout.addWidget(name_lbl, 2)
        row_layout.addWidget(role_lbl, 1)

        row._signer = signer
        self.rows_layout.addWidget(row)

    # ---------- Действия ----------

    def _on_add_clicked(self) -> None:
        """Открывает диалог создания сотрудника.

        Роль: на accepted забирает Signer через get_result()
              и передаёт в _on_signer_added.
        """
        dialog = StaffAddDialog(self, log_manager_v2=self.log_manager_v2)
        dialog.accepted.connect(
            lambda d=dialog: self._on_signer_added(d.get_result())
        )
        dialog.show()

    def _on_signer_added(self, signer) -> None:
        """Добавляет созданного сотрудника в список и сохраняет.

        Вход: signer — Signer или None.
        """
        if signer is None:
            return
        self.signers.append(signer)
        self._add_row(signer)
        self._persist()

    def _on_delete(self, signer: Signer) -> None:
        """Удаляет сотрудника после подтверждения.

        Вход: signer — Signer.
        Роль: MessageDialog с «Да»/«Нет». «Да» → удаление из
              списка, удаление строки, запись в конфиг.
              «Нет» → выход без изменений.
        """
        result = MessageDialog.question(
            self,
            "Вы действительно хотите удалить сотрудника?",
            bg_color=self.bg_color,
        )
        if result != QDialog.Accepted:
            return

        if signer in self.signers:
            self.signers.remove(signer)
        self._remove_row_by_signer(signer)
        self._persist()

    def _remove_row_by_signer(self, signer: Signer) -> None:
        """Удаляет строку, привязанную к сотруднику.

        Вход: signer — Signer.
        Роль: перебирает строки layout-а, находит ту, у которой
              _signer — тот же объект, и удаляет её.
        """
        for i in range(self.rows_layout.count()):
            item = self.rows_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            if getattr(widget, "_signer", None) is signer:
                self.rows_layout.removeWidget(widget)
                widget.deleteLater()
                return

    def _persist(self) -> None:
        """Записывает список сотрудников в config.json.

        Роль: через sellers_brands_service. Если родитель не даёт
              сервис — молча выходит (защита от кривого вызова).
        """
        if self.main_window is None:
            return
        service = getattr(self.main_window, "sellers_brands_service", None)
        if service is None:
            return
        service.set_signers_objects(self.signers)

class StaffAddDialog(BaseEditDialog):
    """Диалог создания сотрудника.

    Назначение:
        Два поля: ФИО и должность (по умолчанию «Сотрудник»).
        Внизу — «Готово», изначально неактивная.

    Роль в программе:
        Открывается из StaffWindow. Валидация — по editingFinished
        (Enter или уход фокуса). Латинский ввод автоматически
        переводится в кириллицу через TextUtils.to_cyrillic.
        Перед accept() ФИО санитайзится (TextUtils.sanitize_fio).

    Контракт базы:
        _validate() -> bool — проверка перед accept. Возвращает
            False — диалог остаётся открытым.
        _collect_result() — сборка Signer, кладётся в _result.
        accept() из базы сам вызовет оба и закроет окно.
    """

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — StaffWindow.
            log_manager_v2 — LogManagerV2 или None. Не используется.
        """
        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r - 10,
            g_fn=lambda g: g + 20,
            b_fn=lambda b: b + 20,
            alpha=0.95,
        )

        super().__init__(
            parent=parent, title="Сотрудник",
            bg_color=self.bg_color,
            width=300, height=200,
            close_button=True, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=False, center=True,
            on_close=None,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    # ---------- Построение ----------

    def _build_content(self, layout) -> None:
        """Строит форму ФИО/Должность и кнопку «Готово».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        text_color = ColorCalculator.text_for(self.bg_color)

        self.name_edit = InputWidgetFactory.create_default_line_edit(self)
        self.role_edit = InputWidgetFactory.create_default_line_edit(
            self, text=Signer.DEFAULT_ROLE,
        )

        form = LayoutFactory.create_form(
            self,
            rows=[
                (
                    LabelFactory.create_label(
                        self, "ФИО:",
                        bg_color=(0, 0, 0, 0), text_color=text_color,
                        alignment=Qt.AlignLeft | Qt.AlignVCenter,
                    ),
                    self.name_edit,
                ),
                (
                    LabelFactory.create_label(
                        self, "Должность:",
                        bg_color=(0, 0, 0, 0), text_color=text_color,
                        alignment=Qt.AlignLeft | Qt.AlignVCenter,
                    ),
                    self.role_edit,
                ),
            ],
            alignment=Qt.AlignLeft,
            spacing=10,
        )
        layout.addWidget(form)

        self.ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(120, 30),
        )
        self.ok_btn.setEnabled(False)
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.clicked.connect(self._on_done)
        LayoutFactory.add_centered_widget(layout, self.ok_btn)

        # В шапке уже создана кнопка «×». Если она останется
        # auto-default, Enter будет её нажимать и окно закроется
        # само. Снимаем флаг со всех кнопок, кроме «Готово».

        self.name_edit.editingFinished.connect(self._on_editing_finished)
        self.name_edit.textChanged.connect(self._update_ok_state)

    # ---------- Ввод ----------

    def _normalize_input(self) -> str:
        """Возвращает текст ФИО, при необходимости переведённый в кириллицу.

        Выход: str — актуальный текст поля после транслитерации.
        """
        text = self.name_edit.text()
        if TextUtils.is_latinic(text):
            text = TextUtils.to_cyrillic(text)
            self.name_edit.setText(text)
        return text

    def _update_ok_state(self, *_args) -> None:
        """Обновляет доступность «Готово» по текущему тексту.

        Вход: *_args — аргументы сигнала textChanged (не нужны).
        Роль: кнопка активна сразу, как только ФИО валидно.
              Красную рамку не трогаем — она только по
              editingFinished или по accept().
        """
        text = self.name_edit.text()
        if TextUtils.is_latinic(text):
            text = TextUtils.to_cyrillic(text)
        self.ok_btn.setEnabled(Validations.is_valid_fio(text))

    # ---------- Валидация ----------

    def _on_editing_finished(self) -> None:
        """Слот editingFinished: Enter или уход фокуса.

        Роль: прогоняет проверку и обновляет вид. Возврат
              игнорируется — это не контракт accept.
        """
        self._validate()

    def _validate(self) -> bool:
        """Проверка перед accept (контракт BaseEditDialog).

        Выход: True — можно закрывать; False — диалог остаётся.

        Роль: нормализует ввод, обновляет рамку и доступность
              «Готово». Вызывается и слотом editingFinished,
              и базовым accept().
        """
        text = self._normalize_input()
        valid = Validations.is_valid_fio(text)
        InputWidgetFactory.set_error_state(self.name_edit, not valid)
        self.ok_btn.setEnabled(valid)
        return valid

    def _on_done(self) -> None:
        """Обработчик «Готово».

        Роль: делегирует в accept(). База сама вызовет
              _validate, _collect_result и super().accept().
        """
        self.accept()

    def _collect_result(self):
        """Собирает Signer (контракт BaseEditDialog).

        Выход: Signer — с санитайзингом ФИО и дефолтной должностью.
        """
        name = TextUtils.sanitize_fio(self.name_edit.text())
        role = self.role_edit.text().strip() or Signer.DEFAULT_ROLE
        return Signer(name=name, role=role)

    # ---------- Enter ----------

    def keyPressEvent(self, event) -> None:
        """Enter — только валидация, без закрытия окна.

        Роль: перехватывает Enter, если он дошёл до диалога,
              и не даёт активировать кнопку по умолчанию.
        """
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._validate()
            event.accept()
            return
        super().keyPressEvent(event)