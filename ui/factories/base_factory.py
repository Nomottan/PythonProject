"""
Базовый класс для фабрик виджетов.

Тонкая прослойка совместимости. Вся стилизация переехала в
ui.styles. Публичные статические методы BaseWidgetFactory
делегируют в ColorCalculator и WidgetStyle — существующие
вызовы BaseWidgetFactory.color_to_str(...) продолжают работать.
"""

from ui.styles.colors import ColorCalculator
from ui.styles.widget_style import WidgetStyle
from ui.styles.window import WindowStyle

class BaseWidgetFactory:
    """Тонкая прослойка совместимости над ui.styles.

    Назначение:
        Сохранить старый публичный API BaseWidgetFactory без
        изменения вызывающего кода. Внутри — делегирование в
        ColorCalculator и WidgetStyle.

    Роль в программе:
        Наследники (ButtonFactory, LabelFactory, InputWidgetFactory,
        ListWidgetFactory, StatusLogFactory, CompositeWidgetFactory)
        продолжают вызывать BaseWidgetFactory.calc_hover_color(...)
        и т.п. Реализация — в ui.styles.
    """

    # Стилевые методы — делегируют в ColorCalculator.
    color_to_str = staticmethod(ColorCalculator.to_str)
    calc_hover_color = staticmethod(ColorCalculator.hover)
    calc_pressed_color = staticmethod(ColorCalculator.pressed)
    calc_disabled_color = staticmethod(ColorCalculator.disabled)
    calc_text_color = staticmethod(ColorCalculator.text_for)

    # Общие настройки — делегируют в WidgetStyle.
    apply_common_settings = staticmethod(WidgetStyle.apply_common)

    @staticmethod
    def resolve_element_bg(parent, bg_color=None) -> tuple:
        """Резолвит фон элемента фабрик от родителя.

        Вход:
            parent — QWidget-родитель или None.
            bg_color — явный цвет или None. Явный — возвращается
                       как есть без изменений.

        Выход:
            Кортеж 3 или 4 элементов — производный цвет.

        Роль:
            Единая точка резолва фона элементов фабрик (кнопки,
            line-edit и т. п.). Фабрики вызывают без наследования —
            BaseWidgetFactory.resolve_element_bg(parent, bg_color).

            Логика:
                1. Явный bg_color → как есть.
                2. parent_bg = WindowStyle.resolve_parent_bg(
                       parent, (63, 63, 63)).
                3. Если parent_bg полностью прозрачен (alpha == 0) —
                   fallback (63, 63, 63, 1.0).
                4. ColorCalculator.element_bg_for(parent_bg) —
                   производный по формуле из colors.py.

        REPLACE: новый метод — основа для bg_color=None в
        ButtonFactory и InputWidgetFactory.
        """
        if bg_color is not None:
            return bg_color

        parent_bg = WindowStyle.resolve_parent_bg(parent, (63, 63, 63))

        if (isinstance(parent_bg, (tuple, list))
                and len(parent_bg) >= 4
                and float(parent_bg[3]) == 0.0):
            parent_bg = (63, 63, 63, 1.0)

        return ColorCalculator.element_bg_for(parent_bg)