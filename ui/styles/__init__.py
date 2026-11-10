"""
Пакет ui.styles — единая точка стилизации виджетов.

Реэкспортирует публичные классы:
    ColorCalculator — работа с цветами.
    IconRenderer — рисование иконок через QPainter.
    SelectorBuilder — сборка QSS-селекторов.
    QssBuilder — сборка QSS-блоков.
    ScrollbarStyle — стиль скроллбаров.
    WindowStyle — стиль окон.
    WidgetStyle — фасад: методы apply_* для виджетов.

Использование:
    from ui.styles import WidgetStyle, ColorCalculator

Пакет не зависит от ui.factories и ui.widgets — обратной
зависимости быть не должно, чтобы избежать циклов.
"""

from .colors import ColorCalculator
from .icon_renderer import IconRenderer
from .selectors import SelectorBuilder
from .qss import QssBuilder
from .scrollbar import ScrollbarStyle
from .window import WindowStyle
from .widget_style import WidgetStyle
from .bg_resolver import BackgroundResolver

__all__ = [
    "ColorCalculator",
    "IconRenderer",
    "SelectorBuilder",
    "QssBuilder",
    "ScrollbarStyle",
    "WindowStyle",
    "WidgetStyle",
    "BackgroundResolver",
]