"""
Сервис генерации экземпляров регулярных задач.
"""

from datetime import date, datetime
from typing import Optional

from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from services.planner_service import PlannerService
from utils.planner_utils import RecurrenceCalculator


class PlannerRecurrenceService:
    """Сервис генерации экземпляров регулярных задач.

    Роль: поддерживает жизненный цикл генераторов.
        ACTIVE  — есть живой экземпляр (создан, не завершён).
        WAITING — живого экземпляра нет, ждём next_generation_date.
        PAUSED  — пользователь остановил генерацию вручную.

        Вызывается при запуске приложения и по таймеру.
    """

    def __init__(self, planner_service: PlannerService, log_manager=None):
        self._service = planner_service
        self._log_manager = log_manager

    # ---------- Основной цикл ----------

    def generate_due_instances(self) -> int:
        """Создаёт экземпляры для всех due-генераторов.

        Выход: количество созданных экземпляров.

        Алгоритм (для каждого генератора):
            1. PAUSED — пропустить: пользователь остановил вручную.
            2. Есть живой экземпляр → генератор должен быть ACTIVE.
               Если он почему-то WAITING — синхронизируем.
            3. Нет живого экземпляра → генератор должен быть WAITING.
               Если он почему-то ACTIVE — синхронизируем.
            4. next_generation_date пустое → вычислить от today с
               include_today=True и сохранить; экземпляр не создаём —
               пусть следующий тик сам «догонит».
            5. next_generation_date <= today → создать экземпляр,
               пересчитать дату строго после today, генератор → ACTIVE.
            6. Один экземпляр на генератор за тик.
        """
        today = date.today()
        count = 0

        for gen in self._service.get_recurring_tasks():
            # 1. Пауза — не трогаем до явного возобновления.
            if gen.status == TaskStatus.PAUSED:
                continue

            # 2. Есть живой экземпляр?
            active = self._service.get_active_instances(gen.task_id)
            if active:
                # Экземпляр есть → генератор обязан быть ACTIVE.
                if gen.status != TaskStatus.ACTIVE:
                    self._service.update_status(
                        gen.task_id, TaskStatus.ACTIVE
                    )
                continue

            # 3. Живого экземпляра нет → генератор обязан быть WAITING.
            if gen.status != TaskStatus.WAITING:
                self._service.update_status(
                    gen.task_id, TaskStatus.WAITING
                )

            # 4. Нет даты — вычислим и сохраним, экземпляр не создаём.
            if not gen.next_generation_date:
                new_date = RecurrenceCalculator.compute_next_date(
                    gen, today, include_today=True
                )
                gen.next_generation_date = (
                    new_date.strftime("%d.%m.%Y") if new_date else None
                )
                # Пишем напрямую в storage: update_status эмитит сигнал,
                # а нам сейчас сигнал не нужен — только сохранить поле.
                self._service._storage.save()
                continue

            # 5. Проверяем дату.
            try:
                next_date = datetime.strptime(
                    gen.next_generation_date, "%d.%m.%Y"
                ).date()
            except ValueError:
                # Битый формат — пропускаем генератор до ручной правки.
                continue

            if next_date > today:
                # Ещё рано — ждём следующего тика.
                continue

            # 6. Дата наступила — создаём экземпляр.
            self._create_instance(gen)
            count += 1

            # Пересчитываем следующую дату строго после today.
            # include_today=False: экземпляр уже создан сегодня,
            # второй на ту же дату не нужен.
            new_date = RecurrenceCalculator.compute_next_date(
                gen, today, include_today=False
            )
            gen.next_generation_date = (
                new_date.strftime("%d.%m.%Y") if new_date else None
            )

            # Генератор → ACTIVE: у него теперь есть живой экземпляр.
            # update_status сохранит storage и эмитит tasks_changed.
            self._service.update_status(
                gen.task_id, TaskStatus.ACTIVE
            )

        return count

    # ---------- Вспомогательные ----------

    def _create_instance(self, generator: PlannerTask) -> PlannerTask:
        """Создаёт экземпляр с priority=RECURRING, task_type=INSTANCE.

        Вход: generator — генератор.
        Выход: созданный PlannerTask-экземпляр.

        Роль: инкапсулирует параметры экземпляра — все места создания
              идут через этот метод, чтобы не разъехались поля.
        """
        return self._service.create_task(
            title=generator.title,
            description=generator.description,
            priority=TaskPriority.RECURRING,
            spawner_task=generator.task_id,
            task_type=TaskType.INSTANCE,
        )

    def _update_next_date(self, generator: PlannerTask, today: date) -> None:
        """Вычисляет и сохраняет новую next_generation_date.

        Вход: generator — генератор; today — опорная дата.
        Выход: нет.
        Роль: вспомогательный метод для случаев, когда нужно пересчитать
              дату без создания экземпляра. В новом алгоритме
              generate_due_instances делает это явно, но метод оставлен
              для обратной совместимости и внешних вызовов.
        """
        new_date = RecurrenceCalculator.compute_next_date(
            generator, today, include_today=False
        )
        generator.next_generation_date = (
            new_date.strftime("%d.%m.%Y") if new_date else None
        )
        self._service._storage.save()

    def compute_next_date(self, task: PlannerTask, from_date: date,
                          include_today: bool = False) -> Optional[date]:
        """Делегирует в RecurrenceCalculator.

        Вход: task — генератор; from_date — опорная дата;
              include_today — включать ли from_date.
        Выход: date или None.

        Роль: сохранён как публичный метод сервиса для обратной
              совместимости. Внутри — просто вызов утилиты, чтобы
              не дублировать логику.
        """
        return RecurrenceCalculator.compute_next_date(
            task, from_date, include_today
        )