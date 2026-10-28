"""
Базовый диалог редактирования.

Содержит класс BaseEditDialog — общий каркас для всех форм
редактирования проекта: заголовок, кнопка закрытия, контент,
опциональные кнопки ОК/Отмена. Наследники добавляют содержимое
через _build_content и возвращают результат через _collect_result.

Роль в программе:
    Заменяет дублирование настройки окон в восьми диалогах:
    BrandEditDialog, CompanyDialog, BrandChecklistDialog,
    StringListDialog, PricesEditWindow, BrandMappingsWindow,
    BrandDetailWindow, AveragePriceInputDialog.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from ui.base.dialog_setup_mixin import DialogSetupMixin


class BaseEditDialog(QDialog, DialogSetupMixin):
    """Базовый диалог редактирования.

    Назначение:
        Каркас формы: заголовок, закрытие, контент, ОК/Отмена.
        Наследники переопределяют:
            _build_content(layout) — добавляют виджеты.
            _collect_result() — возвращают данные (опционально).
            _validate() -> bool — проверка перед accept (опционально).

    Роль в программе:
        Единый источник каркаса. Диалоги типа 2 больше не дёргают
        ExtendedWindowFactory напрямую — только наследуются.

    Порядок MRO: BaseEditDialog → QDialog → ... → DialogSetupMixin.
    Метод setup_dialog_frame доступен наследникам через миксин.
    """

    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None

    def __init__(self, parent=None, title="", bg_color=(64, 48, 66, 0.8),
                 width=400, height=350, close_button=True, ok_cancel=True,
                 draggable=False, close_on_click_outside=False,
                 modal=True, center=True, on_close=None,
                 log_manager_v2=None,
                 service_window_override=None,
                 force_window=False):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок диалога.
            bg_color — цвет фона.
            width, height — размеры по умолчанию.
            close_button — показывать ли крестик.
            ok_cancel — показывать ли кнопки ОК/Отмена.
            draggable — перетаскивание за тело.
            close_on_click_outside — закрывать при клике вне.
            modal — модальность.
            center — центрировать.
            on_close — callback при закрытии.
            log_manager_v2 — LogManagerV2 или None.
            service_window_override — явное сервисное окно для
                центрирования. Если None — наследуется у parent
                через фабрику.
            force_window — если True, окно становится независимым
                на уровне ОС (Qt.Window), но сохраняет модальность.
                Используется, если окно обрезается родителем.

        Роль: сохраняет self.bg_color для наследников, создаёт
              логгер, вызывает setup_dialog_frame и передаёт
              content_layout в _build_content.
        """
        super().__init__(parent)
        self._result = None
        self._locked_pos = None

        # Делаем окно независимым на уровне ОС, если нужно.
        # Это предотвращает обрезку окна родителем (например, резолвером).
        if force_window:
            self.setWindowFlag(Qt.Window, True)

        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None and self.LOGGER_SOURCE is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )
        self.bg_color = bg_color
        content_layout = self.setup_dialog_frame(
            parent=parent,
            title=title,
            bg_color=bg_color,
            width=width,
            height=height,
            close_button=close_button,
            ok_cancel=ok_cancel,
            draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal,
            center=center,
            on_close=on_close,
            service_window_override=service_window_override,
        )

        self._build_content(content_layout)

    # ---------- Публичный API ----------

    def get_result(self):
        """Возвращает результат, собранный в _collect_result.

        Выход: то, что вернул _collect_result (или None).
        Роль: вызывающий код после exec() может получить данные
              через get_result(), не завязываясь на конкретные поля.
        """
        return self._result

    # ---------- Переопределяемые методы ----------

    def accept(self) -> None:
        """Обработка кнопки ОК.

        Роль: перед закрытием вызывает _validate. Если проверка
              не прошла — диалог остаётся открытым. Иначе —
              _collect_result и super().accept().

        Если ok_cancel=False — эта кнопка не создаётся в каркасе,
        но accept() может быть вызван программно из своей
        кнопки «Сохранить» в _build_content.
        """
        if not self._validate():
            return
        self._result = self._collect_result()
        super().accept()

    def _build_content(self, layout) -> None:
        """Добавляет виджеты в content_layout.

        Вход: layout — QVBoxLayout, созданный setup_dialog_frame.
        Роль: абстрактный. Наследник обязан переопределить.
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _build_content"
        )

    def _collect_result(self):
        """Собирает результат диалога.

        Выход: любые данные (или None).
        Роль: по умолчанию возвращает None. Наследники, которым нужен
              результат (например, AveragePriceInputDialog), переопределяют.
        """
        return None

    def _validate(self) -> bool:
        """Проверка перед accept.

        Выход: True — можно закрывать; False — остаться.
        Роль: по умолчанию True. Наследники с валидацией
              (AveragePriceInputDialog, PlannerDayPickerDialog)
              переопределяют.
        """
        return True

    # ---------- Взаимодействие с окном ----------

    def showEvent(self, event):
        """Запоминает изначальную позицию при показе окна."""
        super().showEvent(event)
        if self._locked_pos is None:
            self._locked_pos = self.pos()

    def moveEvent(self, event):
        """Блокирует системное смещение окна (например, при клике на QComboBox).

        Если пользователь тащит окно мышкой — разрешаем движение.
        Если кнопка мыши не зажата (системный сдвиг) — возвращаем на место.
        При перетаскивании ограничиваем позицию рамками service_window.
        """
        if self._locked_pos is not None and self.pos() != self._locked_pos:
            if QApplication.mouseButtons() == Qt.NoButton:
                # Системный сдвиг (глюк при открытии списка) — откатываем
                self.move(self._locked_pos)
                return
            else:
                # Пользователь двигает окно сам — запоминаем новую позицию
                self._locked_pos = self.pos()
                self._clamp_to_bound_window()
        super().moveEvent(event)

    def _clamp_to_bound_window(self) -> None:
        """Не позволяет окну выйти за пределы сервисного окна.

        Роль: если задан service_window (или parent), ограничивает
              перемещение окна его геометрией. Это нужно для окон,
              которые выходят за рамки родителя (Qt.Window),
              но должны оставаться в пределах главного окна.
        """
        bound_window = getattr(self, 'service_window', None)
        if not bound_window:
            bound_window = self.parent()
        if not bound_window:
            return

        # Поправка для безрамочных окон Qt (системное смещение координат)
        OFFSET = -10

        # Получаем глобальные координаты рамок
        geo = bound_window.frameGeometry()
        rect = self.frameGeometry()

        # Если окно вдруг больше границ — не двигаем (чтобы не было дерганий)
        if rect.width() > geo.width() or rect.height() > geo.height():
            return

        # Вычисляем границы с учетом смещения
        min_x = geo.left() - OFFSET
        max_x = geo.right() - rect.width() - OFFSET
        min_y = geo.top() - OFFSET
        max_y = geo.bottom() - rect.height() - OFFSET

        # Ограничиваем позицию (сравниваем реальные координаты rect)
        new_x = max(min_x, min(rect.left(), max_x))
        new_y = max(min_y, min(rect.top(), max_y))

        if new_x != rect.left() or new_y != rect.top():
            self.move(new_x + OFFSET, new_y + OFFSET)
            self._locked_pos = self.pos()