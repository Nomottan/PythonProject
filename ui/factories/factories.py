"""
Шим обратной совместимости для ui.factories.

Реэкспортирует публичный API из специализированных модулей, чтобы
сохранить существующие импорты:

    from ui.factories.factories import ButtonFactory, WindowFactory

Новые модули:
    base_factory           — BaseWidgetFactory.
    button_factory         — ButtonFactory, ActionButtonType.
    input_factory          — InputWidgetFactory.
    element_factory        — StatusLabel, LabelFactory.
    widget_factory         — ListWidgetFactory, StatusLogFactory.
    layout_factory         — LayoutFactory.
    infrastructure_factory — ThreadFactory, FileDialogFactory.
    window_factories       — WindowFactory, ExtendedWindowFactory.
    composite_widget_factory — CompositeWidgetFactory.

Планировщик-специфичные виджеты (кнопки-слоты, поля дедлайна)
живут в ui.widgets и тоже реэкспортируются отсюда — чтобы окна
не переезжали на прямые пути.
"""

from .base_factory import BaseWidgetFactory
from .button_factory import ButtonFactory, ActionButtonType
from .input_factory import InputWidgetFactory
from .element_factory import StatusLabel, LabelFactory
from .widget_factory import ListWidgetFactory, StatusLogFactory
from .layout_factory import LayoutFactory
from .infrastructure_factory import ThreadFactory, FileDialogFactory
from .window_factories import WindowFactory, ExtendedWindowFactory
from .composite_widget_factory import CompositeWidgetFactory

# Планировщик-специфичные виджеты — из ui.widgets.
from ui.widgets.planner_slot_buttons import (
    DeadlineTaskButton, InstanceTaskButton,
    EventTaskButton, SimpleTaskButton,
)
from ui.widgets.planner_dl_fields_widget import DeadlineFieldsWidget


__all__ = [
    # Базовые
    "BaseWidgetFactory",
    # Кнопки
    "ButtonFactory", "ActionButtonType",
    # Ввод
    "InputWidgetFactory",
    # Метки
    "StatusLabel", "LabelFactory",
    # Списки и лог
    "ListWidgetFactory", "StatusLogFactory",
    # Компоновки
    "LayoutFactory",
    # Инфраструктура
    "ThreadFactory", "FileDialogFactory",
    # Окна
    "WindowFactory", "ExtendedWindowFactory",
    # Составные
    "CompositeWidgetFactory",
    # Планировщик-специфичные
    "DeadlineTaskButton", "InstanceTaskButton",
    "EventTaskButton", "SimpleTaskButton",
    "DeadlineFieldsWidget",
]

