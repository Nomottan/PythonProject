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

    # Смещения для каждого направления: (dx, dy, direction_name)

    @staticmethod
    def clamp_to_screen(x: int, y: int, width: int, height: int, screen=None) -> tuple[int, int]:
        """Ограничивает координаты виджета доступной областью экрана."""
        target_screen = screen or QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

        if target_screen is not None:
            geo = target_screen.availableGeometry()
            x = max(geo.left(), min(x, geo.right() - width))
            y = max(geo.top(), min(y, geo.bottom() - height))

        return x, y

    @staticmethod
    def calculate_popup_position(trigger_global: QPoint, popup_w: int, popup_h: int, trigger_h: int = 0,
                                 trigger_w: int = 0, screen=None, preferred_dir: str = "auto") -> tuple[int, int, str]:
        """Вычисляет позицию выпадающего списка и направление открытия."""
        x, y = trigger_global.x(), trigger_global.y()
        if preferred_dir == "auto":
            preferred_dir = "down"
        if screen is None:
            screen = QGuiApplication.screenAt(trigger_global) or QGuiApplication.primaryScreen()

        if screen:
            geo = screen.availableGeometry()
            _BASE = {"right": (trigger_w, 0),
                     "left": (-popup_w, 0),
                     "down": (0, trigger_h),
                     "up": (0, -popup_h)}
            _OPPOSITES = {"down": ("up", 0, -popup_h),
                          "up": ("down", 0, trigger_h),
                          "right": ("left", -popup_w, 0),
                          "left": ("right", trigger_w, 0)}
            _CHECKS = {"down": y + popup_h > geo.bottom(),
                       "up": y < geo.top(),
                       "right": x + popup_w > geo.right(),
                       "left": x < geo.left()}

            match preferred_dir:
                case "right" | "left" | "down" | "up":
                    dx, dy = _BASE[preferred_dir]
                    x += dx
                    y += dy
                    if _CHECKS[preferred_dir]:
                        new_dir, opp_dx, opp_dy = _OPPOSITES[preferred_dir]
                        x = trigger_global.x() + opp_dx
                        y = trigger_global.y() + opp_dy
                        preferred_dir = new_dir
                case _:
                    print(f"НЕИЗВЕСТНОЕ НАПРАВЛЕНИЕ: {preferred_dir}")

        clamped_x, clamped_y = GeometryCalculator.clamp_to_screen(x, y, popup_w, popup_h, screen)
        return clamped_x, clamped_y, preferred_dir

    @staticmethod
    def calculate_max_popup_length(trigger_global: QPoint, trigger_w: int,
                                   trigger_h: int, preferred_dir: str,
                                   window_rect=None,
                                   max_length: int | None = None,
                                   clamp_to: str = "screen") -> int:
        """Вычисляет максимально доступную длину попапа.

        Вход:
            trigger_global — глобальные координаты триггера.
            trigger_w, trigger_h — размеры триггера.
            preferred_dir — "down" / "up" / "right" / "left" /
                            "auto". "auto" считается как вертикаль.
            window_rect — глобальный прямоугольник окна (QRect).
                          Используется только при
                          clamp_to_window=True.
            max_length — жёсткий предел от вызывающего кода
                         или None. Применяется поверх любого
                         ограничения.
            clamp_to — "screen" — резать по availableGeometry
                       экрана (по умолчанию);
                       "window" — резать по window_rect.

        Выход: максимальная длина попапа в пикселях.

        Роль:
            Единая точка предела длины попапа.
            Без ограничений — возвращается max_length или
            QWIDGETSIZE_MAX, и попап подстраивается под контент.
            С ограничением — режется свободным местом в прямом и
            обратном направлении: если calculate_popup_position
            перевернёт попап, длина останется достаточной.
        """
        if clamp_to == "window" and window_rect is not None:
            rect = window_rect
        else:
            screen = (
                    QGuiApplication.screenAt(trigger_global)
                    or QGuiApplication.primaryScreen()
            )
            if screen is None:
                return max_length if max_length is not None else 600
            rect = screen.availableGeometry()

        below = rect.bottom() - trigger_global.y() - trigger_h - 5
        above = trigger_global.y() - rect.top() - 5
        right = rect.right() - trigger_global.x() - trigger_w - 5
        left = trigger_global.x() - rect.left() - 5

        if preferred_dir in ("right", "left"):
            avail = max(right, left)
        else:
            avail = max(below, above)

        avail = max(50, avail)
        if max_length is not None:
            return min(max_length, avail)
        return avail