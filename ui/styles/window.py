"""
Стиль окон.

Содержит WindowStyle — QSS центрального виджета окна и кнопки
закрытия. Раньше это жило в WindowFactory.setup_child_window.

Роль в программе:
    Единая точка генерации QSS окна. WidgetStyle применяет
    через apply_window_central и apply_close_button.
"""

from .colors import ColorCalculator
from .bg_resolver import BackgroundResolver


class WindowStyle:
    """Стиль окна: фон центрального виджета и кнопка закрытия.

    Назначение:
        Убирает дублирование QSS окна из WindowFactory и
        ExtendedWindowFactory.

    Роль в программе:
        Используется через WidgetStyle.apply_window_central
        и WidgetStyle.apply_close_button.
    """

    @staticmethod
    def central_widget_qss(bg_color) -> str:
        """QSS для центрального виджета окна.

        Вход: bg_color — кортеж (r, g, b) или (r, g, b, a).

        Выход: QSS-строка.

        Роль: задаёт фон и скруглённые углы. Для 3-элементного
              кортежа — rgb(...) без альфы; для 4-элементного —
              rgba(...) с указанной альфой.
        """
        if len(bg_color) == 4:
            r, g, b, a = bg_color
            bg_css = f"rgba({r}, {g}, {b}, {a})"
        else:
            r, g, b = bg_color[:3]
            bg_css = f"rgb({r}, {g}, {b})"

        return f"""
                QWidget {{
                    background-color: {bg_css};
                    border-radius: 15px;
                }}
            """

    @staticmethod
    def close_button_qss(color) -> str:
        """QSS для кнопки закрытия «✕».

        Вход: color — цвет фона кнопки (строка или кортеж).

        Выход: QSS-строка с правилами базового состояния и :hover.

        Роль: единый стиль крестика во всех окнах. Hover —
              затемнённый красный (#c10020), как в оригинале.
        """
        color_str = ColorCalculator.to_str(color)
        return f"""
                    QPushButton {{
                        background-color: {color_str};
                        color: white;
                        font-weight: bold;
                        border: none;
                        border-radius: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: #c10020;
                    }}
                """

    @staticmethod
    def resolve_parent_bg(parent, fallback: tuple) -> tuple:
        """Возвращает цвет фона родителя для расчёта производных цветов.

        Вход:
            parent — родительское окно или None.
            fallback — цвет по умолчанию, если у parent нет bg_color.

        Выход:
            Кортеж (r, g, b) или (r, g, b, a). Возвращается как есть —
            без обрезки [:3].

        Роль:
            Делегирует в BackgroundResolver.resolve_parent_bg.
            Единая точка поиска фона родителя: parent.bg_color →
            parent.window().bg_color → fallback.
        """
        return BackgroundResolver.resolve_parent_bg(parent, fallback)

    @staticmethod
    def center_in_app_window(widget, anchor=None,
                             offset_x=10, offset_y=10):
        """Центрирует widget относительно anchor и зажимает его
        в границах ближайшего QMainWindow.

        Вход:
            widget — окно/диалог для позиционирования.
            anchor — источник геометрии (обычно service_window
                     или parent). None → service_window у widget
                     → widget.parent() → экран.
            offset_x, offset_y — сдвиг после центрирования (px).

        Выход: нет.

        Роль:
            Единая точка центрирования. Порядок:
                1. Источник — anchor / service_window / parent / экран.
                2. Желаемая позиция — центр + offset.
                3. Ближайший QMainWindow вверх по цепочке parent()
                   (или widget.window() как fallback) — границы clamp.
                4. x/y зажимаются в его frameGeometry.
            Заменяет три копии центрирования (setup_window,
            ChecklistItemDialog, MessageDialog).
        """
        from PySide6.QtWidgets import (
            QMainWindow, QApplication,
        )

        # 1. Источник геометрии.
        source = anchor
        if source is None:
            source = getattr(widget, "service_window", None)
        if source is None:
            source = widget.parent()

        if source is not None:
            source_geom = source.frameGeometry()
        else:
            app = QApplication.instance()
            if app is None:
                return
            screen = app.primaryScreen()
            if screen is None:
                return
            source_geom = screen.availableGeometry()

        w = widget.width()
        h = widget.height()

        # 2. Желаемая позиция.
        desired_x = (
                source_geom.x() + (source_geom.width() - w) // 2 + offset_x
        )
        desired_y = (
                source_geom.y() + (source_geom.height() - h) // 2 + offset_y
        )

        # 3. Ближайший QMainWindow — границы clamp.
        top = None
        p = widget.parent()
        while p is not None:
            if isinstance(p, QMainWindow):
                top = p
                break
            p = p.parent()
        if top is None:
            top = widget.window()

        # 4. Clamp.
        if top is not None and top is not widget:
            t_geom = top.frameGeometry()
            max_x = t_geom.x() + t_geom.width() - w
            max_y = t_geom.y() + t_geom.height() - h
            x = max(t_geom.x(), min(desired_x, max_x))
            y = max(t_geom.y(), min(desired_y, max_y))
        else:
            x, y = desired_x, desired_y

        widget.move(x, y)