"""
Пакет ui.styles — единая точка стилизации виджетов.

Реэкспортирует публичные классы:
    ColorCalculator — работа с цветами.
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
from .selectors import SelectorBuilder
from .qss import QssBuilder
from .scrollbar import ScrollbarStyle
from .window import WindowStyle
from .widget_style import WidgetStyle

__all__ = [
    "ColorCalculator",
    "SelectorBuilder",
    "QssBuilder",
    "ScrollbarStyle",
    "WindowStyle",
    "WidgetStyle",
]