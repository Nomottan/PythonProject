"""
Резолвер эффективного фона виджета.

Содержит BackgroundResolver — определяет «эффективный» bg_color:
либо свой непрозрачный, либо ближайший непрозрачный у предка
или у окна. Используется при расчёте контрастного цвета текста,
когда виджет полупрозрачен (alpha == 0).
"""


class BackgroundResolver:
    """Определяет эффективный фон виджета.

    Роль:
        При полупрозрачном bg_color (alpha == 0) ищет ближайший
        непрозрачный у предков или у окна. Непрозрачным считается
        кортеж/список из 3+ элементов: длина 3 — по определению,
        длина 4 — если alpha > 0. Строки и не-кортежи
        возвращаются как есть.

    Контракты:
        Все методы — static. Исключений не бросает: на
        некорректном входе возвращает вход.
    """

    @staticmethod
    def resolve_bg_color(widget, bg_color):
        """Возвращает эффективный bg_color.

        Вход:
            widget — QWidget или None.
            bg_color — цвет (кортеж/список/строка/None).

        Выход:
            Кортеж непрозрачного цвета, если исходный был прозрачным
            и нашёлся у предка; иначе исходный bg_color.

        Роль:
            - widget is None → bg_color как есть.
            - bg_color не кортеж/список или длина < 3 → как есть.
            - длина == 3 → как есть.
            - длина == 4 и alpha > 0 → как есть.
            - длина == 4 и alpha == 0 → поиск у предков, затем у window().
            - Не найдено → исходный bg_color.
        """
        # 1. Искать негде.
        if widget is None:
            return bg_color
        # 2. Не кортеж/список или слишком короткий.
        if not isinstance(bg_color, (tuple, list)) or len(bg_color) < 3:
            return bg_color
        # 3. 3-элементный — считаем непрозрачным.
        if len(bg_color) == 3:
            return bg_color
        # 4. 4-элементный: alpha > 0 — непрозрачен.
        if len(bg_color) >= 4:
            try:
                alpha = bg_color[3]
            except (TypeError, IndexError):
                return bg_color
            if alpha is None:
                return bg_color
            try:
                if float(alpha) > 0:
                    return bg_color
            except (TypeError, ValueError):
                return bg_color

        # 5. alpha == 0 — ищем у предков.
        found = BackgroundResolver._walk_parents(
            widget,
            attr_name="bg_color",
            predicate=BackgroundResolver._is_opaque,
        )
        if found is not None:
            return found

        # 6. Проверяем window().
        try:
            top = widget.window()
        except Exception:
            top = None
        if top is not None and top is not widget:
            top_bg = getattr(top, "bg_color", None)
            if top_bg is not None and BackgroundResolver._is_opaque(top_bg):
                return top_bg

        # 7. Ничего не нашли.
        return bg_color

    @staticmethod
    def resolve_parent_bg(parent, fallback):
        """Возвращает цвет фона родителя.

        Вход:
            parent — QWidget или None.
            fallback — значение по умолчанию.

        Выход:
            parent.bg_color, если есть; иначе parent.window().bg_color,
            если есть; иначе fallback. Значение возвращается как есть —
            без обрезки [:3], без нормализации.

        Роль:
            Единая точка поиска фона родителя. Исключений не бросает:
            при любой ошибке доступа к атрибуту возвращает fallback.
        """
        if parent is not None:
            try:
                if hasattr(parent, "bg_color"):
                    return parent.bg_color
                top = parent.window()
                if top is not None and hasattr(top, "bg_color"):
                    return top.bg_color
            except Exception:
                return fallback
        return fallback

    @staticmethod
    def _walk_parents(widget, attr_name, predicate, max_steps=10):
        """Идёт вверх по widget.parent() в поисках атрибута.

        Вход:
            widget — стартовый QWidget или None.
            attr_name — имя атрибута (например, "bg_color").
            predicate — callable(value) -> bool; отбор подходящих.
            max_steps — максимальная глубина (по умолчанию 10).

        Выход:
            Первое подходящее значение атрибута у предка или None.

        Роль:
            Единая утилита для поиска свойств по цепочке родителей.
            Идёт от widget.parent() вверх, максимум max_steps шагов.
        """
        if widget is None:
            return None
        current = widget
        steps = 0
        while current is not None and steps < max_steps:
            try:
                parent = current.parent()
            except Exception:
                return None
            if parent is None:
                return None
            if hasattr(parent, attr_name):
                value = getattr(parent, attr_name)
                if predicate(value):
                    return value
            current = parent
            steps += 1
        return None

    @staticmethod
    def _is_opaque(bg_color) -> bool:
        """Проверяет, что цвет непрозрачный.

        Вход: bg_color — значение любого типа.
        Выход:
            True — кортеж/список из 3+ элементов, где длина 3 или
            длина 4 и alpha > 0.
            False — для всего остального.

        Роль: предикат для _walk_parents и фильтрации.
        """
        if not isinstance(bg_color, (tuple, list)):
            return False
        if len(bg_color) < 3:
            return False
        if len(bg_color) == 3:
            return True
        # 4+ — проверяем alpha.
        try:
            return float(bg_color[3]) > 0
        except (TypeError, ValueError, IndexError):
            return False