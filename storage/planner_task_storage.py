"""
Хранилище задач планировщика в JSON-файле.

Переработка на ListJsonStorage: базовый класс берёт на себя
чтение, запись, логгирование. Здесь — только специфика домена:
как десериализовать PlannerTask и как достать task_id.
"""

from models.planner_task import PlannerTask
from storage.base_json_storage import ListJsonStorage


class PlannerTaskStorage(ListJsonStorage):
    """Хранилище активных задач планировщика.

    Роль: хранит список PlannerTask в planner_tasks.json. Публичный
          API — унаследованные get_all, add, remove. Наследник
          определяет только преобразование моделей в JSON и обратно.
    """

    def __init__(self, file_path, log_manager=None) -> None:
        """Конструктор.

        Вход:
            file_path — путь к planner_tasks.json.
            log_manager — LogManager для логирования.

        Роль: передаёт управление в ListJsonStorage, тот сам
              загрузит файл и вызовет _on_load.
        """
        super().__init__(
            file_path, log_manager,
            source="PlannerTaskStorage.planner_task_storage",
        )

    # ---------- Хуки ListJsonStorage ----------

    def _default_data(self) -> list:
        """Пустой список задач, если файла нет или он битый."""
        return []

    def _deserialize(self, raw: dict) -> PlannerTask:
        """Восстанавливает PlannerTask из dict.

        Вход: raw — словарь из JSON.
        Выход: PlannerTask.
        Роль: делегирует в from_dict модели. Обработка ошибок —
              в самой модели (неизвестный статус → fallback).
        """
        return PlannerTask.from_dict(raw)

    def _serialize(self, item: PlannerTask) -> dict:
        """Превращает PlannerTask в dict для JSON.

        Вход: item — PlannerTask.
        Выход: dict с примитивами.
        Роль: делегирует в to_dict модели.
        """
        return item.to_dict()

    def _get_id(self, item: PlannerTask) -> int:
        """Возвращает task_id элемента — для remove.

        Вход: item — PlannerTask.
        Выход: int task_id.
        """
        return item.task_id