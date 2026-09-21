from datetime import date, datetime
from typing import Optional
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
                 active_storage: PlannerTaskStorage, log_manager=None,
                 planner_service=None):
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
        self._planner_service = planner_service

    def get_archive_tasks(self) -> list[PlannerTask]:
        """Все задачи из архива, отсортированные по task_id убыв."""
        tasks = self._archive_storage.get_all()
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)

    def get_spawned_tasks(self, parent_id: int) -> list[PlannerTask]:
        """Возвращает активные задачи, порождённые задачей parent_id.

        Вход: parent_id — task_id архивной задачи-родителя.
        Выход: список PlannerTask из активного storage, у которых
               spawner_task == parent_id.

        Роль: проверка повторного восстановления COMPLETED-задачи.
              Если задача уже восстанавливалась, в активных есть
              запись с spawner_task = этой архивной задачи.
        """
        return [
            t for t in self._active_storage.get_all()
            if t.spawner_task == parent_id
        ]

    def delete_forever(self, task_id: int) -> bool:
        """Удаляет задачу из архива навсегда.

        Вход: task_id — идентификатор задачи.
        Выход: True — задача найдена и удалена; False — не найдена.
        """
        return self._archive_storage.remove(task_id)

    def restore_task(self, task_id: int,
                     deadline_datetime: Optional[str] = None) -> PlannerTask | None:
        """Восстанавливает задачу из архива.

        Вход:
            task_id — идентификатор в архиве.
            deadline_datetime — новая дата дедлайна (для дедлайн-задач
                                из DeadlineEditDialog). Может быть None.

        Выход: PlannerTask или None.
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
            target.status = TaskStatus.ACTIVE
            target.completed_date = None
            if deadline_datetime:
                target.deadline_datetime = deadline_datetime
            self._archive_storage.remove(task_id)
            self._active_storage.add(target)
            # NEW: уведомляем подписчиков (мини-планировщик, PlannerWindow).
            self._emit_tasks_changed()
            return target

        if target.status == TaskStatus.COMPLETED:
            new_id = TaskIdGenerator.generate(self._active_storage)
            new_task = PlannerTask(
                task_id=new_id,
                title=target.title,
                description=target.description,
                priority=target.priority,
                status=TaskStatus.ACTIVE,
                created_date=date.today().strftime("%d.%m.%Y"),
                completed_date=None,
                spawner_task=task_id,
                deadline_datetime=deadline_datetime or target.deadline_datetime,
                created_datetime=datetime.now().strftime("%d.%m.%Y %H:%M"),
            )
            self._active_storage.add(new_task)
            # NEW: уведомляем подписчиков.
            self._emit_tasks_changed()
            return new_task

            # Fallback: ACTIVE-задача в архиве.
        target.status = TaskStatus.ACTIVE
        target.completed_date = None
        if deadline_datetime:
            target.deadline_datetime = deadline_datetime
        self._archive_storage.remove(task_id)
        self._active_storage.add(target)
        # NEW: уведомляем подписчиков.
        self._emit_tasks_changed()
        return target

    def _emit_tasks_changed(self) -> None:
        """Испускает tasks_changed у PlannerService, если он передан.

        Роль: единая точка уведомления подписчиков после изменений
              активного хранилища. Если PlannerService не передан —
              тихо ничего не делаем (обратная совместимость).
        """
        if self._planner_service is not None:
            self._planner_service.tasks_changed.emit()