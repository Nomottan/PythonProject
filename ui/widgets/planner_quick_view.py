"""
Виджет быстрого просмотра активных задач — «мини-планировщик».

Семь слотов-кнопок: 1 DEADLINE, 3 HIGH, 2 MEDIUM, 1 LOW (по умолчанию).
Для дедлайн-задач слот — DeadlineTaskButton с прогрессбаром. Для
остальных — QPushButton с цветной полосой слева.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from ui.factories.factories import (
    ButtonFactory, BaseWidgetFactory, DeadlineTaskButton,
)
from models.planner_task import TaskPriority


class PlannerQuickView(QWidget):
    """Виджет с 7 кнопками задач.

    Назначение:
        Показать до 7 активных задач. Слоты распределяет
        PlannerQuickViewController; виджет только отображает.

    Сигналы:
        task_clicked(object) — task_id нажатой задачи. object, а не int:
                               task_id = YYYYMMDDNNN превышает 2^31.
    """

    task_clicked = Signal(object)

    SLOT_COUNT = 7

    # Стили обычной кнопки (не-дедлайн).
    SLOT_BG = (78, 78, 83, 0.95)
    SLOT_BG_HOVER = (98, 98, 103, 0.95)
    SLOT_BG_PRESSED = (60, 60, 65, 0.95)
    SLOT_TEXT = "#e0e0e0"

    def __init__(self, parent=None):
        super().__init__(parent)

        # Фон контейнера — темнее главного окна.
        self.setObjectName("planner_quick_view_root")
        self.setStyleSheet("""
            QWidget#planner_quick_view_root {
                background-color: rgba(40, 40, 45, 0.7);
                border-radius: 6px;
            }
        """)
        self.setMaximumWidth(400)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)

        # Состояние слотов.
        self._slot_widgets: list = [None] * self.SLOT_COUNT
        self._slot_task_ids: list = [None] * self.SLOT_COUNT
        self._slot_tasks: list = [None] * self.SLOT_COUNT

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    # ---------- Публичный API ----------

    def set_slots(self, slots: list) -> None:
        """Полностью пересобирает слоты.

        Вход: slots — список длиной SLOT_COUNT. Элемент:
            None — пустой слот (пропускается);
            (task, color) — заполненный слот.
        """
        # Очистка.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._slot_widgets = [None] * self.SLOT_COUNT
        self._slot_task_ids = [None] * self.SLOT_COUNT
        self._slot_tasks = [None] * self.SLOT_COUNT

        for i in range(self.SLOT_COUNT):
            slot = slots[i] if i < len(slots) else None
            if slot is None:
                continue
            task, color = slot
            widget = self._create_widget(task, color, i)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._layout.addWidget(widget)
            self._slot_widgets[i] = widget
            self._slot_task_ids[i] = task.task_id
            self._slot_tasks[i] = task

    def update_slot(self, index: int, task, color) -> None:
        """Обновляет содержимое слота (для карусели).

        Тип виджета не меняется: карусель крутит задачи одного приоритета.
        Поэтому только текст (и прогресс для дедлайна).
        """
        widget = self._slot_widgets[index]
        if widget is None:
            return
        if isinstance(widget, DeadlineTaskButton):
            widget.set_task(task)
        else:
            widget.setText(task.title)
        self._slot_task_ids[index] = task.task_id
        self._slot_tasks[index] = task

    def update_deadline_progress(self) -> None:
        """Обновляет прогрессбары у всех дедлайн-слотов.

        Роль: вызывается таймером контроллера (60 сек) — без полной
              перерисовки слотов.
        """
        for i, task in enumerate(self._slot_tasks):
            w = self._slot_widgets[i]
            if isinstance(w, DeadlineTaskButton) and task is not None:
                w.update_progress(task)

    def show_empty(self) -> None:
        """Показать «Нет активных задач» в верхнем слоте."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._slot_widgets = [None] * self.SLOT_COUNT
        self._slot_task_ids = [None] * self.SLOT_COUNT
        self._slot_tasks = [None] * self.SLOT_COUNT

        empty_btn = QPushButton("Нет активных задач")
        empty_btn.setEnabled(False)
        empty_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 50, 50, 0.5);
                color: #909090;
                text-align: left;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-size: 11px;
            }
        """)
        self._layout.addWidget(empty_btn)

    # ---------- Внутренние ----------

    def _create_widget(self, task, color, index: int):
        """Создаёт виджет слота: DeadlineTaskButton или QPushButton."""
        if task.priority == TaskPriority.DEADLINE:
            widget = ButtonFactory.create_deadline_button(self)
            widget.set_task(task)
            widget.clicked.connect(lambda idx=index: self._on_widget_clicked(idx))
            return widget

        # Обычная кнопка.
        btn = QPushButton(self)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setText(task.title)
        btn.setToolTip("")
        self._apply_regular_style(btn, color)
        btn.clicked.connect(
            lambda checked=False, idx=index: self._on_widget_clicked(idx)
        )
        return btn

    def _apply_regular_style(self, btn: QPushButton, color) -> None:
        """Единый QSS для не-дедлайн кнопки: фон + полоса слева."""
        stripe = BaseWidgetFactory.color_to_str(color)
        bg = BaseWidgetFactory.color_to_str(self.SLOT_BG)
        bg_hover = BaseWidgetFactory.color_to_str(self.SLOT_BG_HOVER)
        bg_pressed = BaseWidgetFactory.color_to_str(self.SLOT_BG_PRESSED)

        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {self.SLOT_TEXT};
                text-align: left;
                padding: 6px 12px 6px 14px;
                border: none;
                border-left: 4px solid {stripe};
                border-radius: 4px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:pressed {{
                background-color: {bg_pressed};
            }}
        """)

    def _on_widget_clicked(self, index: int) -> None:
        """Клик по слоту — испускает task_clicked с текущим task_id."""
        task_id = self._slot_task_ids[index]
        if task_id is None:
            return
        self.task_clicked.emit(task_id)