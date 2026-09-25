"""
Виджет лога статуса.

Содержит StatusLog — QTextEdit с предустановленным стилем для
отображения логов операций в окнах ЧЗ МП, Возвратов и Сравнения.
Цвета автоматически подстраиваются под фон родителя.
"""

from PySide6.QtWidgets import QTextEdit

from ui.factories.base_factory import BaseWidgetFactory

class StatusLog(QTextEdit):
    """Лог статуса: read-only QTextEdit со стилем под фон окна.

    Назначение:
        Единая точка отображения логов в окнах операций. Стиль
        (фон, рамка, шрифт) не дублируется в каждом окне —
        вычисляется от фона родителя или принимается явно.

    Роль в программе:
        Используется через StatusLogFactory.create_status_log.
        Заменяет самодельные QTextEdit с QSS в трёх окнах
        (ChzMPWindow, CompareWindow, ReturnsWindow).

    Публичный API:
        log(message) — добавить строку лога.
        clear() — унаследован от QTextEdit.

    Пример:
        log = StatusLogFactory.create_status_log(self, bg_color=self.bg_color)
        log.log("Готово.")
    """

    def __init__(self, parent=None, bg_color=None, border_color=None,
                 font_family="Consolas, monospace", font_size=10,
                 min_height=100, max_height=200) -> None:
        """Конструктор.

        Вход:
            parent — родительское окно/виджет.
            bg_color — фон лога. Если None — берётся у parent
                       (или parent.window()), иначе fallback
                       (40, 50, 60).
            border_color — цвет рамки. Если None — вычисляется
                           от bg_color (+30 к каждому каналу).
            font_family — шрифт лога (моноширинный по умолчанию).
            font_size — размер шрифта.
            min_height — минимальная высота.
            max_height — максимальная высота.

        Роль: собирает QSS и настраивает виджет одним вызовом.
        """
        super().__init__(parent)

        # Разрешаем фон: явный → parent.bg_color → parent.window().bg_color.
        resolved_bg = self._resolve_bg(bg_color, parent)
        # Рамка: явная → авто-расчёт от фона.
        resolved_border = (
            border_color if border_color is not None
            else self._calc_border(resolved_bg)
        )

        # QSS: фон с alpha 0.3 — полупрозрачный относительно окна.
        bg_str = BaseWidgetFactory.color_to_str(
            (*resolved_bg[:3], 0.3)
        )
        border_str = BaseWidgetFactory.color_to_str(resolved_border)

        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {bg_str};
                color: #d4d4d4;
                border: 1px solid {border_str};
                border-radius: 5px;
                padding: 5px;
                font-family: {font_family};
                font-size: {font_size}px;
            }}
        """)
        self.setMinimumHeight(min_height)
        self.setMaximumHeight(max_height)

    # ---------- Публичный API ----------

    def log(self, message: str) -> None:
        """Добавляет сообщение в лог.

        Вход: message — текст сообщения.
        Роль: обёртка над append — единая точка для вызывающего кода.
              clear() не переопределяем: у QTextEdit он уже есть.
        """
        self.append(message)

    # ---------- Вспомогательные ----------

    @staticmethod
    def _resolve_bg(bg_color, parent):
        """Возвращает (r, g, b) фона.

        Вход: bg_color — явный цвет или None; parent — виджет-родитель.
        Выход: кортеж (r, g, b).
        Роль: приоритет — явный → parent.bg_color → parent.window().bg_color
              → fallback (40, 50, 60).
        """
        if bg_color is not None:
            return tuple(bg_color[:3])
        if parent is not None:
            if hasattr(parent, "bg_color"):
                return tuple(parent.bg_color[:3])
            top = parent.window()
            if top is not None and hasattr(top, "bg_color"):
                return tuple(top.bg_color[:3])
        return (40, 50, 60)

    @staticmethod
    def _calc_border(bg_color):
        """Вычисляет цвет рамки от фона.

        Вход: bg_color — (r, g, b) или (r, g, b, a).
        Выход: кортеж (r, g, b, 0.8).
        Роль: +30 к каждому каналу — рамка светлее фона.
        """
        r, g, b = bg_color[:3]

        def clamp(v):
            return max(0, min(255, int(v)))

        return (clamp(r + 30), clamp(g + 30), clamp(b + 30), 0.8)