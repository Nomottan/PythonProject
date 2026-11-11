"""Вычисление размеров текста для стилевых расчётов."""

from PySide6.QtGui import QFont, QFontMetrics


class SizingCalculator:
    """Калькулятор размеров для стилей."""

    @staticmethod
    def get_text_height(widget, font_size=None) -> int:
        """Возвращает высоту текста с учётом QSS-шрифта.

        Вход:
            widget — QWidget, чей шрифт используется как базовый.
            font_size — размер шрифта в пикселях (как в QSS font-size).
                        Если None — используется текущий шрифт виджета.

        Выход: высота текста (int).

        Роль:
            Единая точка вычисления высоты текста для стилевых
            расчётов. Если font_size задан, создаётся QFont с
            pixelSize и вычисляется QFontMetrics.height(). Если
            нет — QFontMetrics(widget.font()).height().
        """
        if font_size is not None:
            f = QFont(widget.font())
            f.setPixelSize(font_size)
            return QFontMetrics(f).height()
        return QFontMetrics(widget.font()).height()

    @staticmethod
    def calculate_icon_size(widget, font_size=None) -> int:
        """Вычисляет оптимальный размер иконки для виджета.

        Вход:
            widget — QWidget, для которого вычисляется размер.
            font_size — опциональный размер шрифта (px), если он
                        задаётся через QSS.

        Выход: размер иконки (int).
        """
        min_dim = min(widget.width(), widget.height())
        if min_dim <= 0:
            return 16

        base = int(min_dim * 0.8)

        has_text = (
                hasattr(widget, 'text')
                and callable(widget.text)
                and bool(widget.text())
        )

        if has_text:
            # Передаём font_size, если он известен
            text_height = SizingCalculator.get_text_height(
                widget, font_size=font_size
            )
            max_size = int(text_height * 1.2)
            size = min(base, max_size)
        else:
            size = base

        if (min_dim % 2) != (size % 2):
            size -= 1

        return max(4, size)