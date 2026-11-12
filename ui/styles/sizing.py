"""Вычисление размеров текста для стилевых расчётов."""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QCursor


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


class GeometryCalculator:
    """Калькулятор геометрии и координат."""

    @staticmethod
    def clamp_to_screen(x: int, y: int, width: int, height: int, screen=None) -> tuple[int, int]:
        """Ограничивает координаты виджета доступной областью экрана.

        Вход:
            x, y — желаемые координаты левого верхнего угла.
            width, height — размеры виджета.
            screen — QScreen. Если None, берется экран под курсором
                     или основной.

        Выход:
            (new_x, new_y) — скорректированные координаты.

        Роль:
            Единая точка ограничения координат (клампинга) для
            выпадающих списков, тултипов и прочих всплывающих окон,
            чтобы они не уходили за пределы монитора.
        """
        if screen is None:
            screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QGuiApplication.primaryScreen()

        if screen is not None:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(x, geo.right() - width))
            y = max(geo.top(), min(y, geo.bottom() - height))

        return x, y

    @staticmethod
    def calculate_popup_position(btn_global: QPoint, popup_w: int, popup_h: int, trigger_h: int = 0, trigger_w: int = 0,
                                 screen=None) -> tuple[int, int, str]:
        """Вычисляет позицию выпадающего списка и направление открытия."""
        x, y = btn_global.x(), btn_global.y()
        direction = "down"

        if screen is None:
            screen = QGuiApplication.screenAt(btn_global) or QGuiApplication.primaryScreen()

        if screen:
            geo = screen.availableGeometry()

            # 1. Вертикальное позиционирование
            if y + popup_h > geo.bottom():
                # Открываем вверх
                y = btn_global.y() - trigger_h - popup_h
                direction = "up"

            # 2. Горизонтальное позиционирование
            if x + popup_w > geo.right():
                # Не влезает вправо — открываем влево от кнопки
                x = btn_global.x() - popup_w + trigger_w
                # Если открываем влево, стрелка должна смотреть влево
                direction = "left"
            elif x < geo.left():
                # Не влезает влево — прижимаем к левому краю (открываем вправо)
                x = geo.left()
                direction = "right"

        clamped_x, clamped_y = GeometryCalculator.clamp_to_screen(x, y, popup_w, popup_h, screen)
        return clamped_x, clamped_y, direction