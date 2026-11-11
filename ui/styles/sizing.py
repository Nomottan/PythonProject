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