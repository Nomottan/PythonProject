"""
Виджет полей правила повторения регулярной задачи.

Используется в NewTaskDialog и PlannerRecurrenceEditDialog —
чтобы не дублировать логику ввода. Внутри сам переключает блоки
при смене правила, эмитит data_changed при любом изменении.
"""

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Signal

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
)


class PlannerRecurrenceFieldsWidget(QWidget):
    """Поля правила повторения: «Каждые N дней» / «Дни недели» / «Числа».

    Сигналы:
        data_changed() — любое изменение в любом блоке.

    Роль в программе:
        Переиспользуемый виджет для двух окон. Внутри — три
        взаимозаменяемых блока; какой показан, зависит от rule_combo.
        Кнопка «Выбрать числа» открывает PlannerDayPickerDialog,
        который сам решает вопрос про 29/30/31.
    """

    data_changed = Signal()

    # Цвета полей — те же, что у DeadlineFieldsWidget.
    FIELD_BG = (85, 60, 42, 0.9)
    FIELD_BORDER = "1px solid #6b4a33"

    def __init__(self, parent=None, initial_data: Optional[dict] = None):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            initial_data — dict правила повторения для предзаполнения.
                           Ключи: type, value, weekdays, monthdays, use_last_day.
        """
        super().__init__(parent)
        self._selected_monthdays: list = []
        self._use_last_day: bool = False
        self._build_ui()
        if initial_data:
            self.set_data(initial_data)

    # ---------- Публичный API ----------

    def get_recurrence_data(self) -> Optional[dict]:
        """Возвращает правило повторения.

        Выход: dict с ключами type/value/weekdays/monthdays/use_last_day
               или None, если правило невалидно (например, ни одного
               дня недели не отмечено).
        """
        rule = self._rule_combo.currentText()
        if rule == "Каждые N дней":
            return {"type": "every_n_days", "value": self._days_spin.value()}
        if rule == "Дни недели":
            weekdays = [
                i for i, cb in enumerate(self._weekday_boxes) if cb.isChecked()
            ]
            if not weekdays:
                return None
            return {"type": "weekdays", "weekdays": weekdays}
        if rule == "Определённые числа":
            if not self._selected_monthdays:
                return None
            return {
                "type": "monthdays",
                "monthdays": sorted(self._selected_monthdays),
                "use_last_day": self._use_last_day,
            }
        return None

    def set_data(self, data: dict) -> None:
        """Предзаполняет виджет из dict правила повторения.

        Вход: data — dict с ключами type/value/weekdays/monthdays/use_last_day.
        Роль: используется в PlannerRecurrenceEditDialog при открытии.
        """
        rec_type = data.get("type")
        if rec_type == "every_n_days":
            self._rule_combo.setCurrentText("Каждые N дней")
            self._days_spin.setValue(data.get("value") or 1)
        elif rec_type == "weekdays":
            self._rule_combo.setCurrentText("Дни недели")
            weekdays = data.get("weekdays") or []
            for i, cb in enumerate(self._weekday_boxes):
                cb.setChecked(i in weekdays)
        elif rec_type == "monthdays":
            self._rule_combo.setCurrentText("Определённые числа")
            self._selected_monthdays = list(data.get("monthdays") or [])
            self._use_last_day = bool(data.get("use_last_day", False))
            self._monthdays_label.setText(self._format_days_preview())

    # ---------- Сборка ----------

    def _build_ui(self) -> None:
        """Собирает UI: combo правила + три взаимозаменяемых блока."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Combo «Правило».
        self._rule_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["Каждые N дней", "Дни недели", "Определённые числа"],
            current_index=0,
            bg_color=self.FIELD_BG,
            border=self.FIELD_BORDER,
        )
        layout.addWidget(self._rule_combo)

        # «Каждые N дней».
        self._days_widget = QWidget()
        days_l = QHBoxLayout(self._days_widget)
        days_l.setContentsMargins(0, 0, 0, 0)
        days_l.setSpacing(4)
        self._days_spin = InputWidgetFactory.create_spin_box(
            self._days_widget, min_value=1, max_value=9999, value=1,
            bg_color=self.FIELD_BG, border=self.FIELD_BORDER,
            show_buttons=False,
        )
        days_l.addWidget(self._label("Каждые"))
        days_l.addWidget(self._days_spin)
        days_l.addWidget(self._label("дней"))
        days_l.addStretch()
        layout.addWidget(self._days_widget)

        # «Дни недели».
        self._weekdays_widget = QWidget()
        wd_l = QHBoxLayout(self._weekdays_widget)
        wd_l.setContentsMargins(0, 0, 0, 0)
        wd_l.setSpacing(4)
        self._weekday_boxes = []
        for day_name in ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]:
            cb = InputWidgetFactory.create_checkbox(
                self._weekdays_widget, day_name, checked=False,
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            )
            cb.stateChanged.connect(lambda _: self.data_changed.emit())
            self._weekday_boxes.append(cb)
            wd_l.addWidget(cb)
        wd_l.addStretch()
        layout.addWidget(self._weekdays_widget)

        # «Определённые числа».
        self._monthdays_widget = QWidget()
        md_l = QHBoxLayout(self._monthdays_widget)
        md_l.setContentsMargins(0, 0, 0, 0)
        md_l.setSpacing(4)
        self._select_days_btn = ButtonFactory.create_button(
            self._monthdays_widget, "Выбрать числа",
            bg_color=(80, 100, 130), padding="6px 12px",
        )
        self._select_days_btn.clicked.connect(self._on_select_monthdays)
        md_l.addWidget(self._select_days_btn)
        self._monthdays_label = LabelFactory.create_label(
            self._monthdays_widget, "",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4", font_size=11,
        )
        md_l.addWidget(self._monthdays_label)
        md_l.addStretch()
        layout.addWidget(self._monthdays_widget)

        # Триггеры.
        self._rule_combo.currentTextChanged.connect(self._on_rule_changed)
        self._days_spin.valueChanged.connect(lambda _: self.data_changed.emit())

        self._on_rule_changed(self._rule_combo.currentText())

    def _label(self, text: str):
        """Быстрый хелпер для лейблов полей."""
        return LabelFactory.create_label(
            self, text, bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4", font_size=11,
        )

    # ---------- Триггеры ----------

    def _on_rule_changed(self, text: str) -> None:
        """Переключает видимость блоков правила."""
        self._days_widget.setVisible(text == "Каждые N дней")
        self._weekdays_widget.setVisible(text == "Дни недели")
        self._monthdays_widget.setVisible(text == "Определённые числа")
        self.data_changed.emit()

    def _on_select_monthdays(self) -> None:
        """Открывает PlannerDayPickerDialog для выбора чисел месяца.

        Вопрос про 29/30/31 задаётся внутри самого диалога — здесь
        только сохраняем результат.
        """
        dialog = ButtonFactory.create_day_picker(self, self._selected_monthdays)
        if dialog.exec():
            self._selected_monthdays = dialog.get_selected()
            self._use_last_day = dialog.get_use_last_day()
            self._monthdays_label.setText(self._format_days_preview())
            self.data_changed.emit()

    def _format_days_preview(self) -> str:
        """Превью выбранных чисел месяца."""
        if not self._selected_monthdays:
            return "—"
        return ", ".join(str(d) for d in sorted(self._selected_monthdays))