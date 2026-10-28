"""
Виджет быстрого просмотра активных задач — «мини-планировщик».

Слоты-кнопки: 9 слотов. Раскладку распределяет
PlannerQuickViewController. Для дедлайн-задач слот — прогрессбар,
для экземпляров и событий — цветная полоса, для остальных — та же
кнопка-слот с цветом приоритета.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from ui.factories.factories import ButtonFactory
from ui.factories.composite_widget_factory import CompositeWidgetFactory
from ui.styles import ColorCalculator, WidgetStyle
from models.planner_task import TaskPriority, ThemeKey


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
        WidgetStyle.apply_panel(
            self, bg_color=(40, 40, 45, 0.7), border_radius=6
        )
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
              полосы приоритета (legacy).

        Роль: тип виджета не меняется — карусель крутит задачи
              одного приоритета. Обновляем текст, прогресс, а также
              пересчитываем фон под тему новой задачи через
              widget.set_theme (если метод есть).
        """
        widget = self._slot_widgets[index]
        if widget is None:
            return
        if hasattr(widget, "set_task"):
            widget.set_task(task)
        elif hasattr(widget, "setText"):
            widget.setText(task.title)

        if hasattr(widget, "set_theme"):
            theme_key, main_bg = self._resolve_theme_and_bg(task)
            widget.set_theme(theme_key, main_bg)

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

        empty_btn = ButtonFactory.create_button(
            self,
            text="Нет активных задач",
            bg_color=(50, 50, 50, 0.5),
            text_color=ColorCalculator.to_str((144, 144, 144)),
            padding="6px 12px",
            border="none",
            border_radius=4,
            alignment="left",
            font_size=11,
        )
        empty_btn.setEnabled(False)
        self._layout.addWidget(empty_btn)

    # ---------- Внутренние ----------

    def _resolve_theme_and_bg(self, task) -> tuple:
        """Возвращает (ThemeKey, main_bg) для задачи."""
        try:
            theme_key = ThemeKey(task.theme)
        except (ValueError, TypeError):
            theme_key = ThemeKey.BLACK

        window = self.window()
        main_bg = getattr(window, "bg_color", None)
        if not isinstance(main_bg, (tuple, list)) or len(main_bg) < 3:
            main_bg = (50, 50, 50)

        return theme_key, main_bg

    def _create_widget(self, task, color, index: int):
        """Создаёт виджет слота.

        Вход:
            task — PlannerTask.
            color — цвет полосы приоритета.
            index — номер слота (для замыкания в лямбде).

        Выход: QWidget-слот одного из трёх видов.

        Роль: единая точка выбора виджета по типу задачи.
              Резолвит тему и main_bg, передаёт в фабрику.
        """
        theme_key, main_bg = self._resolve_theme_and_bg(task)

        # DEADLINE → слот с прогрессбаром.
        if task.priority == TaskPriority.DEADLINE:
            widget = CompositeWidgetFactory.create_progress_slot(
                self, theme_key=theme_key, main_bg=main_bg
            )
        # EVENT → жёлтая полоса.
        elif task.is_event():
            widget = CompositeWidgetFactory.create_event_slot(
                self, theme_key=theme_key, main_bg=main_bg
            )
        # INSTANCE → голубая полоса.
        elif task.is_recurring_instance():
            widget = CompositeWidgetFactory.create_striped_slot(
                self, stripe_color=(80, 160, 220, 1.0),
                theme_key=theme_key, main_bg=main_bg
            )
        # Обычная задача → SimpleTaskButton с цветом приоритета.
        else:
            widget = CompositeWidgetFactory.create_simple_slot(
                self, stripe_color=color, theme_key=theme_key, main_bg=main_bg
            )

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