from datetime import date

from models.planner_task import PlannerTask, TaskStatus
from storage.planner_task_storage import PlannerTaskStorage
from storage.planner_archive_storage import PlannerArchiveStorage
from utils.task_id_generator import TaskIdGenerator


class PlannerArchiveService:
    """Сервис архива задач.

    Роль: читает архив, восстанавливает задачи, удаляет навсегда.
          Держит оба storage: активный и архивный.
    """

    def __init__(self, archive_storage: PlannerArchiveStorage,
                 active_storage: PlannerTaskStorage, log_manager=None):
        """Конструктор.

        Вход:
            archive_storage — хранилище архива (planner_archive.json).
            active_storage — хранилище активных задач (planner_tasks.json).
            log_manager — LogManager для будущего логирования.

        Роль: сохраняет оба storage — через них идут все операции
              перемещения задач между активными и архивом.
        """
        self._archive_storage = archive_storage
        self._active_storage = active_storage
        self._log_manager = log_manager

    def get_archive_tasks(self) -> list[PlannerTask]:
        """Все задачи из архива, отсортированные по task_id убыв."""
        tasks = self._archive_storage.get_all()
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)

    def delete_forever(self, task_id: int) -> bool:
        """Удаляет задачу из архива навсегда.

        Вход: task_id — идентификатор задачи.
        Выход: True — задача найдена и удалена; False — не найдена.
        """
        return self._archive_storage.remove(task_id)

    def restore_task(self, task_id: int) -> PlannerTask | None:
        """Восстанавливает задачу из архива.

        Вход: task_id — идентификатор задачи в архиве.
        Выход: PlannerTask — восстановленная задача или None, если
               задача с таким id в архиве не найдена.

        Логика:
            CANCELLED → возвращает в активные с тем же task_id,
                        status = ACTIVE, completed_date = None.
            COMPLETED → создаёт новую задачу в активных с новым task_id
                        (от сегодня); оригинал остаётся в архиве.
        """
        # Ищем задачу в архиве.
        target = None
        for task in self._archive_storage.get_all():
            if task.task_id == task_id:
                target = task
                break
        if target is None:
            return None

        if target.status == TaskStatus.CANCELLED:
            # Возвращаем как есть — тот же task_id, статус ACTIVE.
            target.status = TaskStatus.ACTIVE
            target.completed_date = None
            self._archive_storage.remove(task_id)
            self._active_storage.add(target)
            return target

        if target.status == TaskStatus.COMPLETED:
            # Создаём новую задачу, оригинал остаётся в архиве.
            new_id = TaskIdGenerator.generate(self._active_storage)
            new_task = PlannerTask(
                task_id=new_id,
                title=target.title,
                description=target.description,
                priority=target.priority,
                status=TaskStatus.ACTIVE,
                created_date=date.today().strftime("%d.%m.%Y"),
                completed_date=None,
            )
            self._active_storage.add(new_task)
            return new_task

        # На случай, если в архиве оказалась задача с ACTIVE —
        # просто вернуть её в активные.
        target.status = TaskStatus.ACTIVE
        target.completed_date = None
        self._archive_storage.remove(task_id)
        self._active_storage.add(target)
        return target