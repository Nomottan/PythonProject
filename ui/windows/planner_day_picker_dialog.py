"""
Диалог выбора чисел месяца для правила «Определённые числа».

Обёртка над PlannerDayPickerWidget: сетка 7×5 с плитками 36×36,
превью выбранных чисел. Вопрос про 29/30/31 задаётся в _validate.
"""

from PySide6.QtWidgets import QDialog

from ui.widgets.planner_day_picker_widget import PlannerDayPickerWidget
from ui.base.base_edit_dialog import BaseEditDialog
from ui.windows.message_dialog import MessageDialog


class PlannerDayPickerDialog(BaseEditDialog):
    """Диалог выбора чисел месяца.

    Назначение:
        Позволяет выбрать числа 1–31. Если выбраны 29/30/31 — при «ОК»
        спрашивает, использовать ли последний день месяца, когда
        выбранного числа нет.

    Роль в программе:
        Открывается из PlannerRecurrenceFieldsWidget. Содержимое —
        PlannerDayPickerWidget; логика «последнего дня» — здесь.
    """

    def __init__(self, parent=None, selected=None):
        """Конструктор.

        Вход:
            parent — родитель.
            selected — список предвыбранных чисел.

        Роль: сохраняет предвыбранные числа, настраивает каркас
              через BaseEditDialog. Виджет создаётся в _build_content.
        """
        # Сохраняем до super(): нужно для _build_content.
        self._initial_selected = list(selected or [])
        # Виджет создаётся в _build_content.
        self._widget = None
        # Флаг «использовать последний день» — заполняется в _validate.
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

    # ---------- Наполнение ----------

    def _build_content(self, layout) -> None:
        """Добавляет PlannerDayPickerWidget в layout.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: создаёт виджет с предвыбранными числами, кладёт в layout.
        """
        self._widget = PlannerDayPickerWidget(
            self, selected=self._initial_selected,
        )
        layout.addWidget(self._widget)

    # ---------- Валидация ----------

    def _validate(self) -> bool:
        """Спрашивает про 29/30/31, если они выбраны.

        Выход: всегда True — вопрос не блокирует закрытие.
        Роль: если в выбранных есть 29, 30 или 31 — спрашивает
              пользователя, использовать ли последний день месяца
              в тех месяцах, где такого числа нет. Результат
              сохраняется в self._use_last_day.
        """
        selected = self._widget.get_selected()
        if any(d in (29, 30, 31) for d in selected):
            reply = MessageDialog.question(
                self,
                "В некоторых месяцах недостаточно дней. "
                "Выбирать последнюю дату в них?",
                title_text="Последний день",
                bg_color=(70, 80, 90),
            )
            self._use_last_day = (reply == QDialog.Accepted)
        return True

    # ---------- Публичный API ----------

    def get_selected(self) -> list:
        """Возвращает отсортированный список выбранных чисел."""
        return self._widget.get_selected()

    def get_use_last_day(self) -> bool:
        """Возвращает флаг «использовать последний день»."""
        return self._use_last_day