"""
Хранилище mappings.json — сохранённые сопоставления для сравнения.

Новый формат: {brand: {article: {"shk": ..., "supply_name": ...,
                                 "candidate_name": ...}}}
Старый формат (до рефакторинга): список записей. Миграция — в _on_load.
"""

from storage.base_json_storage import DictJsonStorage


class CompareMappingsStorage(DictJsonStorage):
    """Хранилище сохранённых сопоставлений артикулов.

    Роль: единая точка работы с mappings.json. Чтение и запись
          словаря брендов. Нормализация имён брендов (приведение
          к каноничному имени из config) — выше, в CompareService:
          storage не знает про бизнес-логику сравнения.

    Формат: indent=4, как в старом compare_service — файл не
            переформатируется при переходе.
    """

    _JSON_INDENT = 4
    _JSON_SORT_KEYS = False

    def __init__(self, path_manager, log_manager=None) -> None:
        """Конструктор.

        Вход:
            path_manager — PathManager, откуда берём путь к mappings.json.
            log_manager — LogManager для логирования.
        """
        super().__init__(
            path_manager.mappings_file, log_manager,
            source="CompareMappingsStorage.compare_mappings",
        )

    # ---------- Хуки DictJsonStorage ----------

    def _default_data(self) -> dict:
        """Пустой словарь сопоставлений."""
        return {}

    def _to_raw(self) -> dict:
        """Пишем словарь как есть."""
        return self._data

    def _on_load(self, data):
        """Миграция старого формата (список → словарь).

        Вход: data — то, что прочитано из JSON.
        Выход: (dict, changed).

        Роль: старый формат был списком записей вида
              [{"brand": ..., "article": ..., "shk": ...,
                "supply_name": ..., "candidate_name": ...}, ...].
              Новый — словарём по брендам. Конвертируем один раз
              при загрузке, файл перезапишется сразу (changed=True).
        """
        # Уже новый формат — dict.
        if isinstance(data, dict):
            # Защита: если в корне dict, но значения не dict-ы,
            # значит это какая-то гибридная структура — оставляем
            # как есть, выше разберутся.
            return data, False

        # Старый формат — список. Конвертируем.
        if isinstance(data, list):
            converted = {}
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                brand = entry.get("brand", "")
                article = entry.get("article", "")
                if not brand or not article:
                    continue
                converted.setdefault(brand, {})[article] = {
                    "shk": entry.get("shk", ""),
                    "supply_name": entry.get("supply_name", ""),
                    "candidate_name": entry.get("candidate_name", ""),
                }
            return converted, True

        # Что-то совсем неожиданное — warning и пустой словарь.
        self._log_warning(
            f"{self._file_path.name}: ожидался словарь или список, "
            f"получен {type(data).__name__}. Использую пустой."
        )
        return {}, False
