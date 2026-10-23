"""
Базовые диалоги для планировщика.

Содержит BaseTaskDialog (общий предок диалогов задачи) и
BaseThemePickerDialog (общий предок пикеров тем).
"""

from PySide6.QtCore import Signal

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import ButtonFactory, ListWidgetFactory
from ui.styles import ColorCalculator, WindowStyle


class BaseTaskDialog(BaseEditDialog):
    """Базовый диалог задачи.

    Назначение:
        Общий предок для трёх диалогов задачи. Убирает дублирование
        каркаса и хранения ссылки на задачу.

    Роль в программе:
        Промежуточный слой. Наследники переопределяют _build_content,
        _collect_result, _validate.

    Атрибуты:
        _labels_bg — цвет фона лейблов (вычисляется до super().__init__).
        _elements_bg — цвет фона полей ввода (вычисляется до super().__init__).
    """

    LABEL_SHIFT = (-5, -5, -5)
    ELEMENT_SHIFT = (-15, -15, -15)

    def __init__(self, parent=None, task=None, title="",
                 bg_color=(64, 48, 66, 0.8), width=400, height=350,
                 close_button=False, ok_cancel=True,
                 draggable=True, close_on_click_outside=False,
                 modal=True, center=True, on_close=None,
                 log_manager_v2=None):
        """Конструктор."""
        self._task = task

        alpha = bg_color[3] if len(bg_color) == 4 else 1.0

        self._labels_bg = ColorCalculator.derive(
            bg_color,
            r_fn=lambda r: r + self.LABEL_SHIFT[0],
            g_fn=lambda g: g + self.LABEL_SHIFT[1],
            b_fn=lambda b: b + self.LABEL_SHIFT[2],
            alpha=alpha,
        )

        self._elements_bg = ColorCalculator.derive(
            bg_color,
            r_fn=lambda r: r + self.ELEMENT_SHIFT[0],
            g_fn=lambda g: g + self.ELEMENT_SHIFT[1],
            b_fn=lambda b: b + self.ELEMENT_SHIFT[2],
            alpha=alpha,
        )

        super().__init__(
            parent=parent, title=title, bg_color=bg_color,
            width=width, height=height, close_button=close_button,
            ok_cancel=ok_cancel, draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal, center=center, on_close=on_close,
            log_manager_v2=log_manager_v2,
        )

    def _build_title_label(self):
        """Создает стандартный лейбл с названием задачи."""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import Qt
        from ui.factories.factories import LabelFactory
        return LabelFactory.create_label(
            self, f"Задача: {self._task.title}",
            bg_color=self._labels_bg,
            text_color=ColorCalculator.text_for(self._labels_bg),
            alignment=Qt.AlignCenter, word_wrap=True,
            font_size=13, font_weight="bold",
        )


class BaseThemePickerDialog(BaseEditDialog):
    """Базовый диалог выбора темы из списка кнопок.

    Наследники должны определить LOGGER_SOURCE / LOGGER_DOMAIN.
    """
    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None
    theme_selected = Signal(str)

    def __init__(self, parent, items: list, title="Выбор", width=220, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель.
            items — список кортежей (текст, цвет, выбран_ли).
            title — заголовок окна.
            width — ширина.
            log_manager_v2 — логгер.
        """
        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self._bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r // 2,
            g_fn=lambda g: int(g // 1.5),
            b_fn=lambda b: int(b // 1.3),
            alpha=0.95,
        )
        self._items = items
        super().__init__(
            parent=parent,
            title=title,
            bg_color=self._bg_color,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=True,
            modal=False,
            center=True,
            width=width,
            height=400,
            log_manager_v2=log_manager_v2,
        )

    def _build_content(self, layout) -> None:
        scroll_container, _, content_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=4, bg_color=self._bg_color,
        )
        for text, color, is_selected in self._items:
            bg = color
            if is_selected:
                bg = ColorCalculator.derive(
                    color,
                    r_fn=lambda r: r + 5,
                    g_fn=lambda g: g + 5,
                    b_fn=lambda b: b + 5,
                    alpha=0.95,
                )
            btn = ButtonFactory.create_button(
                self, text=text, bg_color=bg, padding="6px 12px",
            )
            btn.clicked.connect(lambda checked=False, t=text: self._on_pick(t))
            content_layout.addWidget(btn)
        layout.addWidget(scroll_container)

    def _on_pick(self, text) -> None:
        self.theme_selected.emit(text)
        self.accept()

    def _validate(self) -> bool:
        return True

    def _collect_result(self):
        return None