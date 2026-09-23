"""
Пакет storage — единый слой работы с JSON-файлами проекта.

Содержит базовые классы (base_json_storage) и специализированные
хранилища для каждого файла. Реэкспортирует публичные имена
для удобного импорта:

    from storage import KizStorage, MainConfig, PlannerTaskStorage

Правило: наружу торчат только перечисленные в __all__ классы.
Внутренние детали (хуки, приватные методы) — не часть публичного API.
"""

# --- Базовые классы ---
# BaseJsonStorage — атомарная работа с одним JSON-файлом.
# ListJsonStorage — для файлов со списком в корне.
# DictJsonStorage — для файлов со словарём в корне.
# ConfigJsonStorage — упрощённый словарь без поключевого remove.
from storage.base_json_storage import (
    BaseJsonStorage,
    ListJsonStorage,
    DictJsonStorage,
    ConfigJsonStorage,
)

# Хранилище used_kiz.json: словарь {КИЗ: {sold_date, returned_date}}.
# С батчингом записи через utils.batcher.Batcher.
from storage.fbs_kiz_storage import KizStorage

# Хранилище активных задач планировщика (planner_tasks.json).
from storage.planner_task_storage import PlannerTaskStorage

# Хранилище архива задач планировщика (planner_archive.json).
from storage.planner_archive_storage import PlannerArchiveStorage

# Хранилище config.json: словарь с ключами "sellers" и "brands".
from storage.main_config import MainConfig

# Хранилище сохранённых сопоставлений сравнения (mappings.json).
# С миграцией старого формата (список → словарь).
from storage.compare_mappings_storage import CompareMappingsStorage

__all__ = [
    # Базовые
    "BaseJsonStorage",
    "ListJsonStorage",
    "DictJsonStorage",
    "ConfigJsonStorage",
    # Специализированные
    "KizStorage",
    "PlannerTaskStorage",
    "PlannerArchiveStorage",
    "MainConfig",
    "CompareMappingsStorage",
]