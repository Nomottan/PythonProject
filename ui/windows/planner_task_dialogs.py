"""
Три диалога задачи: создание/редактирование обычной задачи,
восстановление дедлайна, восстановление регулярной задачи.
+ специлизированное окно для выбора чисел месяца для регулярных задач от BaseEditDialog.
"""

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory, LayoutFactory,
    DeadlineFieldsWidget,
)
from ui.base.base_edit_dialog import BaseEditDialog
from ui.base.base_planner_dialogs import BaseTaskDialog
from ui.factories.composite_widget_factory import CompositeWidgetFactory
from ui.windows.message_dialog import MessageDialog, NotificationDialog
from ui.widgets.planner_day_picker_widget import PlannerDayPickerWidget
from models.planner_task import TaskPriority, PlannerTask, ThemeKey
from ui.styles import ColorCalculator, WindowStyle


class NewTaskDialog(BaseTaskDialog):
    """Диалог создания/редактирования задачи."""

    def __init__(self, parent=None, planner_service=None, task=None, main_config=None):
        self.service = planner_service
        self.creator = task is None
        self._main_config = main_config

        parent_bg = WindowStyle.resolve_parent_bg(parent, (111, 78, 55))
        if self.creator:
            self.bg_color = ColorCalculator.derive(
                parent_bg,
                r_fn=lambda r: r + 10,
                g_fn=lambda g: g + 10,
                b_fn=lambda b: b - 20,
                alpha=0.95,
            )
        else:
            self.bg_color = ColorCalculator.derive(
                parent_bg,
                r_fn=lambda r: r - 20,
                g_fn=lambda g: g + 10,
                b_fn=lambda b: b + 10,
                alpha=0.95,
            )

        super().__init__(
            parent=parent,
            task=task,
            title="Новая задача",
            bg_color=self.bg_color,
            width=400,
            height=350,
        )

    def _build_content(self, layout) -> None:
        """Строит форму задачи."""
        # --- Скрытое поле описания ---
        self.full_desc_edit = InputWidgetFactory.create_text_edit(
            self,
            placeholder="Подробное описание...",
            bg_color=self._elements_bg,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
        )
        self.full_desc_edit.setReadOnly(True)
        layout.addWidget(self.full_desc_edit)

        # --- Поле названия ---
        self.task_edit = InputWidgetFactory.create_line_edit(
            self,
            bg_color=self._elements_bg,
            text_color=None,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
            border_radius=3,
            padding="3px",
        )

        # Чекбокс чек-листа.
        self.checklist_cb = InputWidgetFactory.create_checkbox(
            self, text="",
            checked=(not self.creator and self._task.checklist_required),
            bg_color=self._elements_bg,
        )
        self.checklist_cb.clicked.connect(self._on_checklist_cb_clicked)

        # --- Приоритеты ---
        priorities = (
            self.service.get_priorities() if self.service
            else ["Дедлайн", "Высокий", "Средний", "Низкий"]
        )
        self.priority_combo = InputWidgetFactory.create_combo_box(
            self,
            items=priorities,
            bg_color=self._elements_bg,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
        )
        medium_name = TaskPriority.MEDIUM.display_name
        medium_idx = self.priority_combo.findText(medium_name)
        if medium_idx >= 0:
            self.priority_combo.setCurrentIndex(medium_idx)

        # --- Combo типа дедлайна ---
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=self._elements_bg,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
        )
        self.deadline_type_combo.setVisible(False)

        # --- Поля правила повторения ---
        initial = None
        if (not self.creator
                and self._task.priority == TaskPriority.RECURRING
                and self._task.recurrence_type):
            initial = {
                "type": self._task.recurrence_type,
                "value": self._task.recurrence_value,
                "weekdays": self._task.recurrence_weekdays,
                "monthdays": self._task.recurrence_monthdays,
                "use_last_day": self._task.recurrence_use_last_day,
            }
        self._recurrence_fields = CompositeWidgetFactory.create_recurrence_fields(
            self, initial, field_bg=self._elements_bg, label_bg=self._labels_bg,
        )
        self._recurrence_fields.setVisible(False)
        self._recurrence_fields.rule_combo.setVisible(False)

        # --- Строка «Приоритет»: три combo ---
        priority_row = QWidget()
        priority_row_layout = QHBoxLayout(priority_row)
        priority_row_layout.setContentsMargins(0, 0, 0, 0)
        priority_row_layout.setSpacing(6)
        priority_row_layout.addWidget(self.priority_combo, 1)
        priority_row_layout.addWidget(self.deadline_type_combo, 1)
        priority_row_layout.addWidget(self._recurrence_fields.rule_combo, 1)

        self.task_edit.textChanged.connect(self._on_title_changed)

        # --- Поля дедлайна ---
        initial_deadline = self._task.deadline_datetime if not self.creator else None
        self._deadline_fields = DeadlineFieldsWidget(
            self, field_bg=self._elements_bg, label_bg=self._labels_bg,
            initial=initial_deadline
        )
        self._deadline_fields.setVisible(False)

        # --- Тема ---
        self.theme_combo = InputWidgetFactory.create_combo_box(
            self, items=[], bg_color=self._elements_bg,
        )
        raw_themes = self._main_config.get("planner_themes", {}) if self._main_config else {}
        if not isinstance(raw_themes, dict):
            raw_themes = {}
        for key in ThemeKey:
            self.theme_combo.addItem(ThemeKey.resolve_effective_name(key, raw_themes), key.value)

        current_theme = self._task.theme if not self.creator else "black"
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

        # --- Форма ---
        label_kwargs = {
            "bg_color": self._labels_bg,
            "text_color": ColorCalculator.text_for(self._labels_bg),
            "padding": "4px 8px",
            "border_radius": 3,
            "alignment": Qt.AlignLeft | Qt.AlignVCenter,
            "fixed_size": (120, 24),
        }
        task_label = LabelFactory.create_label(self, "Задача:", **label_kwargs)
        checklist_label = LabelFactory.create_label(self, "Чек-лист:", **label_kwargs)
        theme_label = LabelFactory.create_label(self, "Тема:", **label_kwargs)
        priority_label = LabelFactory.create_label(self, "Приоритет:", **label_kwargs)

        # Дата события (теперь часть формы)
        self.event_label = LabelFactory.create_label(self, "Дата события:", **label_kwargs)
        self._event_date_edit = InputWidgetFactory.create_line_edit(
            self,
            bg_color=self._elements_bg,
            text_color=None,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
            border_radius=3,
            padding="3px",
        )
        self._event_date_edit.setInputMask("99.99.9999")
        self.event_label.setVisible(False)
        self._event_date_edit.setVisible(False)

        form = LayoutFactory.create_form(
            self,
            rows=[
                (task_label, self.task_edit),
                (checklist_label, self.checklist_cb),
                (theme_label, self.theme_combo),
                (priority_label, priority_row),
                (self.event_label, self._event_date_edit),
                (None, self._deadline_fields),
                (None, self._recurrence_fields),
            ],
            spacing=10,
            margins=(10, 10, 10, 10),
        )
        layout.addWidget(form)

        # --- Триггеры ---
        self.priority_combo.currentTextChanged.connect(self._on_priority_changed)
        self.deadline_type_combo.currentTextChanged.connect(self._on_deadline_type_changed)

        # --- Предзаполнение при редактировании ---
        if not self.creator:
            self.task_edit.setText(self._task.title)
            self.full_desc_edit.setPlainText(self._task.description)
            for i in range(self.priority_combo.count()):
                if self.priority_combo.itemText(i) == self._task.priority.display_name:
                    self.priority_combo.setCurrentIndex(i)
                    break
            self._on_priority_changed(self.priority_combo.currentText())
            if (self._task.priority == TaskPriority.EVENT
                    and self._task.event_date):
                self._event_date_edit.setText(self._task.event_date)

    def _validate(self) -> bool:
        if not self.task_edit.text().strip():
            result = MessageDialog.warning(
                self,
                "Название задачи не может быть пустым.\n"
                "Хотите продолжить создание задачи?",
                bg_color=self.bg_color,
            )
            if result == "no":
                self.reject()
            return False

        if self.priority_combo.currentText() == TaskPriority.EVENT.display_name:
            date_str = self._event_date_edit.text().strip()
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                MessageDialog.warning(
                    self,
                    "Введите корректную дату события в формате ДД.ММ.ГГГГ.",
                    bg_color=self.bg_color,
                )
                return False
        return True

    def _collect_result(self):
        priority = self.service.get_priority_by_display_name(
            self.priority_combo.currentText()
        )
        return {
            "title": self.task_edit.text().strip(),
            "description": self.full_desc_edit.toPlainText().strip(),
            "priority": priority,
            "deadline_datetime": self._deadline_fields.get_deadline_data(
                "inclusive" if self.deadline_type_combo.currentText() == "До даты включительно" else "duration"
            ) if priority == TaskPriority.DEADLINE else None,
            "recurrence_data": self._recurrence_fields.get_recurrence_data()
            if priority == TaskPriority.RECURRING else None,
            "event_date": self._event_date_edit.text().strip()
            if priority == TaskPriority.EVENT else None,
            "checklist_required": self.checklist_cb.isChecked(),
            "theme": self.theme_combo.currentData(),
        }

    def _on_title_changed(self, text: str) -> None:
        self.full_desc_edit.setReadOnly(not bool(text.strip()))

    def _on_deadline_type_changed(self, text: str) -> None:
        mode = "inclusive" if text == "До даты включительно" else "duration"
        self._deadline_fields.set_mode(mode)

    def _on_priority_changed(self, text: str) -> None:
        """Показывает поля, соответствующие приоритету."""
        is_deadline = (text == TaskPriority.DEADLINE.display_name)
        is_recurring = (text == TaskPriority.RECURRING.display_name)
        is_event = (text == TaskPriority.EVENT.display_name)

        self.deadline_type_combo.setVisible(is_deadline)
        self._deadline_fields.setVisible(is_deadline)

        self._recurrence_fields.rule_combo.setVisible(is_recurring)
        self._recurrence_fields.setVisible(is_recurring)

        self.event_label.setVisible(is_event)
        self._event_date_edit.setVisible(is_event)
        if not is_event:
            self._event_date_edit.clear()

    def _on_checklist_cb_clicked(self, checked: bool) -> None:
        if self.creator:
            return
        if (not checked
                and self._task.checklist_required
                and self._task.checklist):
            NotificationDialog.notify(
                self,
                "Невозможно убрать чек-лист: он не пуст.",
                bg_color=self.bg_color,
            )
            self.checklist_cb.setChecked(True)


class DeadlineEditDialog(BaseTaskDialog):
    """Диалог редактирования дедлайна при восстановлении из архива."""

    def __init__(self, parent=None, task=None):
        parent_bg = WindowStyle.resolve_parent_bg(parent, (70, 80, 90))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 20,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b - 10,
            alpha=0.95,
        )
        super().__init__(
            parent=parent,
            task=task,
            title="Восстановление дедлайна",
            bg_color=self.bg_color,
            width=420,
            height=280,
        )

    def _build_content(self, layout) -> None:
        layout.addWidget(self._build_title_label())

        type_row = QWidget()
        type_row_layout = QHBoxLayout(type_row)
        type_row_layout.setContentsMargins(0, 0, 0, 0)
        type_row_layout.setSpacing(6)
        type_row_layout.addWidget(LabelFactory.create_label(
            type_row, "Тип:",
            bg_color=self._labels_bg, text_color=ColorCalculator.text_for(self._labels_bg), font_size=11,
        ))
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            type_row,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=self._elements_bg,
            border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
        )
        type_row_layout.addWidget(self.deadline_type_combo, 1)
        layout.addWidget(type_row)

        self._deadline_fields = DeadlineFieldsWidget(
            self,
            initial=self._task.deadline_datetime,
            mode="inclusive",
            field_bg=self._elements_bg,
            label_bg=self._labels_bg,
            field_border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
        )
        layout.addWidget(self._deadline_fields)

        self.deadline_type_combo.currentTextChanged.connect(
            lambda text: self._deadline_fields.set_mode(
                "inclusive" if text == "До даты включительно" else "duration"
            )
        )

    def _collect_result(self):
        mode = (
            "inclusive"
            if self.deadline_type_combo.currentText() == "До даты включительно"
            else "duration"
        )
        return {
            "deadline_datetime": self._deadline_fields.get_deadline_data(mode),
        }


class PlannerRecurrenceEditDialog(BaseTaskDialog):
    """Диалог редактирования правила повторения при восстановлении."""

    def __init__(self, parent=None, task=None):
        parent_bg = WindowStyle.resolve_parent_bg(parent, (70, 80, 90))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r - 10,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b + 20,
            alpha=0.95,
        )
        super().__init__(
            parent=parent,
            task=task,
            title="Восстановление регулярной задачи",
            bg_color=self.bg_color,
            width=420,
            height=300,
        )

    def _build_content(self, layout) -> None:
        layout.addWidget(self._build_title_label())

        initial = None
        if self._task and self._task.recurrence_type:
            initial = {
                "type": self._task.recurrence_type,
                "value": self._task.recurrence_value,
                "weekdays": self._task.recurrence_weekdays,
                "monthdays": self._task.recurrence_monthdays,
                "use_last_day": self._task.recurrence_use_last_day,
            }
        self._recurrence_fields = CompositeWidgetFactory.create_recurrence_fields(
            self, initial,
            field_bg=self._elements_bg,
            field_border=f"1px solid {ColorCalculator.to_str(self._elements_bg)}",
            label_bg=self._labels_bg,
        )
        layout.addWidget(self._recurrence_fields.rule_combo)
        layout.addWidget(self._recurrence_fields)

    def _collect_result(self):
        return {
            "recurrence_data": self._recurrence_fields.get_recurrence_data(),
        }


class PlannerDayPickerDialog(BaseEditDialog):
    """Диалог выбора чисел месяца."""

    def __init__(self, parent=None, selected=None):
        self._initial_selected = list(selected or [])
        self._widget = None
        self._use_last_day = False

        super().__init__(
            parent=parent,
            title="Выберите числа месяца",
            bg_color=(70, 80, 90, 0.95),
            close_button=False,
            ok_cancel=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=420,
            height=400,
        )

    def _build_content(self, layout) -> None:
        self._widget = PlannerDayPickerWidget(
            self, selected=self._initial_selected,
        )
        layout.addWidget(self._widget)

    def _validate(self) -> bool:
        selected = self._widget.get_selected()
        if any(d in (29, 30, 31) for d in selected):
            reply = MessageDialog.question(
                self,
                "В некоторых месяцах недостаточно дней. "
                "Выбирать последнюю дату в них?",
                title_text="Последний день",
                bg_color=(70, 80, 90),
            )
            self._use_last_day = (reply == "yes")
        return True

    def get_selected(self) -> list:
        return self._widget.get_selected()

    def get_use_last_day(self) -> bool:
        return self._use_last_day