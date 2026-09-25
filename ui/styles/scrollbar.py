"""
Стиль скроллбаров.

Содержит ScrollbarStyle — расчёт цветов и сборку QSS для
вертикального и горизонтального скроллбаров. Раньше это жило
в ListWidgetFactory как приватные методы.

Роль в программе:
    Единая точка стилизации скроллбаров. WidgetStyle вызывает
    ScrollbarStyle при создании QScrollArea — так стиль
    согласован во всём проекте.
"""

from .colors import ColorCalculator


class ScrollbarStyle:
    """Стиль скроллбаров.

    Назначение:
        Автоматически подбирает цвета ползунка и дорожки под фон
        окна, собирает QSS для QScrollBar:vertical/horizontal.

    Роль в программе:
        Используется через WidgetStyle.apply_scroll_area.
    """

    @staticmethod
    def palette(bg_color) -> dict:
        """Рассчитывает цвета скроллбара от фона окна.

        Вход: bg_color — кортеж (r, g, b) или (r, g, b, a), либо строка.

        Выход: dict с ключами handle, handle_hover, handle_pressed,
               track. Значения — кортежи (r, g, b, a).

        Роль: логика:
              - avg = (r + g + b) // 3 — средняя яркость фона.
              - Тёмный фон (avg <= 128) → ползунок светлее (+30).
              - Светлый фон (avg > 128) → ползунок темнее (−30).
              - Hover — сдвиг в ту же сторону ещё на ±30.
              - Pressed — минус 1.5 × hover_offset от handle.
              - Track — тот же RGB, что handle, alpha 0.6.
        """
        r, g, b = ColorCalculator.extract_rgb(bg_color)
        avg = (r + g + b) // 3
        shift = 30 if avg <= 128 else -30

        def clamp(v):
            return max(0, min(255, int(v)))

        handle = (clamp(r + shift), clamp(g + shift), clamp(b + shift), 0.8)

        hover_offset = 30 if shift > 0 else -30
        handle_hover = (
            clamp(r + shift + hover_offset),
            clamp(g + shift + hover_offset),
            clamp(b + shift + hover_offset),
            0.8,
        )

        handle_pressed = (
            clamp(r + shift - hover_offset * 1.5),
            clamp(g + shift - hover_offset * 1.5),
            clamp(b + shift - hover_offset * 1.5),
            0.8,
        )

        track = (handle[0], handle[1], handle[2], 0.6)

        return {
            "handle": handle,
            "handle_hover": handle_hover,
            "handle_pressed": handle_pressed,
            "track": track,
        }

    @staticmethod
    def build_qss(colors: dict, width: int = 12, radius: int = 6) -> str:
        """Собирает QSS для вертикального и горизонтального скроллбаров.

        Вход:
            colors — dict из palette.
            width — толщина скроллбара в px.
            radius — радиус скругления ползунка.

        Выход: строка QSS.

        Роль: единая точка генерации стиля скроллбара. Включает
              :hover и :pressed, убирает add-line/sub-line/
              add-page/sub-page (они дают артефакты).
        """

        def rgba(c):
            return f"rgba({c[0]}, {c[1]}, {c[2]}, {c[3]})"

        h = rgba(colors["handle"])
        hh = rgba(colors["handle_hover"])
        hp = rgba(colors["handle_pressed"])
        t = rgba(colors["track"])

        return f"""
                QScrollBar:vertical {{
                    background: {t};
                    width: {width}px;
                    margin: 0px;
                    border: none;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:vertical {{
                    background: {h};
                    min-height: 30px;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {hh};
                }}
                QScrollBar::handle:vertical:pressed {{
                    background: {hp};
                }}
                QScrollBar::add-line:vertical,
                QScrollBar::sub-line:vertical {{
                    height: 0px;
                    background: none;
                    border: none;
                }}
                QScrollBar::add-page:vertical,
                QScrollBar::sub-page:vertical {{
                    background: none;
                }}

                QScrollBar:horizontal {{
                    background: {t};
                    height: {width}px;
                    margin: 0px;
                    border: none;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:horizontal {{
                    background: {h};
                    min-width: 30px;
                    border-radius: {radius}px;
                }}
                QScrollBar::handle:horizontal:hover {{
                    background: {hh};
                }}
                QScrollBar::handle:horizontal:pressed {{
                    background: {hp};
                }}
                QScrollBar::add-line:horizontal,
                QScrollBar::sub-line:horizontal {{
                    width: 0px;
                    background: none;
                    border: none;
                }}
                QScrollBar::add-page:horizontal,
                QScrollBar::sub-page:horizontal {{
                    background: none;
                }}
            """
