"""
Диалоги чек-листа: редактирование одного пункта и всего списка задачи.

ChecklistItemDialog — форма пункта (short, detail) + кнопки.
ChecklistDialog — модальный диалог со списком всех пунктов задачи.

Роль в программе:
    ChecklistItemDialog открывается из ChecklistWidget при + / ✏.
    ChecklistDialog — из PlannerWindow при клике на плашку «Чек-лист».
"""

from PySide6.QtWidgets import QHBoxLayout

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import ButtonFactory, InputWidgetFactory
from ui.windows.message_dialog import MessageDialog


class ChecklistItemDialog(BaseEditDialog):
    """Диалог создания/редактирования одного пункта чек-листа.

    Наследует BaseEditDialog. ok_cancel=False — кнопки свои,
    поведение отличается для создания и редактирования.
    """

    LOGGER_SOURCE = "ChecklistItemDialog.planner_checklist_dialogs"
    LOGGER_DOMAIN = "planner"

    def __init__(self, parent, item=None, bg_color=None):
        """Конструктор.

        Вход:
            parent — родитель.
            item — ChecklistItem при редактировании, None при создании.
            bg_color — фон; при None — fallback.
        """
        self._item = item
        self._is_edit = item is not None
        self._result_data = None
        from ui.styles import WindowStyle, ColorCalculator
        parent_bg = WindowStyle.resolve_parent_bg(
            parent, (60, 50, 40, 0.95),
        )
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 15,
            g_fn=lambda g: g + 10,
            b_fn=lambda b: b + 5,
            alpha=0.95,
        )
        super().__init__(
            parent=parent,
            title=("Редактирование пункта" if self._is_edit
                   else "Новый пункт"),

            bg_color=self.bg_color,
            width=400, height=250,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            log_manager_v2=None,
        )

        from PySide6.QtCore import Qt as _Qt
        self.setWindowFlag(_Qt.Window, True)
        self.setWindowModality(_Qt.NonModal)
        self.setWindowFlag(_Qt.WindowStaysOnTopHint, True)

    def _build_content(self, layout) -> None:
        """Поля short/detail + кнопки."""
        self._short_edit = InputWidgetFactory.create_default_line_edit(
            self,
            text=self._item.short if self._is_edit else "",
            placeholder="Название пункта",
        )
        layout.addWidget(self._short_edit)

        self._detail_edit = InputWidgetFactory.create_text_edit(
            self,
            text=self._item.detail if self._is_edit else "",
            placeholder="Подробное описание (необязательно)",
            bg_color=self.bg_color,
        )
        self._detail_edit.setMinimumHeight(80)
        layout.addWidget(self._detail_edit)

        btns = QHBoxLayout()
        btns.addStretch()

        if self._is_edit:
            save_btn = ButtonFactory.create_button(
                self, "Сохранить",
                bg_color=(70, 120, 90, 0.85),
                padding="6px 14px",
            )
            save_btn.clicked.connect(self.accept)
            btns.addWidget(save_btn)

            cancel_btn = ButtonFactory.create_button(
                self, "Отмена",
                bg_color=(120, 90, 70, 0.85),
                padding="6px 14px",
            )
            cancel_btn.clicked.connect(self.reject)
            btns.addWidget(cancel_btn)

            del_btn = ButtonFactory.create_button(
                self, "Удалить",
                bg_color=(180, 60, 60, 0.85),
                padding="6px 14px",
            )
            del_btn.clicked.connect(self._on_delete)
            btns.addWidget(del_btn)
        else:
            ok_btn = ButtonFactory.create_button(
                self, "Ок",
                bg_color=(70, 120, 90, 0.85),
                padding="6px 14px",
            )
            ok_btn.clicked.connect(self.accept)
            btns.addWidget(ok_btn)

            cancel_btn = ButtonFactory.create_button(
                self, "Отмена",
                bg_color=(120, 90, 70, 0.85),
                padding="6px 14px",
            )
            cancel_btn.clicked.connect(self.reject)
            btns.addWidget(cancel_btn)

        btns.addStretch()
        layout.addLayout(btns)

    def _on_delete(self) -> None:
        """Помечает результат «deleted» и закрывает с accept()."""
        self._result_data = "deleted"
        self.accept()

    def _validate(self) -> bool:
        """Пустое название не пропускаем. «Нет» → reject()."""
        short_text = self._short_edit.text().strip()
        if not short_text:
            if self._is_edit:
                text = (
                    "Название пункта чек-листа не может быть пустым.\n"
                    "Хотите продолжить редактирование?"
                )
            else:
                text = (
                    "Название пункта чек-листа не может быть пустым.\n"
                    "Хотите продолжить создание пункта чек-листа?"
                )
            result = MessageDialog.warning(
                self, text, bg_color=self.bg_color,
            )
            if result == "no":
                self.reject()
            return False
        return True

    def _collect_result(self):
        """dict {short, detail} или строка 'deleted'."""
        if self._result_data == "deleted":
            return "deleted"
        return {
            "short": self._short_edit.text().strip(),
            "detail": self._detail_edit.toPlainText().strip(),
        }

    def showEvent(self, event):
        """Центрирует диалог относительно родителя и поднимает поверх.

        Роль: делегирует в WindowStyle.center_in_app_window.
              Затем raise_() и activateWindow() — родитель
              (MainCommentary) с Qt.WindowStaysOnTopHint; без
              явного поднятия дочерний диалог рисуется за ним,
              пользователь его не видит.
        """

        super().showEvent(event)
        if getattr(self, "_placed_once", False):
            return
        self._placed_once = True
        from ui.styles import WindowStyle
        WindowStyle.center_in_app_window(self, anchor=self.parent())
        self.raise_()
        self.activateWindow()


class ChecklistDialog(BaseEditDialog):
    """Модальный диалог чек-листа задачи — правка целиком.

    Наследует BaseEditDialog с ok_cancel=True. Внутри —
    ChecklistWidget(mode="edit"). _collect_result возвращает
    список пунктов; при reject() _result остаётся None.
    """

    LOGGER_SOURCE = "ChecklistDialog.planner_checklist_dialogs"
    LOGGER_DOMAIN = "planner"

    def __init__(self, parent, task, bg_color=None, log_manager_v2=None, mode="edit"):
        """Конструктор.

        Вход:
            parent — родитель.
            task — PlannerTask, чей чек-лист редактируем.
            bg_color — фон; при None — fallback.
            log_manager_v2 — LogManagerV2 или None.
        """

        self._mode = mode
        self._task = task
        from ui.styles import WindowStyle, ColorCalculator
        parent_bg = WindowStyle.resolve_parent_bg(
            parent, (60, 50, 40, 0.95),
        )
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 20,
            g_fn=lambda g: g + 10,
            b_fn=lambda b: b ,
            alpha=0.95,
        )

        is_view = (self._mode == "view")

        super().__init__(
            parent=parent,
            title=f"Чек-лист: {task.title}",
            bg_color=self.bg_color,

            width=225, height=250,
            close_button=False,
            ok_cancel=not is_view,
            draggable=True,
            close_on_click_outside=is_view,
            modal=True,
            center=True,
            log_manager_v2=log_manager_v2,
        )

    def _build_content(self, layout) -> None:
        """Внутрь — ChecklistWidget(mode='edit')."""
        from ui.widgets.checklist_widget import ChecklistWidget

        self._widget = ChecklistWidget(
            self,
            items=list(self._task.checklist),
            mode=self._mode,
            bg_color=self.bg_color,
            task_id=self._task.task_id,
        )
        layout.addWidget(self._widget)

    def _collect_result(self):
        """Собирает результат диалога (список ChecklistItem)."""
        if self._mode == "view":
            return None
        return self._widget.get_items()
