"""
Фабрика виджетов панели фильтров.

Содержит FilterFactory — единая точка создания тристейт-чекбокса,
мастер-кнопки, скролл-контейнера значений и самой панели FilterPanel.
"""

from PySide6.QtCore import Qt
from ui.factories.button_factory import ButtonFactory
from ui.factories.checkbox_factory import CheckBoxFactory
from ui.factories.widget_factory import ListWidgetFactory


class FilterFactory:
    """Фабрика виджетов панели фильтров."""

    # ---------- Панель ----------

    @staticmethod
    def create_filter_panel(parent, field_defs, get_source, bg_color):
        """Создаёт FilterPanel.

        Ленивый импорт FilterPanel для разрыва цикла
        (factories -> filter_factory -> filter_panel -> factories).
        """
        from ui.widgets.filter_panel import FilterPanel
        return FilterPanel(parent, field_defs, get_source, bg_color)

    # ---------- Кнопки ----------

    @staticmethod
    def create_master_button(parent, text, bg_color, object_name=None):
        """Создаёт мастер-кнопку «Фильтры» (checkable)."""
        return ButtonFactory.create_button(
            parent, text, bg_color,
            checkable=True, object_name=object_name,
            padding="8px 16px",
        )

    # ---------- Чекбоксы ----------

    @staticmethod
    def create_tristate_checkbox(parent, bg_color, text=""):
        """Создаёт тристейт-чекбокс с текстом."""
        return CheckBoxFactory.create_checkbox(
            parent, text=text, bg_color=bg_color,
            square_size=20, position="left",
            tristate=True, check_state=Qt.Unchecked,
        )

    @staticmethod
    def create_value_checkbox(parent, text, checked, bg_color):
        """Создаёт обычный чекбокс значения категории."""
        return CheckBoxFactory.create_checkbox(
            parent, text, checked=checked, bg_color=bg_color,
        )

    # ---------- Контейнер значений ----------

    @staticmethod
    def create_values_scroll(parent, bg_color) -> tuple:
        """Создаёт скролл-контейнер для чекбоксов значений."""
        return ListWidgetFactory.create_scroll_container(
            parent, spacing=2, bg_color=bg_color, rounded=False,
        )