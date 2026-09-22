"""
Сервис генерации экземпляров регулярных задач.
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional

from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from services.planner_service import PlannerService


class PlannerRecurrenceService:
    """Сервис генерации экземпляров регулярных задач.

    Роль: создаёт экземпляры для генераторов, у которых наступила
          next_generation_date. Вызывается при запуске приложения
          и по таймеру (30 минут).
    """

    def __init__(self, planner_service: PlannerService, log_manager=None):
        self._service = planner_service
        self._log_manager = log_manager

    def generate_due_instances(self) -> int:
        """Создаёт экземпляры для всех due-генераторов.

        Выход: количество созданных экземпляров.
        """
        today = date.today()
        count = 0
        for gen in self._service.get_recurring_tasks():
            # Пропускаем на паузе.
            if gen.status == TaskStatus.PAUSED:
                continue

            # Если уже есть активный экземпляр — генератор в WAITING.
            active = self._service.get_active_instances(gen.task_id)
            if active:
                if gen.status == TaskStatus.ACTIVE:
                    self._service.update_status(gen.task_id, TaskStatus.WAITING)
                continue

            # Проверяем next_generation_date.
            if gen.next_generation_date:
                try:
                    next_date = datetime.strptime(
                        gen.next_generation_date, "%d.%m.%Y"
                    ).date()
                except ValueError:
                    continue
                if next_date > today:
                    continue

            # Создаём экземпляр.
            self._create_instance(gen)
            count += 1

            # Обновляем next_generation_date.
            self._update_next_date(gen, today)

            # Если генератор был WAITING — возвращаем в ACTIVE.
            if gen.status == TaskStatus.WAITING:
                self._service.update_status(gen.task_id, TaskStatus.ACTIVE)
        return count

    def _create_instance(self, generator: PlannerTask) -> PlannerTask:
        """Создаёт экземпляр с priority=RECURRING, task_type=INSTANCE."""
        return self._service.create_task(
            title=generator.title,
            description=generator.description,
            priority=TaskPriority.RECURRING,
            spawner_task=generator.task_id,
            task_type=TaskType.INSTANCE,
        )

    def _update_next_date(self, generator: PlannerTask, today: date) -> None:
        """Вычисляет и сохраняет новую next_generation_date."""
        new_date = self.compute_next_date(generator, today)
        generator.next_generation_date = (
            new_date.strftime("%d.%m.%Y") if new_date else None
        )
        self._service._storage.save()

    def compute_next_date(self, task: PlannerTask,
                          from_date: date) -> Optional[date]:
        """Вычисляет следующую дату генерации.

        Логика:
            every_n_days — from_date + N дней.
            weekdays — следующий подходящий день недели.
            monthdays — следующее число месяца.
        """
        if not task.is_generator():
            return None

        rec_type = task.recurrence_type

        if rec_type == "every_n_days":
            n = task.recurrence_value or 1
            return from_date + timedelta(days=n)

        if rec_type == "weekdays":
            weekdays = task.recurrence_weekdays or []
            if not weekdays:
                return None
            for offset in range(1, 8):
                d = from_date + timedelta(days=offset)
                if d.weekday() in weekdays:
                    return d
            return None

        if rec_type == "monthdays":
            monthdays = sorted(task.recurrence_monthdays or [])
            if not monthdays:
                return None
            y, m = from_date.year, from_date.month
            for _ in range(24):
                for day in monthdays:
                    try:
                        candidate = date(y, m, day)
                    except ValueError:
                        if task.recurrence_use_last_day:
                            last_day = calendar.monthrange(y, m)[1]
                            candidate = date(y, m, last_day)
                        else:
                            continue
                    if candidate > from_date:
                        return candidate
                m += 1
                if m > 12:
                    m = 1
                    y += 1
            return None

        return None