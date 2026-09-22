from PySide6.QtCore import QObject, Signal
from datetime import date, datetime, timedelta
from typing import Optional
from utils.task_id_generator import TaskIdGenerator
from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from storage.planner_task_storage import PlannerTaskStorage
from utils.recurrence_utils import RecurrenceCalculator



class PlannerService(QObject):
    """Сервис планировщика задач.

    Роль: создаёт задачи, генерирует task_id, читает/пишет через storage.
    Не знает про UI. Задачи отдаёт отсортированными по task_id убыв.
    """

    tasks_changed = Signal()

    def __init__(self, storage: PlannerTaskStorage,
                 archive_storage=None, log_manager=None):
        super().__init__()
        self._storage = storage
        self._archive_storage = archive_storage
        self._log_manager = log_manager

    def get_tasks(self) -> list[PlannerTask]:
        """Возвращает список задач, отсортированный по task_id убыв (новые сверху)."""
        tasks = self._storage.get_all()
        return sorted(tasks, key=lambda t: t.task_id, reverse=True)

    def create_task(self, title: str, description: str = "",
                    priority: TaskPriority = TaskPriority.MEDIUM,
                    spawner_task: Optional[int] = None,
                    deadline_datetime: Optional[str] = None,
                    task_type: TaskType = TaskType.REGULAR,
                    recurrence_data: Optional[dict] = None) -> PlannerTask:
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
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
        if task_type == TaskType.RECURRING and recurrence_data:
            rec_type = recurrence_data.get("type")
            rec_value = recurrence_data.get("value")
            rec_weekdays = recurrence_data.get("weekdays")
            rec_monthdays = recurrence_data.get("monthdays")
            rec_use_last = recurrence_data.get("use_last_day", False)
        else:
            rec_type = rec_value = rec_weekdays = rec_monthdays = None
            rec_use_last = False
        if priority == TaskPriority.DEADLINE and not deadline_datetime:
            fallback_dt = datetime.now() + timedelta(days=1)
            deadline_datetime = fallback_dt.strftime("%d.%m.%Y %H:%M")
        next_date = date.today().strftime("%d.%m.%Y") if task_type == TaskType.RECURRING else None
        task = PlannerTask(
            task_id=task_id,
            title=title.strip(),
            description=description,
            priority=priority,
            status=TaskStatus.ACTIVE,
            created_date=date.today().strftime("%d.%m.%Y"),
            completed_date=None,
            spawner_task=spawner_task,
            deadline_datetime=deadline_datetime if priority == TaskPriority.DEADLINE else None,
            created_datetime=now_str,
            task_type=task_type,
            recurrence_type=rec_type,
            recurrence_value=rec_value,
            recurrence_weekdays=rec_weekdays,
            recurrence_monthdays=rec_monthdays,
            recurrence_use_last_day=rec_use_last,
            next_generation_date=next_date,
        )
        self._storage.add(task)
        self.tasks_changed.emit()
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

        # NEW: если архивировали экземпляр — переводим его генератора
        # в WAITING. Делаем это строго после удаления экземпляра из
        # storage, иначе генератор «увидел» бы ещё живой экземпляр.
        # Если генератор в PAUSED — не трогаем: пользователь явно
        # остановил его, и наша архивация не должна снимать паузу.
        if target.is_recurring_instance() and target.spawner_task is not None:
            for gen in self._storage.get_all():
                if (gen.task_id == target.spawner_task
                        and gen.is_generator()):
                    if gen.status == TaskStatus.ACTIVE:
                        gen.status = TaskStatus.WAITING
                        self._storage.save()
                    break

        self.tasks_changed.emit()
        return True

    def check_overdue(self) -> bool:
        """Проверяет активные задачи, помечает просроченные дедлайны.

        Выход: True — были изменения; False — нет.

        Роль: вызывается таймером контроллера (60 сек). Сигнал НЕ
              испускает: вызывающий код сам решает, обновлять ли
              раскладку слотов (иначе карусели пересоздаются каждую
              минуту).
        """
        changed = False
        for task in self._storage.get_all():
            if task.status == TaskStatus.ACTIVE and task.is_overdue():
                task.status = TaskStatus.OVERDUE
                changed = True
        if changed:
            self._storage.save()
        return changed

    def update_status(self, task_id: int, new_status: TaskStatus) -> bool:
        """Меняет статус задачи и сохраняет.

        Вход: task_id — идентификатор; new_status — новый статус.
        Выход: True — задача найдена и обновлена; False — не найдена.

        Роль: единая точка смены статуса. При переходе
              PAUSED → WAITING у генератора пересчитывается
              next_generation_date с «догоном» пропущенных дат —
              пользователь мог стоять на паузе долго.

        Порядок действий: пересчёт → сохранение → эмит.
        Один эмит на всю операцию — подписчики (мини-планировщик,
        окно планировщика) не мигнут лишний раз.
        """
        for task in self._storage.get_all():
            if task.task_id == task_id:
                old_status = task.status
                task.status = new_status

                # NEW: выход из паузы — «догон» пропущенных дат.
                if (old_status == TaskStatus.PAUSED
                        and new_status == TaskStatus.WAITING
                        and task.is_generator()):
                    catch_up = RecurrenceCalculator.catch_up_date(
                        task, date.today()
                    )
                    task.next_generation_date = (
                        catch_up.strftime("%d.%m.%Y") if catch_up else None
                    )

                self._storage.save()
                self.tasks_changed.emit()
                return True
        return False

    def get_recurring_tasks(self) -> list[PlannerTask]:
        """Возвращает все активные генераторы регулярных задач."""
        return [t for t in self._storage.get_all() if t.is_generator()]

    def get_active_instances(self, parent_id: int) -> list[PlannerTask]:
        """Активные экземпляры конкретного генератора.

        Вход: parent_id — task_id генератора.
        Выход: список PlannerTask с spawner_task == parent_id
               и статусом ACTIVE.

        Роль: по списку сервис генерации определяет, есть ли у
              генератора живой экземпляр. Экземпляры в статусе
              WAITING не бывают — этот статус только у генераторов.
              Фильтр только по ACTIVE — согласно спецификации
              жизненного цикла.
        """
        return [
            t for t in self._storage.get_all()
            if t.spawner_task == parent_id
               and t.status == TaskStatus.ACTIVE
               and t.is_recurring_instance()
        ]

    def archive_stale_instances(self) -> int:
        """Архивирует активные экземпляры, не завершённые в день генерации.

        Выход: количество заархивированных экземпляров.
        Роль: вызывается при запуске приложения — «вчерашние» экземпляры
              автоматически уходят в архив как CANCELLED.
        """
        today = date.today().strftime("%d.%m.%Y")
        count = 0
        for task in self._storage.get_all():
            if not task.is_recurring_instance():
                continue
            if (task.created_date != today
                    and task.status in (TaskStatus.ACTIVE, TaskStatus.WAITING)):
                self.archive_task(task.task_id, TaskStatus.CANCELLED)
                count += 1
        return count

    def update_task(self, task_id: int,
                    title: Optional[str] = None,
                    description: Optional[str] = None,
                    priority: Optional[TaskPriority] = None,
                    deadline_datetime: Optional[str] = None) -> bool:
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
            return False

        if title is not None:
            target.title = title.strip()
        if description is not None:
            target.description = description

        if priority is not None:
            target.priority = priority
            if priority != TaskPriority.DEADLINE:
                # Не дедлайн — обнуляем дату.
                target.deadline_datetime = None
            elif deadline_datetime:
                target.deadline_datetime = deadline_datetime
            elif not target.deadline_datetime:
                # Переключили на DEADLINE без даты, даты не было — fallback.
                fallback_dt = datetime.now() + timedelta(days=1)
                target.deadline_datetime = fallback_dt.strftime("%d.%m.%Y %H:%M")
        elif deadline_datetime:
            # Приоритет не меняется, но дату обновили явно.
            target.deadline_datetime = deadline_datetime

        self._storage.save()
        return True

    def get_priorities(self) -> list[str]:
        """Возвращает приоритеты в порядке убывания важности."""
        return [
            TaskPriority.RECURRING.display_name,
            TaskPriority.DEADLINE.display_name,
            TaskPriority.HIGH.display_name,
            TaskPriority.MEDIUM.display_name,
            TaskPriority.LOW.display_name,
        ]

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
