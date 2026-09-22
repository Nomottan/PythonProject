"""
Диалог редактирования правила повторения при восстановлении
регулярной задачи из архива.
"""

from PySide6.QtWidgets import QDialog
from PySide6.QtCore import Qt

from ui.factories.factories import ButtonFactory, LabelFactory
from ui.factories.window_factories import ExtendedWindowFactory
from models.planner_task import PlannerTask


class PlannerRecurrenceEditDialog(QDialog):
    """Диалог редактирования правила повторения.

    Роль: открывается из PlannerArchiveWindow при восстановлении
          регулярной задачи. Позволяет задать новое правило.
    """

    def __init__(self, parent=None, task: PlannerTask = None):
        super().__init__(parent)
        self._task = task
        bg_color = (70, 80, 90, 0.95)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Восстановление регулярной задачи",
            bg_color=bg_color,
            close_button=False,
            ok_cancel=True,
            ok_callback=self.accept,
            cancel_callback=self.reject,
            draggable=True,
            return_content_layout=True,
            default_width=420,
            default_height=300,
        )

        content_layout.addWidget(LabelFactory.create_label(
            self, f"Задача: {task.title}",
            bg_color=(0, 0, 0, 0), text_color="#ffffff",
            alignment=Qt.AlignCenter, font_size=13, font_weight="bold",
            word_wrap=True,
        ))

        # Поля правила — из фабрики, с предзаполнением из задачи.
        initial = None
        if task and task.recurrence_type:
            initial = {
                "type": task.recurrence_type,
                "value": task.recurrence_value,
                "weekdays": task.recurrence_weekdays,
                "monthdays": task.recurrence_monthdays,
                "use_last_day": task.recurrence_use_last_day,
            }
        self._fields = ButtonFactory.create_recurrence_fields(self, initial)
        content_layout.addWidget(self._fields)

    def get_recurrence_data(self):
        """Возвращает правило повторения."""
        return self._fields.get_recurrence_data()