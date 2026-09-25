"""
Виджет быстрого просмотра активных задач — «мини-планировщик».

Слоты-кнопки: 9 слотов. Раскладку распределяет
PlannerQuickViewController. Для дедлайн-задач слот — прогрессбар,
для экземпляров и событий — цветная полоса, для остальных — та же
кнопка-слот с цветом приоритета.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from ui.factories.composite_widget_factory import CompositeWidgetFactory
from models.planner_task import TaskPriority


class PlannerQuickView(QWidget):
    """Виджет с 9 кнопками задач.

    Назначение:
        Показать до 9 активных задач. Слоты распределяет
        PlannerQuickViewController; виджет только отображает.

    Сигналы:
        task_clicked(object) — task_id нажатой задачи. object, а не int:
                               task_id = YYYYMMDDNNN превышает 2^31.
    """

    task_clicked = Signal(object)

    SLOT_COUNT = 9

    def __init__(self, parent=None):
        """Конструктор.

        Вход: parent — родительский виджет.
        Роль: создаёт контейнерный layout и хранилище состояния слотов.
        """
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

        Вход: index — номер слота; task — новая задача; color — цвет
              полосы приоритета.

        Роль: тип виджета не меняется — карусель крутит задачи
              одного приоритета. Обновляем только текст и прогресс.
        """
        widget = self._slot_widgets[index]
        if widget is None:
            return
        if hasattr(widget, "set_task"):
            widget.set_task(task)
        elif hasattr(widget, "setText"):
            widget.setText(task.title)
        self._slot_task_ids[index] = task.task_id
        self._slot_tasks[index] = task

    def update_deadline_progress(self) -> None:
        """Обновляет прогрессбары у всех дедлайн-слотов.

        Роль: вызывается таймером контроллера (60 сек) — без полной
              перерисовки слотов. Локальный импорт — DeadlineTaskButton
              используется только здесь, чтобы не тянуть зависимость
              в шапку модуля.
        """
        from ui.widgets.planner_slot_buttons import DeadlineTaskButton
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
        """Создаёт виджет слота.

        Вход:
            task — PlannerTask.
            color — цвет полосы приоритета.
            index — номер слота (для замыкания в лямбде).

        Выход: QWidget-слот одного из трёх видов.

        Роль: единая точка выбора виджета по типу задачи.
              Конкретный цвет полосы задаётся здесь.
        """
        # DEADLINE → слот с прогрессбаром.
        if task.priority == TaskPriority.DEADLINE:
            widget = CompositeWidgetFactory.create_progress_slot(self)
        # EVENT → жёлтая полоса.
        elif task.is_event():
            widget = CompositeWidgetFactory.create_event_slot(self)
        # INSTANCE → голубая полоса.
        elif task.is_recurring_instance():
            widget = CompositeWidgetFactory.create_striped_slot(
                self, stripe_color=(80, 160, 220, 1.0))
        # Обычная задача → SimpleTaskButton с цветом приоритета.
        else:
            widget = CompositeWidgetFactory.create_simple_slot(
                self, stripe_color=color)

        widget.set_task(task)
        widget.clicked.connect(
            lambda idx=index: self._on_widget_clicked(idx)
        )
        return widget

    def _on_widget_clicked(self, index: int) -> None:
        """Клик по слоту — испускает task_clicked с текущим task_id."""
        task_id = self._slot_task_ids[index]
        if task_id is None:
            return
        self.task_clicked.emit(task_id)