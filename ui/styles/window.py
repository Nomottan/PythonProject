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

        Роль: задаёт полупрозрачный фон и скруглённые углы.
              Для кортежа из 3 значений alpha = 0.8.
        """
        r, g, b, a = (
            bg_color if len(bg_color) == 4
            else (*bg_color, 0.8)
        )
        return f"""
            QWidget {{
                background-color: rgba({r}, {g}, {b}, {a});
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