"""
Публичный API пакета ui.factories.

Реэкспортирует всё, что находится в шиме factories — чтобы
работали импорты как через ui.factories.factories, так и через
ui.factories:

    from ui.factories import ButtonFactory, WindowFactory
"""

from .factories import (
    BaseWidgetFactory,
    ButtonFactory, ActionButtonType,
    InputWidgetFactory,
    StatusLabel, LabelFactory,
    ListWidgetFactory, StatusLogFactory,
    LayoutFactory,
    ThreadFactory, FileDialogFactory,
    WindowFactory, ExtendedWindowFactory,
    CompositeWidgetFactory,
    DeadlineTaskButton, InstanceTaskButton,
    EventTaskButton, SimpleTaskButton,
    DeadlineFieldsWidget,
)

__all__ = [
    "BaseWidgetFactory",
    "ButtonFactory", "ActionButtonType",
    "InputWidgetFactory",
    "StatusLabel", "LabelFactory",
    "ListWidgetFactory", "StatusLogFactory",
    "LayoutFactory",
    "ThreadFactory", "FileDialogFactory",
    "WindowFactory", "ExtendedWindowFactory",
    "CompositeWidgetFactory",
    "DeadlineTaskButton", "InstanceTaskButton",
    "EventTaskButton", "SimpleTaskButton",
    "DeadlineFieldsWidget",
]