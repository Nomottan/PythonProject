"""
Пакет ui.widgets — кастомные виджеты проекта.

Модули:
    planner_slot_buttons.py             — кнопки-слоты мини-планировщика
                                          (_BaseTaskButton, DeadlineTaskButton,
                                          InstanceTaskButton, EventTaskButton,
                                          SimpleTaskButton).
    planner_dl_fields_widget.py         — поля ввода дедлайна.
    planner_recurrence_fields_widget.py — поля правила повторения.
    planner_day_picker_widget.py        — сетка выбора чисел месяца.
    status_log.py                       — QTextEdit-лог статуса.
    editable_list_widget.py             — редактируемый список строк.
    path_selector.py                    — виджет выбора папки.

Публичные виджеты реэкспортируются. _BaseTaskButton — приватный,
наружу не выходит.
"""

from .planner_slot_buttons import (
    DeadlineTaskButton, InstanceTaskButton,
    EventTaskButton, SimpleTaskButton,
)
from .planner_dl_fields_widget import DeadlineFieldsWidget
from .path_selector import PathSelector
from .editable_list_widget import EditableListWidget

__all__ = [
    "DeadlineTaskButton",
    "InstanceTaskButton",
    "EventTaskButton",
    "SimpleTaskButton",
    "DeadlineFieldsWidget",
    "PathSelector",
    "EditableListWidget",
]