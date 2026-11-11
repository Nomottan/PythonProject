"""
Отрисовка иконок через QPainter.

Содержит IconRenderer — единую точку рисования иконок проекта:
индикаторы чекбокса, стрелки выпадающих списков, прочие
элементы, которые раньше были SVG-файлами.

Роль в программе:
    Постепенный отказ от SVG-иконок в пользу рисования кодом.
    Преимущества: единая точка цвета (ColorCalculator), нет
    внешних файлов, нет рассинхронизации при смене палитры,
    HiDPI из коробки. Каждый метод отвечает за свой визуальный
    элемент и переиспользует приватные утилиты класса.
"""

import base64
from PySide6.QtCore import Qt, QPointF, QRectF, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF,
    QTransform, QIcon
)
from .colors import ColorCalculator
from .sizing import SizingCalculator

class IconRenderer:
    """Рендерер иконок проекта.

    Назначение:
        Рисует QPixmap для визуальных элементов, которые раньше
        жили в SVG: индикаторы чекбокса, стрелки выпадающих
        списков, маркеры и т.п. Один класс — одна точка правок
        для всех иконок.

    Роль в программе:
        Постепенно заменяет SVG-файлы в ui/styles/icons/. Каждый
        публичный метод — отдельная иконка; общая логика
        (нормализация цвета, HiDPI-обвязка) — в приватных
        утилитах класса.

    Соглашения:
        Все публичные методы — @staticmethod, возвращают QPixmap
        с devicePixelRatio = 2 и прозрачным фоном.
    """

    @staticmethod
    def _to_rgb(color) -> tuple[int, int, int]:
        """Извлекает (r, g, b) из цвета любого формата.

        Вход:
            color — кортеж (r, g, b) / (r, g, b, a) или строка
                    любого формата, поддерживаемого ColorCalculator.

        Выход:
            (r, g, b) — целые 0–255. Fallback (255, 255, 255) при
            невалидном входе.

        Роль:
            Единая точка нормализации через ColorCalculator.to_rgba.
            Допускает и кортежи, и строки — вызывающий код может
            передать результат ColorCalculator.hover/text_for как есть.
        """
        rgba = ColorCalculator.to_rgba(color)
        if rgba is None:
            return 255, 255, 255
        return rgba[0], rgba[1], rgba[2]

    @staticmethod
    def make_checkbox_indicator(state, size: int, color) -> QPixmap:
        """Рисует индикатор чекбокса в указанном состоянии.

        Вход:
            state — Qt.CheckState (Unchecked / PartiallyChecked /
                    Checked). Внешний модуль выставляет состояние
                    через setCheckState; сам CheckBox эмитит
                    булевы сигналы.
            size — логический размер стороны квадрата (int).
            color — цвет индикатора (кортеж или строка).

        Выход:
            QPixmap с devicePixelRatio = 2, прозрачный фон.

        Роль:
            Единая точка рисования индикатора чекбокса. Форма:
                Unchecked        — рамка.
                PartiallyChecked — рамка + диагональ из левого
                                   верхнего угла внутренней области
                                   в правый нижний.
                Checked          — рамка + заливка внутренней
                                   области.
            Толщина пера — 1.4. Скругления: рамка — 1.5 * scale,
            заливка — 1.0 * scale.
        """
        ratio = 2
        pixmap = QPixmap(size * ratio, size * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        rgb = IconRenderer._to_rgb(color)
        color_q = QColor(*rgb)
        pen = QPen(color_q)
        pen.setWidthF(1.4)
        painter.setPen(pen)

        scale = size / 12.0
        x = y = 1.5 * scale
        w = h = 9.0 * scale
        r = 1.5 * scale

        painter.drawRoundedRect(QRectF(x, y, w, h), r, r)

        if state == Qt.PartiallyChecked:
            inner_path = QPainterPath()
            inner_path.addRoundedRect(
                QRectF(2.5 * scale, 2.5 * scale, 7.0 * scale, 7.0 * scale),
                1.0 * scale, 1.0 * scale,
            )
            half_polygon = QPolygonF([
                QPointF(9.5 * scale, 2.5 * scale),
                QPointF(9.5 * scale, 9.5 * scale),
                QPointF(2.5 * scale, 9.5 * scale),
            ])
            half_path = QPainterPath()
            half_path.addPolygon(half_polygon)
            half_path.closeSubpath()

            clipped = inner_path.intersected(half_path)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color_q))
            painter.drawPath(clipped)
        elif state == Qt.Checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(*rgb)))
            inner_x = inner_y = 2.5 * scale
            inner_w = inner_h = 7.0 * scale
            inner_r = 1.0 * scale
            painter.drawRoundedRect(
                QRectF(inner_x, inner_y, inner_w, inner_h),
                inner_r, inner_r,
            )

        painter.end()
        return pixmap

    @staticmethod
    def _arrow_polygon(direction: str) -> QPolygonF:
        """Создаёт полигон стрелки с учётом направления."""
        base = QPolygonF([
            QPointF(7.5, 3), QPointF(7.5, 9), QPointF(3.5, 6)
        ])
        if direction == "left":
            return base
        if direction == "up":
            angle = -90
        elif direction == "right":
            angle = 180
        elif direction == "down":
            angle = 90
        else:
            return base

        transform = QTransform().translate(6, 6).rotate(angle).translate(-6, -6)
        return transform.map(base)

    @staticmethod
    def _draw_arrow(painter: QPainter, direction: str, color: tuple, size: int) -> None:
        """Отрисовывает стрелку в painter."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 12.0, size / 12.0)

        pen = QPen(QColor(*color))
        pen.setWidthF(1.6)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        painter.drawPolygon(IconRenderer._arrow_polygon(direction))

    @staticmethod
    def make_arrow_pixmap(direction: str, bg_color, size: int = None, widget=None) -> QPixmap:
        """Рисует стрелку как QPixmap (HiDPI 2x)."""
        if bg_color is None:
            bg_color = (255, 255, 255)

        if size is None:
            if widget is not None:
                text_height = SizingCalculator.get_text_height(widget)
                size = int(text_height * 0.8)
                max_size = int(text_height * 1.2)
                size = max(8, min(size, max_size))
            else:
                size = 12

        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        arrow_color = ColorCalculator.text_for(bg_color)
        IconRenderer._draw_arrow(
            painter, direction, IconRenderer._to_rgb(arrow_color), size
        )
        painter.end()
        return pixmap

    @staticmethod
    def make_arrow(direction: str, widget, bg_color=None, size: int = None) -> QIcon:
        """Возвращает QIcon стрелки."""
        if bg_color is None:
            from .bg_resolver import BackgroundResolver
            bg_color = BackgroundResolver.resolve_bg_color(widget, None)
            if bg_color is None:
                bg_color = (63, 63, 63)

        pixmap = IconRenderer.make_arrow_pixmap(direction, bg_color, size, widget)
        return QIcon(pixmap)

    @staticmethod
    def pixmap_to_data_uri(pixmap: QPixmap) -> str:
        """Конвертирует QPixmap в base64 Data URI."""
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        pixmap.save(buffer, "PNG")
        buffer.close()
        base64_str = base64.b64encode(byte_array.data()).decode("utf-8")
        return f"data:image/png;base64,{base64_str}"

    @staticmethod
    def make_arrow_data_uri(direction: str, widget, bg_color=None, size: int = None) -> str:
        """Возвращает base64 Data URI для стрелки."""
        pixmap = IconRenderer.make_arrow_pixmap(direction, bg_color, size, widget)
        return IconRenderer.pixmap_to_data_uri(pixmap)
