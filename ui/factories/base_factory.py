"""
Базовый класс для фабрик виджетов.

Тонкая прослойка совместимости. Вся стилизация переехала в
ui.styles. Публичные статические методы BaseWidgetFactory
делегируют в ColorCalculator и WidgetStyle — существующие
вызовы BaseWidgetFactory.color_to_str(...) продолжают работать.
"""

from ui.styles.colors import ColorCalculator
from ui.styles.widget_style import WidgetStyle


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
