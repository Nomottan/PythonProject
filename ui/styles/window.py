"""
Стиль окон.

Содержит WindowStyle — QSS центрального виджета окна и кнопки
закрытия. Раньше это жило в WindowFactory.setup_child_window.

Роль в программе:
    Единая точка генерации QSS окна. WidgetStyle применяет
    через apply_window_central и apply_close_button.
"""

from .colors import ColorCalculator


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
            Кортеж (r, g, b) или (r, g, b, a).

        Роль:
            Единая точка поиска фона родителя: parent.bg_color →
            parent.window().bg_color → fallback. Используется
            окнами и диалогами для расчёта производных цветов
            через ColorCalculator.derive.
        """
        if parent is not None:
            if hasattr(parent, "bg_color"):
                return parent.bg_color
            top = parent.window()
            if top is not None and hasattr(top, "bg_color"):
                return top.bg_color
        return fallback