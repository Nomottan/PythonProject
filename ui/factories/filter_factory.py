"""
Фабрика виджетов панели фильтров.

Содержит FilterFactory — единая точка создания тристейт-чекбокса
с SVG-иконками, мастер-кнопки, кнопок категории, скролл-контейнера
значений и самой панели FilterPanel.

Роль в программе:
    Изолирует FilterPanel/FilterCategory от прямых вызовов
    ButtonFactory / InputWidgetFactory / ListWidgetFactory.
    Логика фильтра — в utils/filter_utils.py; панель — в
    ui/widgets/filter_panel.py. Фабрика только собирает виджеты.
"""

from pathlib import Path

from PySide6.QtCore import Qt

from ui.factories.button_factory import ButtonFactory
from ui.factories.input_factory import InputWidgetFactory
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

    _ICONS_DIR = Path(__file__).parent.parent / "styles" / "icons"

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
    def create_tristate_checkbox(parent, bg_color):
        """Создаёт тристейт-чекбокс с SVG-иконками.

        Вход:
            parent — родитель.
            bg_color — фон.

        Выход: QCheckBox с setTristate(True), начальное состояние
        Unchecked. Иконки — tristate_empty / tristate_partial /
        tristate_full из ui/styles/icons/.

        Роль: иконки пробрасываются через icon_paths, который
              поддержан InputWidgetFactory.create_checkbox и
              WidgetStyle.apply_checkbox.
        """
        icon_paths = {
            "unchecked": (
                FilterFactory._ICONS_DIR / "tristate_empty.svg"
            ).as_posix(),
            "indeterminate": (
                FilterFactory._ICONS_DIR / "tristate_partial.svg"
            ).as_posix(),
            "checked": (
                FilterFactory._ICONS_DIR / "tristate_full.svg"
            ).as_posix(),
        }
        cb = InputWidgetFactory.create_checkbox(
            parent, text="", bg_color=bg_color,
            fixed_size=(20, 20),
            icon_paths=icon_paths,
        )
        cb.setTristate(True)
        cb.setCheckState(Qt.Unchecked)
        return cb

    @staticmethod
    def create_value_checkbox(parent, text, checked, bg_color):
        """Создаёт обычный чекбокс значения категории.

        Вход:
            parent — родитель.
            text — подпись (строка значения).
            checked — начальное состояние.
            bg_color — фон.

        Выход: QCheckBox.
        """
        return InputWidgetFactory.create_checkbox(
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