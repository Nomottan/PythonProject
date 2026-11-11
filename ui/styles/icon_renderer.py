"""
Отрисовка иконок через QPainter.

Содержит IconRenderer — единую точку рисования иконок проекта:
индикаторы чекбокса, стрелки, системные иконки действий.
"""

import base64
from PySide6.QtCore import Qt, QPointF, QRectF, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF,
    QTransform, QIcon
)
from .colors import ColorCalculator
from .sizing import SizingCalculator
from .bg_resolver import BackgroundResolver


class IconRenderer:
    """Рендерер иконок проекта."""

    @staticmethod
    def _to_rgb(color) -> tuple[int, int, int]:
        """Извлекает (r, g, b) из цвета любого формата."""
        rgba = ColorCalculator.to_rgba(color)
        if rgba is None:
            return 255, 255, 255
        return rgba[0], rgba[1], rgba[2]

    @staticmethod
    def make_checkbox_indicator(state, size: int, color) -> QPixmap:
        """Рисует индикатор чекбокса."""
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
        """Создаёт полигон стрелки."""
        base = QPolygonF([QPointF(7.5, 3), QPointF(7.5, 9), QPointF(3.5, 6)])
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
        """Отрисовывает стрелку."""
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
        """Рисует стрелку как QPixmap."""
        if bg_color is None:
            bg_color = (255, 255, 255)
        if size is None:
            if widget is not None:
                text_height = SizingCalculator.get_text_height(widget)
                size = max(8, min(int(text_height * 0.8), int(text_height * 1.2)))
            else:
                size = 12
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        arrow_color = ColorCalculator.text_for(bg_color)
        IconRenderer._draw_arrow(painter, direction, IconRenderer._to_rgb(arrow_color), size)
        painter.end()
        return pixmap

    @staticmethod
    def make_arrow(direction: str, widget, bg_color=None, size: int = None) -> QIcon:
        """Возвращает QIcon стрелки."""
        if bg_color is None:
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

    # ------------------------------------------------------------------
    # НОВЫЕ МЕТОДЫ ДЛЯ СИСТЕМНЫХ ИКОНОК (согласно §3.3)
    # ------------------------------------------------------------------

    @staticmethod
    def _draw_add(painter: QPainter) -> None:
        pen = QPen(painter.pen())
        pen.setWidthF(0.8)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(6, 6), 4.5, 4.5)
        painter.drawLine(QPointF(3.5, 6), QPointF(8.5, 6))
        painter.drawLine(QPointF(6, 3.5), QPointF(6, 8.5))

    @staticmethod
    def _draw_close(painter: QPainter) -> None:
        painter.drawLine(QPointF(3, 3), QPointF(9, 9))
        painter.drawLine(QPointF(9, 3), QPointF(3, 9))

    @staticmethod
    def _draw_complete(painter: QPainter) -> None:
        painter.drawLine(QPointF(3.25, 3.74), QPointF(6, 8.5))
        painter.drawLine(QPointF(8.75, 3.74), QPointF(6, 8.5))

    @staticmethod
    def _draw_edit(painter: QPainter) -> None:
        painter.drawLine(QPointF(9, 3), QPointF(4, 8))

        # Залитый треугольный кончик
        path = QPainterPath()
        path.moveTo(4.5, 8.5)
        path.lineTo(3.5, 7.5)
        path.lineTo(3, 9)
        path.closeSubpath()

        painter.save()
        painter.setPen(Qt.NoPen)
        # Используем цвет текущего пера для заливки
        painter.setBrush(painter.pen().color())
        painter.drawPath(path)
        painter.restore()

    @staticmethod
    def _draw_restore(painter: QPainter) -> None:
        path = QPainterPath()
        # Радиус 3.5, центр (6,6). Начало 45, размах 270.
        path.arcMoveTo(QRectF(2.5, 2.5, 7.0, 7.0), 45)
        path.arcTo(QRectF(2.5, 2.5, 7.0, 7.0), 45, 270)
        painter.drawPath(path)

        # Залитый треугольный наконечник в конечной точке (315 градусов)
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(painter.pen().color())

        # Приблизительные координаты наконечника (Пользователь визуально поправит)
        tip_poly = QPolygonF([
            QPointF(8.47, 3.53),  # Остриё
            QPointF(7.8, 4.8),  # Основание 1
            QPointF(9.2, 4.2)  # Основание 2
        ])
        painter.drawPolygon(tip_poly)
        painter.restore()

    @staticmethod
    def _draw_pause(painter: QPainter) -> None:
        painter.drawLine(QPointF(4, 3.5), QPointF(4, 8.5))
        painter.drawLine(QPointF(8, 3.5), QPointF(8, 8.5))

    @staticmethod
    def make_icon(icon_type: str, widget, size: int = None) -> QIcon:
        """Единый диспетчер иконок.

        Поддерживает системные иконки, стрелки (arrow_*) и
        тристейт-боксы (checkbox_*).
        """
        if size is None:
            size = SizingCalculator.calculate_icon_size(widget)

        if icon_type == "close":
            color = (255, 255, 255)
        else:
            bg = BackgroundResolver.resolve_bg_color(widget, None)
            color = ColorCalculator.text_for(bg)

        # 1. Диспетчеризация стрелок
        if icon_type.startswith("arrow_"):
            direction = icon_type.replace("arrow_", "")
            return IconRenderer.make_arrow(direction, widget, size=size)

        # 2. Диспетчеризация чекбоксов
        if icon_type.startswith("checkbox_"):
            state_str = icon_type.replace("checkbox_", "")
            state = Qt.Unchecked
            if state_str == "checked":
                state = Qt.Checked
            elif state_str == "partial":
                state = Qt.PartiallyChecked
            pixmap = IconRenderer.make_checkbox_indicator(state, size, color)
            return QIcon(pixmap)

        # 3. Отрисовка новых системных иконок
        pixmap = QPixmap(size * 2, size * 2)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 12.0, size / 12.0)

        rgb = IconRenderer._to_rgb(color)
        pen = QPen(QColor(*rgb))
        pen.setWidthF(1.6)
        pen.setJoinStyle(Qt.RoundJoin)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        if icon_type == "add":
            IconRenderer._draw_add(painter)
        elif icon_type == "close":
            IconRenderer._draw_close(painter)
        elif icon_type == "complete":
            IconRenderer._draw_complete(painter)
        elif icon_type == "edit":
            IconRenderer._draw_edit(painter)
        elif icon_type == "restore":
            IconRenderer._draw_restore(painter)
        elif icon_type == "pause":
            IconRenderer._draw_pause(painter)
        elif icon_type == "play":
            painter.scale(12.0 / size, 12.0 / size)
            IconRenderer._draw_arrow(painter, "right", rgb, size)


        painter.end()
        return QIcon(pixmap)

    # ------------------------------------------------------------------
    # ПУБЛИЧНЫЕ ОБЕРТКИ
    # ------------------------------------------------------------------

    @staticmethod
    def make_add_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("add", widget, size)

    @staticmethod
    def make_close_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("close", widget, size)

    @staticmethod
    def make_edit_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("edit", widget, size)

    @staticmethod
    def make_restore_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("restore", widget, size)

    @staticmethod
    def make_pause_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("pause", widget, size)

    @staticmethod
    def make_play_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("play", widget, size)

    @staticmethod
    def make_complete_icon(widget, size=None) -> QIcon:
        return IconRenderer.make_icon("complete", widget, size)