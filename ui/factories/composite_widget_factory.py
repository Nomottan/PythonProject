"""
Фабрика составных виджетов.

Содержит CompositeWidgetFactory — создаёт виджеты, собранные из
нескольких элементов или требующие локальных зависимостей
(например, PlannerRecurrenceFieldsWidget, PlannerDayPickerDialog).
Не знает про TaskPriority — выбор приоритетных стилей делает
вызывающий код.
"""

from PySide6.QtWidgets import QPushButton

from ui.factories.factories import (
    BaseWidgetFactory, DeadlineTaskButton, InstanceTaskButton,
)


class CompositeWidgetFactory(BaseWidgetFactory):
    """Фабрика составных виджетов.

    Назначение:
        Создаёт виджеты-слоты для мини-планировщика (с полосой,
        с прогрессбаром, обычные кнопки), а также составные
        виджеты (поля правила повторения, диалог выбора чисел).
        Не знает про TaskPriority — конкретный стиль выбирает
        вызывающий код.

    Роль в программе:
        Заменяет методы ButtonFactory.create_task_slot_button,
        create_deadline_button, create_recurrence_fields, create_day_picker,
        которые смешивали общий код фабрики с planner-спецификой.

    Публичный API:
        create_striped_slot(parent, stripe_color) — InstanceTaskButton
                                                    с цветной полосой.
        create_progress_slot(parent) — DeadlineTaskButton.
        create_simple_slot(parent) — QPushButton.
        create_recurrence_fields(parent, ...) — PlannerRecurrenceFieldsWidget.
        create_day_picker(parent, selected) — PlannerDayPickerDialog.
    """

    # ---------- Слоты мини-планировщика ----------

    @staticmethod
    def create_striped_slot(parent, stripe_color=(80, 160, 220, 1.0)):
        """Создаёт слот с цветной полосой слева.

        Вход:
            parent — родитель.
            stripe_color — цвет полосы. По умолчанию голубой
                           (INSTANCE). Для события вызывающий код
                           передаёт жёлтый (240, 240, 40).

        Выход: InstanceTaskButton.
        Роль: используется для экземпляров регулярных задач и событий.
        """
        return InstanceTaskButton(parent, stripe_color=stripe_color)

    @staticmethod
    def create_progress_slot(parent):
        """Создаёт слот с прогрессбаром.

        Вход: parent — родитель.
        Выход: DeadlineTaskButton.
        Роль: используется для дедлайн-задач.
        """
        return DeadlineTaskButton(parent)

    @staticmethod
    def create_simple_slot(parent):
        """Создаёт простую кнопку-слот без стиля.

        Вход: parent — родитель.
        Выход: QPushButton.
        Роль: используется для обычных задач. Стиль
              (полоса, фон) задаёт вызывающий код.
        """
        return QPushButton(parent)

    # ---------- Составные виджеты planner ----------

    @staticmethod
    def create_recurrence_fields(parent, initial_data=None,
                                 field_bg=None, field_border=None,
                                 button_border=None):
        """Создаёт виджет полей правила повторения.

        Вход:
            parent — родитель.
            initial_data — dict для предзаполнения.
            field_bg, field_border — цвета полей. None — дефолтные.
            button_border — рамка кнопки «Выбрать числа».

        Выход: PlannerRecurrenceFieldsWidget.

        Роль: локальный импорт — виджет живёт в ui/widgets и
              не должен тянуться в шапку фабрики (иначе цикл:
              planner_recurrence_fields_widget импортирует
              CompositeWidgetFactory).
        """
        from ui.widgets.planner_recurrence_fields_widget import (
            PlannerRecurrenceFieldsWidget,
        )
        return PlannerRecurrenceFieldsWidget(
            parent, initial_data,
            field_bg=field_bg,
            field_border=field_border,
            button_border=button_border,
        )

    @staticmethod
    def create_day_picker(parent, selected=None):
        """Создаёт диалог выбора чисел месяца.

        Вход: parent — родитель; selected — список предвыбранных чисел.
        Выход: PlannerDayPickerDialog.

        Роль: локальный импорт — диалог живёт в ui/windows и тянет
              за собой MessageDialog; в шапку фабрики его не тянем.
        """
        from ui.windows.planner_day_picker_dialog import PlannerDayPickerDialog
        return PlannerDayPickerDialog(parent, selected)