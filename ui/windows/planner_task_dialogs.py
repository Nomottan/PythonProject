"""
Три диалога задачи: создание/редактирование обычной задачи,
восстановление дедлайна, восстановление регулярной задачи.

Все наследуют BaseTaskDialog.
"""

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout, QDialog
from PySide6.QtCore import Qt

from ui.base.base_task_dialog import BaseTaskDialog
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory, LayoutFactory,
    DeadlineFieldsWidget,
)
from ui.windows.message_dialog import MessageDialog
from models.planner_task import TaskPriority, PlannerTask
from ui.factories.composite_widget_factory import CompositeWidgetFactory

class NewTaskDialog(BaseTaskDialog):
    """Диалог создания/редактирования задачи.

    Назначение:
        Поля: название, приоритет, описание, тип дедлайна,
        поля дедлайна, правило повторения, дата события.

    Роль в программе:
        Открывается из PlannerWindow по кнопкам «Новая задача»
        и «Редактировать». Наследник BaseTaskDialog.
    """

    def __init__(self, parent=None, planner_service=None, task=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerWindow).
            planner_service — сервис для получения приоритетов.
            task — PlannerTask для редактирования (None при создании).
        """
        self.service = planner_service
        # creator=True — режим создания, False — редактирования.
        self.creator = task is None
        self.bg_color = (111, 78, 55, 0.95)

        super().__init__(
            parent=parent,
            task=task,
            title="Новая задача",
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=400,
            height=350,
        )

    def _build_content(self, layout) -> None:
        """Строит форму задачи.

        Вход: layout — QVBoxLayout из BaseTaskDialog.
        """
        # --- Скрытое поле описания (read-only, пока нет названия). ---
        self.full_desc_edit = InputWidgetFactory.create_text_edit(
            self,
            placeholder="Подробное описание...",
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        self.full_desc_edit.setReadOnly(True)
        layout.addWidget(self.full_desc_edit)

        # --- Поле названия ---
        self.task_edit = InputWidgetFactory.create_line_edit(
            self,
            bg_color=(85, 60, 42, 0.9),
            text_color="#d4d4d4",
            border="1px solid #6b4a33",
            border_radius=3,
            padding="3px",
        )

        # --- Приоритеты ---
        priorities = (
            self.service.get_priorities() if self.service
            else ["Дедлайн", "Высокий", "Средний", "Низкий"]
        )
        self.priority_combo = InputWidgetFactory.create_combo_box(
            self,
            items=priorities,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        # NEW: явно выбираем «Средний» по имени, а не по индексу.
        medium_name = TaskPriority.MEDIUM.display_name
        medium_idx = self.priority_combo.findText(medium_name)
        if medium_idx >= 0:
            self.priority_combo.setCurrentIndex(medium_idx)

        # --- Combo типа дедлайна ---
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        self.deadline_type_combo.setVisible(False)

        # --- Поля правила повторения ---
        self._recurrence_fields = CompositeWidgetFactory.create_recurrence_fields(self)
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
        self._deadline_fields = DeadlineFieldsWidget(self)
        self._deadline_fields.setVisible(False)

        # --- Форма ---
        label_kwargs = {
            "bg_color": (145, 105, 75, 0.0),
            "text_color": "#dabdab",
            "padding": "4px 8px",
            "border_radius": 3,
            "alignment": Qt.AlignLeft | Qt.AlignVCenter,
            "fixed_size": (120, 24),
        }
        task_label = LabelFactory.create_label(self, "Задача:", **label_kwargs)
        priority_label = LabelFactory.create_label(self, "Приоритет:", **label_kwargs)

        form = LayoutFactory.create_form(
            self,
            rows=[
                (task_label, self.task_edit),
                (priority_label, priority_row),
            ],
            spacing=10,
            margins=(10, 10, 10, 10),
        )
        layout.addWidget(form)
        layout.addWidget(self._deadline_fields)
        layout.addWidget(self._recurrence_fields)

        # --- Поля даты события ---
        self._event_date_row = QWidget()
        event_row_layout = QHBoxLayout(self._event_date_row)
        event_row_layout.setContentsMargins(0, 0, 0, 0)
        event_row_layout.setSpacing(6)

        event_label = LabelFactory.create_label(
            self._event_date_row, "Дата события:",
            bg_color=(145, 105, 75, 0.0), text_color="#dabdab",
            padding="4px 8px", border_radius=3,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            fixed_size=(120, 24),
        )
        self._event_date_edit = InputWidgetFactory.create_line_edit(
            self._event_date_row,
            bg_color=(85, 60, 42, 0.9),
            text_color="#d4d4d4",
            border="1px solid #6b4a33",
            border_radius=3,
            padding="3px",
        )
        self._event_date_edit.setInputMask("99.99.9999")
        event_row_layout.addWidget(event_label)
        event_row_layout.addWidget(self._event_date_edit, 1)
        self._event_date_row.setVisible(False)
        layout.addWidget(self._event_date_row)

        # --- Триггеры ---
        self.priority_combo.currentTextChanged.connect(self._on_priority_changed)
        self.deadline_type_combo.currentTextChanged.connect(
            self._on_deadline_type_changed
        )

        # --- Предзаполнение при редактировании ---
        if not self.creator:
            self.task_edit.setText(self.task.title)
            self.full_desc_edit.setPlainText(self.task.description)
            for i in range(self.priority_combo.count()):
                if self.priority_combo.itemText(i) == self.task.priority.display_name:
                    self.priority_combo.setCurrentIndex(i)
                    break
            self._on_priority_changed(self.priority_combo.currentText())
            if (self.task.priority == TaskPriority.DEADLINE
                    and self.task.deadline_datetime):
                self._deadline_fields._load_initial(self.task.deadline_datetime)

    # ---------- Валидация ----------

    def _validate(self) -> bool:
        """Проверяет название и дату события.

        Выход: True — можно закрывать; False — остаться.

        Особенность: при пустом названии спрашивает «продолжить?».
            «Да»  (Accepted) — остаёмся в диалоге, правим название.
            «Нет» (Rejected) — reject() закрывает и предупреждение,
                               и NewTaskDialog.
        """
        if not self.task_edit.text().strip():
            result = MessageDialog.warning(
                self,
                "Название задачи не может быть пустым.\n"
                "Хотите продолжить создание задачи?",
                bg_color=self.bg_color,
            )
            if result == QDialog.Rejected:
                # «Нет» — пользователь передумал создавать задачу.
                # reject() закроет NewTaskDialog с результатом Rejected,
                # и в PlannerWindow._on_new_task ветка создания
                # не сработает.
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
    # ---------- Сбор результата ----------

    def _collect_result(self):
        """Собирает данные задачи в dict.

        Выход: dict с ключами title, description, priority,
               deadline_datetime, recurrence_data, event_date.
        """
        priority = self.service.get_priority_by_display_name(
            self.priority_combo.currentText()
        )
        return {
            "title": self.task_edit.text().strip(),
            "description": self.full_desc_edit.toPlainText().strip(),
            "priority": priority,
            "deadline_datetime": self._deadline_fields.get_deadline_data(
                self.deadline_type_combo.currentText()
            ) if priority == TaskPriority.DEADLINE else None,
            "recurrence_data": self._recurrence_fields.get_recurrence_data()
            if priority == TaskPriority.RECURRING else None,
            "event_date": self._event_date_edit.text().strip()
            if priority == TaskPriority.EVENT else None,
        }

    # ---------- Внутренние слоты ----------

    def _on_title_changed(self, text: str) -> None:
        """Разрешает редактирование описания при непустом названии."""
        self.full_desc_edit.setReadOnly(not bool(text.strip()))

    def _on_deadline_type_changed(self, text: str) -> None:
        """Переключает режим полей дедлайна."""
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
        self._event_date_row.setVisible(is_event)
        if not is_event:
            self._event_date_edit.clear()


class DeadlineEditDialog(BaseTaskDialog):
    """Диалог редактирования дедлайна при восстановлении из архива.

    Назначение:
        Read-only заголовок + combo типа дедлайна + DeadlineFieldsWidget.

    Роль в программе:
        Открывается из PlannerArchiveWindow. Наследник BaseTaskDialog.
    """

    def __init__(self, parent=None, task=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerArchiveWindow).
            task — PlannerTask для восстановления.
        """
        super().__init__(
            parent=parent,
            task=task,
            title="Восстановление дедлайна",
            bg_color=(70, 80, 90, 0.95),
            close_button=False,
            ok_cancel=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=420,
            height=280,
        )

    def _build_content(self, layout) -> None:
        """Заголовок + combo типа + поля дедлайна."""
        # Read-only заголовок задачи.
        layout.addWidget(LabelFactory.create_label(
            self, f"Задача: {self._task.title}",
            bg_color=(0, 0, 0, 0), text_color="#ffffff",
            alignment=Qt.AlignCenter, word_wrap=True,
            font_size=13, font_weight="bold",
        ))

        # Строка «Тип»: label + combo.
        type_row = QWidget()
        type_row_layout = QHBoxLayout(type_row)
        type_row_layout.setContentsMargins(0, 0, 0, 0)
        type_row_layout.setSpacing(6)
        type_row_layout.addWidget(LabelFactory.create_label(
            type_row, "Тип:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4", font_size=11,
        ))
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            type_row,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=(50, 60, 70, 0.95),
            border="1px solid #3a4556",
        )
        type_row_layout.addWidget(self.deadline_type_combo, 1)
        layout.addWidget(type_row)

        # Поля дедлайна.
        self._deadline_fields = DeadlineFieldsWidget(
            self,
            initial=self._task.deadline_datetime,
            mode="inclusive",
            field_bg=(50, 60, 70, 0.95),
            field_border="1px solid #3a4556",
        )
        layout.addWidget(self._deadline_fields)

        # Триггер переключения режима.
        self.deadline_type_combo.currentTextChanged.connect(
            lambda text: self._deadline_fields.set_mode(
                "inclusive" if text == "До даты включительно" else "duration"
            )
        )

    def _collect_result(self):
        """Возвращает dict с deadline_datetime."""
        mode = (
            "inclusive"
            if self.deadline_type_combo.currentText() == "До даты включительно"
            else "duration"
        )
        return {
            "deadline_datetime": self._deadline_fields.get_deadline_data(mode),
        }


class PlannerRecurrenceEditDialog(BaseTaskDialog):
    """Диалог редактирования правила повторения при восстановлении.

    Назначение:
        Read-only заголовок + PlannerRecurrenceFieldsWidget.

    Роль в программе:
        Открывается из PlannerArchiveWindow. Наследник BaseTaskDialog.
    """

    def __init__(self, parent=None, task=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerArchiveWindow).
            task — PlannerTask для восстановления.
        """
        super().__init__(
            parent=parent,
            task=task,
            title="Восстановление регулярной задачи",
            bg_color=(70, 80, 90, 0.95),
            close_button=False,
            ok_cancel=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=420,
            height=300,
        )

    def _build_content(self, layout) -> None:
        """Заголовок + поля правила повторения."""
        layout.addWidget(LabelFactory.create_label(
            self, f"Задача: {self._task.title}",
            bg_color=(0, 0, 0, 0), text_color="#ffffff",
            alignment=Qt.AlignCenter, font_size=13,
            font_weight="bold", word_wrap=True,
        ))

        # Предзаполнение правила.
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
            field_bg=(50, 60, 70, 0.95),
            field_border="1px solid #3a4556",
            button_border="1px solid #6a7a8a",
        )
        layout.addWidget(self._recurrence_fields.rule_combo)
        layout.addWidget(self._recurrence_fields)

    def _collect_result(self):
        """Возвращает dict с recurrence_data."""
        return {
            "recurrence_data": self._recurrence_fields.get_recurrence_data(),
        }