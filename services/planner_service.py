from datetime import date
from utils.task_id_generator import TaskIdGenerator
from models.planner_task import PlannerTask, TaskPriority, TaskStatus
from storage.planner_task_storage import PlannerTaskStorage
from typing import Optional


class PlannerService:
    """Сервис планировщика задач.

    Роль: создаёт задачи, генерирует task_id, читает/пишет через storage.
    Не знает про UI. Задачи отдаёт отсортированными по task_id убыв.
    """

    def __init__(self, storage: PlannerTaskStorage,
                 archive_storage=None, log_manager=None):
        """Конструктор.

        Вход:
            storage — PlannerTaskStorage с путём к planner_tasks.json.
            archive_storage — PlannerArchiveStorage для архива. Если None,
                              архивация отключена (только удаление).
            log_manager — LogManager для будущего логирования.
        """
        self._storage = storage
        self._archive_storage = archive_storage
        self._log_manager = log_manager

    def get_tasks(self) -> list[PlannerTask]:
        """Возвращает список задач, отсортированный по task_id убыв (новые сверху)."""
        tasks = self._storage.get_all()
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)

    def create_task(self, title: str, description: str = "",
                    priority: TaskPriority = TaskPriority.MEDIUM,
                    spawner_task: Optional[int] = None) -> PlannerTask:
        """Создаёт задачу, генерирует task_id, сохраняет.

        Вход:
            title, description, priority — как раньше.
            spawner_task — task_id архивной задачи-родителя, если задача
                           создаётся при восстановлении COMPLETED. По умолчанию None.

        Выход: созданный PlannerTask.
        Ошибка: ValueError, если title пустой.
        """
        if not title or not title.strip():
            raise ValueError("Название задачи не может быть пустым")
        task_id = TaskIdGenerator.generate(self._storage)
        task = PlannerTask(
            task_id=task_id,
            title=title.strip(),
            description=description,
            priority=priority,
            status=TaskStatus.ACTIVE,
            created_date=date.today().strftime("%d.%m.%Y"),
            completed_date=None,
            spawner_task=spawner_task,
        )
        self._storage.add(task)
        return task

    def archive_task(self, task_id: int, final_status: TaskStatus) -> bool:
        """Архивирует задачу: удаляет из активных, добавляет в архив.

        Вход:
            task_id — идентификатор задачи.
            final_status — TaskStatus.COMPLETED или TaskStatus.CANCELLED.

        Выход: True — задача найдена и заархивирована; False — не найдена.

        Роль: помечает задачу финальным статусом, ставит completed_date,
              добавляет в архивный storage, затем удаляет из активного.
              Порядок важен: сначала добавить в архив, потом удалить
              из активных — чтобы при падении между шагами задача
              не потерялась полностью.
        """
        # Ищем задачу в активных.
        target = None
        for task in self._storage.get_all():
            if task.task_id == task_id:
                target = task
                break
        if target is None:
            return False

        # Проставляем финальный статус и дату завершения.
        target.status = final_status
        target.completed_date = date.today().strftime("%d.%m.%Y")

        # Сначала архив, потом удаление из активных.
        if self._archive_storage is not None:
            self._archive_storage.add(target)
        self._storage.remove(task_id)
        return True

    def update_task(self, task_id: int, title: str, description: str = "",
                    priority: TaskPriority = TaskPriority.MEDIUM) -> PlannerTask:
        """Обновляет существующую задачу.

        Вход:
            task_id — идентификатор задачи, которую меняем.
            title — новое название (обязательное, непустое).
            description — новое описание.
            priority — новый приоритет.

        Выход: обновлённый PlannerTask.

        Ошибка:
            ValueError — если title пустой или задача с таким task_id
                         не найдена.

        Роль: точечно меняет три поля, не трогая status/completed_date/
              created_date. Сохраняет storage.
        """
        if not title or not title.strip():
            raise ValueError("Название задачи не может быть пустым")

        # get_all() возвращает копию списка, но объекты те же —
        # мутация полей видна в storage.
        target = None
        for task in self._storage.get_all():
            if task.task_id == task_id:
                target = task
                break
        if target is None:
            raise ValueError(f"Задача с id={task_id} не найдена")

        target.title = title.strip()
        target.description = description
        target.priority = priority
        self._storage.save()
        return target

    def get_priorities(self) -> list[str]:
        """Возвращает список приоритетов в виде строк для UI."""
        return [p.display_name for p in TaskPriority]

    def get_statuses(self) -> list[str]:
        """Возвращает список статусов в виде строк для UI."""
        return [s.display_name for s in TaskStatus]

    def get_priority_by_display_name(self, name: str) -> TaskPriority:
        """Преобразует строку из UI обратно в TaskPriority.

        Если строка не найдена — возвращает TaskPriority.MEDIUM.
        """
        for p in TaskPriority:
            if p.display_name == name:
                return p
        return TaskPriority.MEDIUM

    def get_status_by_display_name(self, name: str) -> TaskStatus:
        """Преобразует строку из UI обратно в TaskStatus.

        Если строка не найдена — возвращает TaskStatus.ACTIVE.
        """
        for s in TaskStatus:
            if s.display_name == name:
                return s
        return TaskStatus.ACTIVE
