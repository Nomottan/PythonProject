"""
Адаптеры для QSS.

Содержит классы-адаптеры, которые связывают чистые рендереры
(например, IconRenderer) со сборщиками QSS (QssBuilder).
Адаптеры берут на себя роль «переводчика»: они знают, как
правильно встроить результат рендеринга в синтаксис QSS,
не нарушая чистоту и независимость исходных модулей.
"""

from .icon_renderer import IconRenderer
from .qss import QssBuilder


class IconAdapter:
    """Адаптер для встраивания иконок в QSS-правила.

    Роль:
        Связующее звено между IconRenderer и QssBuilder.
        Позволяет WidgetStyle собирать стили для псевдоэлементов
        (стрелки выпадающих списков, чекбоксы) без ручной
        склейки Data URI и QSS-свойств.
    """

    @staticmethod
    def arrow_rule(selector: str, direction: str, widget,
                   bg_color=None, size: int = 12,
                   margin_right: str = "1px") -> str:
        """Собирает QSS для стрелки (например, ::down-arrow).

        Вход:
            selector — селектор (например, "QComboBox::down-arrow").
            direction — направление ("up", "down", "left", "right").
            widget — виджет для резолва цвета и размера текста.
            bg_color — цвет стрелки. None → резолвится от виджета.
            size — размер стороны в px.
            margin_right — отступ справа.

        Выход: QSS-строка.
        """
        data_uri = IconRenderer.make_arrow_data_uri(
            direction, widget, bg_color=bg_color, size=size
        )
        return QssBuilder.image_rule(
            selector, data_uri, width=size, height=size,
            margin_right=margin_right
        )