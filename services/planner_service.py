from datetime import date

from models.planner_task import PlannerTask, TaskPriority, TaskStatus
from storage.planner_task_storage import PlannerTaskStorage


class PlannerService:
    """Сервис планировщика задач.

    Роль: создаёт задачи, генерирует task_id, читает/пишет через storage.
    Не знает про UI. Задачи отдаёт отсортированными по task_id убыв.
    """

    def __init__(self, storage: PlannerTaskStorage, log_manager=None):
        """Конструктор.

        Вход:
            storage — PlannerTaskStorage с путём к planner_tasks.json.
            log_manager — LogManager для будущего логирования.

        Роль: сохраняет storage, через который идут все операции с файлом.
        """
        self._storage = storage
        self._log_manager = log_manager

    def get_tasks(self) -> list[PlannerTask]:
        """Возвращает список задач, отсортированный по task_id убыв (новые сверху)."""
        tasks = self._storage.get_all()
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)

    def create_task(self, title: str, description: str = "",
                    priority: TaskPriority = TaskPriority.MEDIUM) -> PlannerTask:
        """Создаёт задачу, генерирует task_id, сохраняет.

        Вход: title, description, priority.
        Выход: созданный PlannerTask.
        Ошибка: ValueError, если title пустой.
        """
        if not title or not title.strip():
            raise ValueError("Название задачи не может быть пустым")
        task_id = self._generate_task_id()
        task = PlannerTask(
            task_id=task_id,
            title=title.strip(),
            description=description,
            priority=priority,
            status=TaskStatus.ACTIVE,
            created_date=date.today().strftime("%d.%m.%Y"),
            completed_date=None,
        )
        self._storage.add(task)
        return task

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

    def _generate_task_id(self) -> int:
        """Генерирует task_id формата YYYYMMDDNNN.

        NNN = max(NNN существующих за сегодня, default=0) + 1.
        Дырки от удалённых задач не заполняются.
        """
        today_str = date.today().strftime("%Y%m%d")
        existing = self._storage.get_all()
        today_nnn = [
            t.task_id % 1000
            for t in existing
            if str(t.task_id).startswith(today_str)
        ]
        max_nnn = max(today_nnn, default=0)
        return int(today_str) * 1000 + max_nnn + 1

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
