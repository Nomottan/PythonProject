"""
Фабрика выпадающих списков.

Содержит DroplistFactory — единую точку создания DropdownComposite.
"""


class DroplistFactory:
    """Фабрика для создания выпадающих списков."""

    @staticmethod
    def create_dropdown(parent, config: dict = None, **kwargs):
        """Создаёт DropdownComposite по конфигурации.

        Вход:
            parent — родительский виджет.
            config — словарь с настройками (settings) и элементами (items).
            **kwargs — дополнительные настройки, переопределяющие дефолтные.

        Выход: DropdownComposite.
        """
        # Ленивый импорт для разрыва потенциального цикла
        # (ui.factories -> ui.widgets -> ui.factories)
        from ui.widgets.dropdown_composite import DropdownComposite

        if config is None:
            config = {}

        dropdown = DropdownComposite(parent, config=config, **kwargs)

        for item in config.get("items", []):
            dropdown.add_item(item)

        return dropdown