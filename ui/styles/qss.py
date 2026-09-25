"""
Сборка QSS-блоков.

Содержит QssBuilder — единая точка сборки типовых QSS-блоков:
базовое правило, правила состояний (hover/pressed/disabled),
псевдо-элементы (::indicator, ::item, ::chunk).

Роль в программе:
    Убирает ручное склеивание QSS-строк в фабриках. Все фабрики
    при формировании стиля используют QssBuilder через
    WidgetStyle.
"""

from .colors import ColorCalculator


class QssBuilder:
    """Сборщик QSS-блоков.

    Назначение:
        Генерирует готовые QSS-строки для типовых случаев:
        основной блок селектора, правило одного свойства,
        правило для псевдо-элемента.

    Роль в программе:
        Основной инструмент WidgetStyle. Все CSS-правила
        собираются здесь.
    """

    @staticmethod
    def base_rule(selector: str, bg_color=None, text_color=None,
                  border=None, border_radius=None, padding=None,
                  font_size=None, font_family=None, font_weight=None,
                  alignment=None, extra_props="",
                  bg_property: str = "background-color") -> str:
        """Собирает основной QSS-блок.

        Вход:
            selector — селектор ("QPushButton#name").
            bg_color — цвет фона; None → не добавляем свойство.
            text_color — цвет текста; None → не добавляем.
            border — CSS-рамка; None → не добавляем.
            border_radius — радиус в px; None → не добавляем.
            padding — внутренние отступы.
            font_size — размер шрифта в px.
            font_family — семейство шрифта.
            font_weight — насыщенность.
            alignment — text-align.
            extra_props — дополнительные свойства строкой.
            bg_property — имя свойства фона. По умолчанию
                          "background-color". Для QScrollArea
                          в проекте используется "background"
                          (без -color) — сохраняем совместимость.

        Выход: QSS-блок "{ selector { ... } }".

        Роль: единая сборка основного блока. Порядок свойств:
              {bg_property} → color → border → border-radius →
              padding → font-size → font-family → font-weight →
              text-align → extra_props.
        """
        style = f"{selector} {{"
        if bg_color is not None:
            style += f" {bg_property}: {ColorCalculator.to_str(bg_color)};"
        if text_color is not None:
            style += f" color: {text_color};"
        if border is not None:
            style += f" border: {border};"
        if border_radius is not None:
            style += f" border-radius: {border_radius}px;"
        if padding is not None:
            style += f" padding: {padding};"
        if font_size is not None:
            style += f" font-size: {font_size}px;"
        if font_family is not None:
            style += f" font-family: {font_family};"
        if font_weight is not None:
            style += f" font-weight: {font_weight};"
        if alignment is not None:
            style += f" text-align: {alignment};"
        if extra_props:
            style += f" {extra_props}"
        style += " }"
        return style

    @staticmethod
    def background_rule(selector: str, color) -> str:
        """Собирает QSS-правило только с background-color.

        Вход:
            selector — селектор.
            color — цвет фона.

        Выход: QSS-блок.

        Роль: используется для :hover/:pressed/:disabled — там
              меняется только фон.
        """
        return (
            f"{selector} "
            f"{{ background-color: {ColorCalculator.to_str(color)}; }}"
        )

    @staticmethod
    def indicator_rule(selector: str, size: tuple, bg_color,
                       border: str, border_radius: int,
                       checked_bg_color) -> str:
        """Собирает QSS для ::indicator и ::indicator:checked.

        Вход:
            selector — базовый селектор.
            size — (w, h) квадратика.
            bg_color — фон индикатора в обычном состоянии.
            border — CSS-рамка.
            border_radius — радиус скругления.
            checked_bg_color — фон в состоянии :checked.

        Выход: два QSS-блока подряд (обычный + :checked).
        """
        base = f"{selector}::indicator"
        return (
            f"{base} {{"
            f" width: {size[0]}px;"
            f" height: {size[1]}px;"
            f" background-color: {ColorCalculator.to_str(bg_color)};"
            f" border: {border};"
            f" border-radius: {border_radius}px;"
            f" }}"
            f" {base}:checked {{"
            f" background-color: {ColorCalculator.to_str(checked_bg_color)};"
            f" }}"
        )

    @staticmethod
    def item_rule(selector: str, padding: str = "2px",
                  selected_bg=None) -> str:
        """Собирает QSS для ::item и опционально ::item:selected.

        Вход:
            selector — базовый селектор QListWidget.
            padding — внутренний отступ элемента.
            selected_bg — цвет фона в состоянии :selected;
                          None → правило :selected не добавляется.

        Выход: QSS-блок или два блока.
        """
        base = f"{selector}::item"
        style = f"{base} {{ padding: {padding}; }}"
        if selected_bg is not None:
            style += (
                f" {base}:selected "
                f"{{ background-color: {ColorCalculator.to_str(selected_bg)}; }}"
            )
        return style

    @staticmethod
    def chunk_rule(selector: str, chunk_color,
                   border_radius: int = None) -> str:
        """Собирает QSS для ::chunk.

        Вход:
            selector — базовый селектор QProgressBar.
            chunk_color — цвет заполнителя.
            border_radius — радиус скругления; None → не добавляем.

        Выход: QSS-блок.
        """
        style = (
            f"{selector}::chunk "
            f"{{ background-color: {ColorCalculator.to_str(chunk_color)};"
        )
        if border_radius is not None:
            style += f" border-radius: {border_radius}px;"
        style += " }"
        return style