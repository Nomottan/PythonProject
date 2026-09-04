# planner_storage.py

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from utils.path_utils import PathManager
from models.planner_models import PlannerTask

# Настройка логирования
logger = logging.getLogger('PlannerStorage')
logger.setLevel(logging.INFO)
handler = logging.FileHandler('planner.log', mode='w', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class TaskRepository:
    def __init__(self, filename="tasks.json"):
        self.path_manager = PathManager()
        self.file_path = self.path_manager.get_data_path() / filename
        self.tasks: list[PlannerTask] = []
        self.load()

    def load(self):
        """Загружает задачи из файла."""
        if not self.file_path.exists():
            logger.info(f"Файл {self.file_path.name} не найден. Создан пустой список.")
            self.tasks = []
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"Неверный формат {self.file_path.name}: ожидался список.")
                self.tasks = []
                return
            self.tasks = [PlannerTask.from_dict(item) for item in data]
            logger.info(f"Загружено {len(self.tasks)} задач из {self.file_path.name}.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения {self.file_path.name}: {e}")
            self.tasks = []

    def save(self):
        """Сохраняет задачи в файл."""
        try:
            data = [task.to_dict() for task in self.tasks]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"Сохранено {len(self.tasks)} задач в {self.file_path.name}.")
        except IOError as e:
            logger.error(f"Ошибка записи {self.file_path.name}: {e}")

    def add(self, task: PlannerTask):
        """Добавляет задачу и сохраняет файл."""
        self.tasks.append(task)
        self.save()

    def update(self, task_id: str, updated_task: PlannerTask):
        """Заменяет задачу с указанным id."""
        for i, task in enumerate(self.tasks):
            if task.id == task_id:
                self.tasks[i] = updated_task
                self.save()
                return
        logger.warning(f"Задача с id {task_id} не найдена при обновлении.")

    def remove(self, task_id: str):
        """Удаляет задачу по id и сохраняет файл."""
        self.tasks = [task for task in self.tasks if task.id != task_id]
        self.save()

    def get_by_id(self, task_id: str) -> PlannerTask | None:
        """Возвращает задачу по id или None."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_templates(self) -> list[PlannerTask]:
        """Возвращает все шаблоны (is_template=True)."""
        return [task for task in self.tasks if task.is_template]

    def get_instances(self) -> list[PlannerTask]:
        """Возвращает все экземпляры (is_template=False)."""
        return [task for task in self.tasks if not task.is_template]

    def get_all(self) -> list[PlannerTask]:
        """Возвращает все задачи."""
        return list(self.tasks)


class ArchiveRepository:
    """Хранилище архивных записей."""

    def __init__(self, file_path="archive.json"):
        self.path_manager = PathManager()
        self.file_path = self.path_manager.get_data_path()
        self.archive: list[PlannerTask] = []
        self.load()

    def load(self):
        """Загружает архив из файла."""
        if not self.file_path.exists():
            logger.info(f"Файл {self.file_path.name} не найден. Создан пустой список.")
            self.archive = []
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                logger.error(f"Неверный формат {self.file_path.name}: ожидался список.")
                self.archive = []
                return
            self.archive = [PlannerTask.from_dict(item) for item in data]
            logger.info(f"Загружено {len(self.archive)} записей из {self.file_path.name}.")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Ошибка чтения {self.file_path.name}: {e}")
            self.archive = []

    def save(self):
        """Сохраняет архив в файл."""
        try:
            data = [task.to_dict() for task in self.archive]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"Сохранено {len(self.archive)} записей в {self.file_path.name}.")
        except IOError as e:
            logger.error(f"Ошибка записи {self.file_path.name}: {e}")

    def add(self, record: PlannerTask):
        """Добавляет запись в архив и сохраняет файл."""
        self.archive.append(record)
        self.save()

    def remove(self, record_id: str):
        """Удаляет запись из архива по id и сохраняет файл."""
        self.archive = [rec for rec in self.archive if rec.id != record_id]
        self.save()

    def get_by_id(self, record_id: str) -> PlannerTask | None:
        """Возвращает архивную запись по id или None."""
        for rec in self.archive:
            if rec.id == record_id:
                return rec
        return None

    def get_all(self) -> list[PlannerTask]:
        """Возвращает все архивные записи."""
        return list(self.archive)

    def get_filtered(self, filters: dict | None = None) -> list[PlannerTask]:
        """
        Возвращает отфильтрованные записи.
        Пока заглушка: возвращает все записи. Фильтры будут реализованы позже.
        """
        # TODO: реализовать фильтрацию по типам, датам и приоритетам
        return self.get_all()

    def cleanup_expired(self):
        """Удаляет записи, у которых срок хранения истёк (7 дней для удалённых шаблонов и невыполненных экземпляров)."""
        now = datetime.now()
        threshold = now - timedelta(days=7)
        expired = []
        for rec in self.archive:
            if rec.status in ("deleted_template", "expired_not_completed"):
                if rec.archived_at and rec.archived_at < threshold:
                    expired.append(rec)
        if expired:
            self.archive = [rec for rec in self.archive if rec not in expired]
            self.save()
            logger.info(f"Очищено {len(expired)} устаревших записей из архива.")