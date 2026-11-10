"""
Фабрика виджетов панели фильтров.

Содержит FilterFactory — единая точка создания тристейт-чекбокса,
мастер-кнопки, кнопок категории, скролл-контейнера значений и
самой панели FilterPanel.

Роль в программе:
    Изолирует FilterPanel/FilterCategory от прямых вызовов
    ButtonFactory / CheckBoxFactory / ListWidgetFactory.
    Логика фильтра — в utils/filter_utils.py; панель — в
    ui/widgets/filter_panel.py. Фабрика только собирает виджеты.
"""

from PySide6.QtCore import Qt

from ui.factories.button_factory import ButtonFactory
from ui.factories.checkbox_factory import CheckBoxFactory
from ui.factories.widget_factory import ListWidgetFactory
from ui.widgets.filter_panel import FilterPanel, FilterCategory

class FilterFactory:
    """Фабрика виджетов панели фильтров.

    Роль:
        Все методы — @staticmethod. Собирают панель фильтров из
        готовых фабрик. Панель и категории уже определены в
        ui.widgets.filter_panel; фабрика только передаёт им
        параметры.
    """

    # ---------- Панель и категория ----------

    @staticmethod
    def create_filter_panel(parent, field_defs, get_source,
                            bg_color) -> FilterPanel:
        """Создаёт FilterPanel.

        Вход:
            parent — родительский виджет.
            field_defs — list[FieldDef].
            get_source — Callable[[], list] — источник объектов.
            bg_color — фон панели (кортеж).

        Выход: FilterPanel.
        """
        return FilterPanel(parent, field_defs, get_source, bg_color)

    @staticmethod
    def create_category(parent, field_def, bg_color) -> FilterCategory:
        """Создаёт FilterCategory.

        Вход:
            parent — родительский виджет.
            field_def — FieldDef.
            bg_color — фон панели (кортеж).

        Выход: FilterCategory.
        """
        return FilterCategory(parent, field_def, bg_color)

    # ---------- Кнопки ----------

    @staticmethod
    def create_master_button(parent, text, bg_color,
                             object_name=None):
        """Создаёт мастер-кнопку «Фильтры» (checkable).

        Вход:
            parent — родитель.
            text — подпись.
            bg_color — фон.
            object_name — опциональный objectName.

        Выход: QPushButton с checkable=True.
        """
        return ButtonFactory.create_button(
            parent, text, bg_color,
            checkable=True, object_name=object_name,
            padding="8px 16px",
        )

    @staticmethod
    def create_select_all_button(parent, bg_color):
        """Создаёт кнопку «Выбрать всё»."""
        return ButtonFactory.create_button(
            parent, "Выбрать всё", bg_color, padding="4px 10px",
        )

    @staticmethod
    def create_clear_all_button(parent, bg_color):
        """Создаёт кнопку «Очистить всё»."""
        return ButtonFactory.create_button(
            parent, "Очистить всё", bg_color, padding="4px 10px",
        )

    # ---------- Чекбоксы ----------

    @staticmethod
    def create_tristate_checkbox(parent, bg_color, text=""):
        """Создаёт тристейт-чекбокс с текстом.

        Вход:
            parent — родитель.
            bg_color — фон.
            text — подпись (по умолчанию пустая).

        Выход: CheckBox с setTristate(True), начальное состояние
        Unchecked.

        Роль: размер квадратика фиксирован (20), а сам виджет
              растягивается под текст — поэтому fixed_size не
              используется.
        """
        return CheckBoxFactory.create_checkbox(
            parent, text=text, bg_color=bg_color,
            square_size=20, position="left",
            tristate=True, check_state=Qt.Unchecked,
        )

    @staticmethod
    def create_value_checkbox(parent, text, checked, bg_color):
        """Создаёт обычный чекбокс значения категории.

        Вход:
            parent — родитель.
            text — подпись (строка значения).
            checked — начальное состояние.
            bg_color — фон.

        Выход: CheckBox.
        """
        return CheckBoxFactory.create_checkbox(
            parent, text, checked=checked, bg_color=bg_color,
        )

    # ---------- Контейнер значений ----------

    @staticmethod
    def create_values_scroll(parent, bg_color) -> tuple:
        """Создаёт скролл-контейнер для чекбоксов значений.

        Вход:
            parent — родитель.
            bg_color — фон.

        Выход:
            (scroll_area, content_widget, content_layout) — как
            возвращает ListWidgetFactory.create_scroll_container.
            rounded=False — прямые углы, вписывается в панель.
        """
        return ListWidgetFactory.create_scroll_container(
            parent, spacing=2, bg_color=bg_color, rounded=False,
        )