"""
Сборка QSS-селекторов.

Содержит SelectorBuilder — единая точка сборки селекторов
("QPushButton", "QPushButton#name", "QPushButton#name:hover",
"QListWidget#name::item" и т.п.).

Роль в программе:
    Убирает дублирование шаблонов вида f"QPushButton#{name}" и
    f"{selector}:hover" из фабрик и QssBuilder. Работает без
    зависимостей — чистый формат.
"""


class SelectorBuilder:
    """Сборщик QSS-селекторов.

    Назначение:
        Единая точка формирования селекторов. Никакой логики,
        только конкатенация строк в правильном порядке.

    Роль в программе:
        Используется QssBuilder при генерации правил. Раньше
        селектор собирался вручную в каждой фабрике — теперь
        здесь.
    """

    @staticmethod
    def build(widget_class: str, object_name: str = None) -> str:
        """Собирает базовый селектор.

        Вход:
            widget_class — имя класса виджета ("QPushButton").
            object_name — опциональный objectName.

        Выход:
            "QPushButton#name" — если object_name задан;
            "QPushButton" — иначе.

        Роль: база для всех остальных методов.
        """
        if object_name:
            return f"{widget_class}#{object_name}"
        return widget_class

    @staticmethod
    def with_state(selector: str, state: str) -> str:
        """Добавляет псевдо-состояние к селектору.

        Вход:
            selector — базовый селектор ("QPushButton#name").
            state — имя состояния ("hover", "pressed", "disabled").

        Выход: "QPushButton#name:hover".

        Роль: единая точка для hover/pressed/disabled/checked
              и т.п.
        """
        return f"{selector}:{state}"

    @staticmethod
    def with_element(selector: str, element: str) -> str:
        """Добавляет псевдо-элемент к селектору.

        Вход:
            selector — базовый селектор ("QListWidget#name").
            element — имя элемента ("item", "indicator", "chunk").

        Выход: "QListWidget#name::item".

        Роль: единая точка для ::item, ::indicator, ::chunk.
        """
        return f"{selector}::{element}"