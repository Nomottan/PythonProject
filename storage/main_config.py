"""
Конфигурация приложения: config.json.

Только хранилище: чтение/запись словаря. Работа с моделями
Seller/Brand — в services/sellers_brands_service.py.
"""

from storage.base_json_storage import ConfigJsonStorage


class MainConfig(ConfigJsonStorage):
    """Хранилище config.json.

    Роль: единая точка доступа к конфигу. Содержит ключи
          "sellers" и "brands" — списки dict-представлений.
          Логики по моделям тут нет.

    Формат: indent=4, как в старом ConfigManager — чтобы файл
            не переформатировался при переходе.
    """

    # Формат совпадает со старым config_manager.py.
    _JSON_INDENT = 4
    _JSON_SORT_KEYS = False

    def __init__(self, path_manager, log_manager=None) -> None:
        """Конструктор.

        Вход:
            path_manager — PathManager, откуда берём путь к config.json.
            log_manager — LogManager для логирования.

        Роль: путь к файлу — из PathManager.config_file, чтобы
              не хардкодить "Data/config.json" в двух местах.
        """
        super().__init__(
            path_manager.config_file, log_manager,
            source="MainConfig.main_config",
        )

    # ---------- Хуки ConfigJsonStorage ----------

    def _default_data(self) -> dict:
        """Пустой конфиг."""
        return {}

    def _to_raw(self) -> dict:
        """Пишем словарь как есть."""
        return self._data