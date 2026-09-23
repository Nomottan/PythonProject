"""
Хранилище архива задач планировщика в JSON-файле.

Переработка на ListJsonStorage: как PlannerTaskStorage, но
для planner_archive.json. Отдельный source в логах, чтобы
записи архива и активных задач не смешивались.
"""

from models.planner_task import PlannerTask
from storage.base_json_storage import ListJsonStorage


class PlannerArchiveStorage(ListJsonStorage):
    """Хранилище архива задач планировщика.

    Роль: хранит список PlannerTask в planner_archive.json.
          Отличие от PlannerTaskStorage — только путь и source
          в логах. Поведение полностью наследуется.
    """

    def __init__(self, file_path, log_manager=None) -> None:
        """Конструктор.

        Вход:
            file_path — путь к planner_archive.json.
            log_manager — LogManager для логирования.
        """
        super().__init__(
            file_path, log_manager,
            source="PlannerArchiveStorage.planner_archive_storage",
        )

    def _default_data(self) -> list:
        """Пустой список, если файла нет или он битый."""
        return []

    def _deserialize(self, raw: dict) -> PlannerTask:
        """Восстанавливает PlannerTask из dict."""
        return PlannerTask.from_dict(raw)

    def _serialize(self, item: PlannerTask) -> dict:
        """Превращает PlannerTask в dict для JSON."""
        return item.to_dict()

    def _get_id(self, item: PlannerTask) -> int:
        """Возвращает task_id элемента — для remove."""
        return item.task_id