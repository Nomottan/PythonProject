"""
Фабрика составных виджетов.

Содержит CompositeWidgetFactory — создаёт виджеты-слоты для
мини-планировщика (три варианта) и составные виджеты
(поля правила повторения, диалог выбора чисел).
Не знает про TaskPriority — конкретный цвет полосы выбирает
вызывающий код.
"""

from ui.factories.base_factory import BaseWidgetFactory


class CompositeWidgetFactory(BaseWidgetFactory):
    """Фабрика составных виджетов.

    Назначение:
        Создаёт виджеты-слоты для мини-планировщика (три варианта),
        а также составные виджеты (поля правила повторения,
        диалог выбора чисел). Не знает про TaskPriority —
        конкретный стиль выбирает вызывающий код.

    Роль в программе:
        Заменяет методы ButtonFactory.create_task_slot_button,
        create_deadline_button, create_recurrence_fields,
        create_day_picker, которые смешивали общий код фабрики
        с planner-спецификой.

    Публичный API:
        create_progress_slot(parent) — DeadlineTaskButton.
        create_striped_slot(parent, stripe_color) — InstanceTaskButton.
        create_event_slot(parent) — EventTaskButton.
        create_simple_slot(parent, stripe_color) — SimpleTaskButton.
        create_recurrence_fields(parent, ...) — PlannerRecurrenceFieldsWidget.
        create_day_picker(parent, selected) — PlannerDayPickerDialog.
    """

    # ---------- Слоты мини-планировщика ----------

    @staticmethod
    def create_striped_slot(parent, stripe_color=(80, 160, 220, 1.0), theme_key=None, main_bg=(50, 50, 50)):
        """Создаёт слот экземпляра регулярной задачи.

        Вход:
            parent — родитель.
            stripe_color — цвет полосы. По умолчанию голубой
                           (INSTANCE).
            theme_key — объект ThemeKey (или None).
            main_bg — цвет фона главного окна.

        Выход: InstanceTaskButton.
        ...
        """
        from ui.widgets.planner_slot_buttons import InstanceTaskButton
        return InstanceTaskButton(parent, stripe_color=stripe_color, theme_key=theme_key, main_bg=main_bg)

    @staticmethod
    def create_progress_slot(parent, theme_key=None, main_bg=(50, 50, 50)):
        """Создаёт слот с прогрессбаром.

        Вход:
            parent — родитель.
            theme_key — объект ThemeKey (или None).
            main_bg — цвет фона главного окна.
        Выход: DeadlineTaskButton.
        Роль: используется для дедлайн-задач.
        """
        from ui.widgets.planner_slot_buttons import DeadlineTaskButton
        return DeadlineTaskButton(parent, theme_key=theme_key, main_bg=main_bg)

    @staticmethod
    def create_event_slot(parent, theme_key=None, main_bg=(50, 50, 50)):
        """Создаёт слот события.

        Вход:
            parent — родитель.
            theme_key — объект ThemeKey (или None).
            main_bg — цвет фона главного окна.
        Выход: EventTaskButton.
        Роль: используется для задач с task_type == EVENT.
              Жёлтая полоса — чтобы событие визуально выделялось.
        """
        from ui.widgets.planner_slot_buttons import EventTaskButton
        return EventTaskButton(parent, theme_key=theme_key, main_bg=main_bg)

    @staticmethod
    def create_simple_slot(parent, stripe_color=(80, 160, 220, 1.0), theme_key=None, main_bg=(50, 50, 50)):
        """Создаёт слот обычной задачи.

        Вход:
            parent — родитель.
            stripe_color — цвет полосы слева. Обычно — цвет
                           приоритета (LOW/MEDIUM/HIGH).
            theme_key — объект ThemeKey (или None).
            main_bg — цвет фона главного окна.

        Выход: SimpleTaskButton.

        Роль: используется для задач без особого типа
              (не дедлайн, не экземпляр, не событие). Заменяет
              прежний QPushButton с ручной стилизацией — теперь
              единая база с остальными слотами.
        """
        from ui.widgets.planner_slot_buttons import SimpleTaskButton
        return SimpleTaskButton(parent, stripe_color=stripe_color, theme_key=theme_key, main_bg=main_bg)

    # ---------- Составные виджеты planner ----------

    @staticmethod
    def create_recurrence_fields(parent, initial_data=None,
                                 field_bg=None, field_border=None,
                                 button_border=None, label_bg=None):
        """Создаёт виджет полей правила повторения.

        Вход:
            parent — родитель.
            initial_data — dict для предзаполнения.
            field_bg, field_border — цвета полей. None — дефолтные.
            button_border — рамка кнопки «Выбрать числа».
            label_bg — цвет фона лейблов (None — прозрачный).

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
            label_bg=label_bg,
        )

    @staticmethod
    def create_day_picker(parent, selected=None):
        """Создаёт диалог выбора чисел месяца.

        Вход: parent — родитель; selected — список предвыбранных чисел.
        Выход: PlannerDayPickerDialog.

        Роль: локальный импорт — диалог живёт в ui/windows и тянет
              за собой MessageDialog; в шапку фабрики его не тянем.
        """
        from ui.windows.planner_task_dialogs import PlannerDayPickerDialog
        return PlannerDayPickerDialog(parent, selected)