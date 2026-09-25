"""
Вычисление и преобразование цветов.

Содержит ColorCalculator — единая точка работы с цветами в проекте:
преобразование кортежей в CSS-строки, нормализация к RGBA,
расчёт состояний (hover/pressed/disabled), подбор контрастного
цвета текста, извлечение RGB из разных форматов.

Роль в программе:
    Поглощает методы BaseWidgetFactory.calc_* и ListWidgetFactory._extract_rgb.
    BaseWidgetFactory становится тонкой прослойкой, делегирующей сюда.
"""

from typing import Optional, Tuple


class ColorCalculator:
    """Калькулятор цветов.

    Назначение:
        Единая точка работы с цветами: любой формат (кортеж или
        строка) приводится к RGBA, из него считаются состояния,
        итог сериализуется в CSS-строку.

    Роль в программе:
        Родитель для WidgetStyle (фасад) и источник методов для
        BaseWidgetFactory. Все остальные классы работают с цветами
        только через ColorCalculator.

    Форматы цвета на входе:
        кортеж (r, g, b) — alpha 1.0.
        кортеж (r, g, b, a) — с alpha.
        "#RGB", "#RRGGBB".
        "rgb(r, g, b)", "rgba(r, g, b, a)".
        Имена CSS ("white", "red") не поддерживаются — слишком
        большой справочник. При необходимости вызывающий код
        раскрывает имя сам.
    """

    @staticmethod
    def to_str(color) -> str:
        """Преобразует кортеж цвета в CSS-строку.

        Вход:
            color — кортеж (r, g, b) или (r, g, b, a), либо строка.

        Выход: строка "rgb(...)" / "rgba(...)" или исходная строка.

        Роль: единая точка преобразования кортежей в CSS. Если
              на входе строка — возвращается как есть. Числа
              приводятся к int/float автоматически.
        """
        if isinstance(color, str):
            return color
        if isinstance(color, (tuple, list)):
            if len(color) == 3:
                r, g, b = color
                return f"rgb({int(r)}, {int(g)}, {int(b)})"
            if len(color) == 4:
                r, g, b, a = color
                return f"rgba({int(r)}, {int(g)}, {int(b)}, {float(a)})"
        return str(color)

    @staticmethod
    def to_rgba(color) -> Optional[Tuple[int, int, int, float]]:
        """Нормализует цвет к кортежу (r, g, b, a).

        Вход:
            color — кортеж (r, g, b) или (r, g, b, a), либо строка
                    одного из форматов:
                    "#RGB", "#RRGGBB", "rgb(r, g, b)",
                    "rgba(r, g, b, a)".

        Выход:
            (r, g, b, a) — кортеж целых r, g, b (0–255) и float a (0–1),
            либо None, если распарсить не удалось.

        Роль: единая точка нормализации. Все методы расчёта
              состояний и подбора текста используют её, поэтому
              работают одинаково и с кортежами, и со строками.
        """
        if color is None:
            return None

        # --- Кортеж / список ---
        if isinstance(color, (tuple, list)):
            n = len(color)
            if n == 3:
                try:
                    r, g, b = int(color[0]), int(color[1]), int(color[2])
                except (TypeError, ValueError):
                    return None
                return (r, g, b, 1.0)
            if n == 4:
                try:
                    r, g, b = int(color[0]), int(color[1]), int(color[2])
                    a = float(color[3])
                except (TypeError, ValueError):
                    return None
                return (r, g, b, a)
            return None

        # --- Строка ---
        if isinstance(color, str):
            s = color.strip().lower()

            # "#RGB" / "#RRGGBB"
            if s.startswith("#"):
                s = s[1:]
                if len(s) == 3:
                    try:
                        r = int(s[0] * 2, 16)
                        g = int(s[1] * 2, 16)
                        b = int(s[2] * 2, 16)
                    except ValueError:
                        return None
                    return (r, g, b, 1.0)
                if len(s) == 6:
                    try:
                        r = int(s[0:2], 16)
                        g = int(s[2:4], 16)
                        b = int(s[4:6], 16)
                    except ValueError:
                        return None
                    return (r, g, b, 1.0)
                return None

            # "rgb(...)" / "rgba(...)"
            if s.startswith("rgb"):
                body = s[s.find("(") + 1:s.rfind(")")]
                if not body:
                    return None
                parts = [p.strip() for p in body.split(",")]
                try:
                    if len(parts) == 3:
                        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                        return (r, g, b, 1.0)
                    if len(parts) == 4:
                        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                        a = float(parts[3])
                        return (r, g, b, a)
                except (ValueError, TypeError):
                    return None
                return None

            return None

        return None

    @staticmethod
    def pack_rgba(r: int, g: int, b: int, a: float):
        """Упаковывает (r, g, b, a) в кортеж для to_str.

        Вход: r, g, b — целые 0–255; a — float 0–1.

        Выход: кортеж из 3 элементов, если a == 1.0, иначе из 4.

        Роль: сохранить формат вывода. Для alpha=1.0 — rgb(...),
              для остальных — rgba(...).
        """
        if a == 1.0:
            return (r, g, b)
        return (r, g, b, a)

    @staticmethod
    def hover(bg_color) -> str:
        """Рассчитывает цвет для состояния :hover.

        Вход: bg_color — кортеж или строка.

        Выход: CSS-строка rgb/rgba или "" при невалидном входе.

        Роль: осветляет или затемняет базовый цвет на ±25 по
              каждому каналу. Если c + 25 > 255 — идём вниз,
              иначе — вверх. При пустом входе — "".
        """
        rgba = ColorCalculator.to_rgba(bg_color)
        if rgba is None:
            return ""
        r, g, b, a = rgba

        hover = []
        for c in (r, g, b):
            if c + 25 <= 255:
                hover.append(c + 25)
            else:
                hover.append(c - 25)

        return ColorCalculator.to_str(
            ColorCalculator.pack_rgba(hover[0], hover[1], hover[2], a)
        )

    @staticmethod
    def pressed(bg_color) -> str:
        """Рассчитывает цвет для состояния :pressed.

        Вход: bg_color — кортеж или строка.

        Выход: CSS-строка rgb/rgba или "".

        Роль: c − 25, если c ≥ 25, иначе c + 25. Темнее для
              светлых, светлее для тёмных — эффект «вдавливания».
              Контрастно к hover.
        """
        rgba = ColorCalculator.to_rgba(bg_color)
        if rgba is None:
            return ""
        r, g, b, a = rgba

        pressed = []
        for c in (r, g, b):
            if c >= 25:
                pressed.append(c - 25)
            else:
                pressed.append(c + 25)

        return ColorCalculator.to_str(
            ColorCalculator.pack_rgba(pressed[0], pressed[1], pressed[2], a)
        )

    @staticmethod
    def disabled(bg_color) -> str:
        """Рассчитывает цвет для состояния :disabled.

        Вход: bg_color — кортеж или строка.

        Выход: CSS-строка rgba или "".

        Роль: avg = (r + g + b) // 3; каждый канал смещается к
              среднему наполовину. Даёт «выцветший» вид. Alpha
              принудительно 0.8.
        """
        rgba = ColorCalculator.to_rgba(bg_color)
        if rgba is None:
            return ""
        r, g, b, _ = rgba
        avg = (r + g + b) // 3
        return ColorCalculator.to_str((
            avg + (r - avg) // 5,
            avg + (g - avg) // 5,
            avg + (b - avg) // 5,
            0.8,
        ))

    @staticmethod
    def text_for(bg_color, forced=None) -> str:
        """Определяет контрастный цвет текста для фона.

        Вход:
            bg_color — кортеж или строка.
            forced — если задан, возвращается как есть.

        Выход: CSS-цвет текста (#000000 / rgb(...) / rgba(...)).

        Роль: если forced задан — используем его. Иначе нормализуем
              bg_color к RGBA и по средней яркости avg = (r+g+b)//3
              вычисляем «инверсный по яркости» цвет. Формула:
              целевое значение + по-канальное смещение на 1/10
              разницы — визуальный результат как в оригинале.
        """
        if forced is not None:
            return forced

        rgba = ColorCalculator.to_rgba(bg_color)
        if rgba is None:
            return "#ffffff"

        r, g, b, _ = rgba
        avg = (r + g + b) // 3
        if avg > 128:
            target = avg - 128
        else:
            target = avg + 127

        text = []
        for c in (r, g, b):
            if target >= c:
                text.append(target + (target - c) // 10)
            else:
                text.append(target - (c - target) // 10)

        return ColorCalculator.to_str(tuple(text))

    @staticmethod
    def extract_rgb(color) -> Tuple[int, int, int]:
        """Извлекает (r, g, b) из разных форматов цвета.

        Вход: color — кортеж или строка.
        Выход: (r, g, b) — целые. Fallback (25, 25, 45) при
               невалидном входе.

        Роль: используется для расчёта скроллбара. Alpha
              отбрасывается — для скроллбаров она задаётся
              отдельно.
        """
        rgba = ColorCalculator.to_rgba(color)
        if rgba is None:
            return 25, 25, 45
        r, g, b, _ = rgba
        return r, g, b