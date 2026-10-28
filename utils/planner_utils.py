"""
Утилиты планировщика: поиск, генерация id, расчёт дат.

Модуль собирает три вещи, которые раньше жили отдельно:
    TaskFinder          — поиск задачи по id в списке.
    TaskIdGenerator     — генерация уникального task_id.
    RecurrenceCalculator — расчёт дат генерации экземпляров.

Зачем объединять:
    Все три — утилиты планировщика, используются вместе в
    PlannerService и PlannerRecurrenceService. Разнеся их по
    разным файлам, мы плодим циклические импорты и неудобные
    пути. Один модуль — одна точка входа.

Использование:
    from utils.planner_utils import (
        TaskFinder, TaskIdGenerator, RecurrenceCalculator,
    )
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional


class TaskFinder:
    """Поиск задач по идентификатору.

    Роль: единая точка поиска. Используется сервисами планировщика
          вместо ручных циклов for.
    """

    @staticmethod
    def find_by_id(tasks: list, task_id: int):
        """Возвращает задачу с указанным task_id или None.

        Вход:
            tasks — список PlannerTask.
            task_id — идентификатор для поиска.

        Выход: PlannerTask или None.
        Роль: линейный поиск. Списки в планировщике маленькие
              (десятки записей), оптимизация не нужна.
        """
        for task in tasks:
            if task.task_id == task_id:
                return task
        return None


class TaskIdGenerator:
    """Генератор уникальных task_id.

    Формат: YYYYMMDDNNN, где YYYYMMDD — сегодняшняя дата,
            NNN — порядковый номер в пределах дня (001, 002, …).

    Роль: id должен быть уникальным в пределах хранилища. Дневной
          счётчик удобен для сортировки (новые сверху) и читаем
          глазами.
    """

    @staticmethod
    def generate(tasks: list) -> int:
        """Генерирует новый task_id на основе текущего списка задач.

        Вход: tasks — объединённый список задач (активные + архив).
        Выход: int — новый уникальный идентификатор.

        Роль: берём сегодняшнюю дату как префикс, считаем сколько
              задач с этим префиксом уже есть, добавляем 1.
              Принимает объединённый список задач (активные + архив) — оба storage,
              чтобы новый ID не совпал с уже существующим в любом из файлов.
              Раньше принимал один storage.
        """
        today_prefix = datetime.now().strftime("%Y%m%d")
        existing = tasks

        # Считаем максимальный счётчик среди задач с сегодняшним
        # префиксом. Формат: YYYYMMDDNNN → 8 цифр префикс, 3 суффикс.
        max_suffix = 0
        for task in existing:
            task_id_str = str(task.task_id)
            if len(task_id_str) == 11 and task_id_str.startswith(today_prefix):
                try:
                    suffix = int(task_id_str[8:])
                    if suffix > max_suffix:
                        max_suffix = suffix
                except ValueError:
                    continue

        new_suffix = max_suffix + 1
        return int(f"{today_prefix}{new_suffix:03d}")


class RecurrenceCalculator:
    """Калькулятор дат генерации экземпляров регулярных задач.

    Роль: единая точка вычисления next_generation_date. Используется
          PlannerRecurrenceService (при генерации) и PlannerService
          (при выходе из паузы). Вынесен в отдельный класс, чтобы
          не дублировать логику и не связывать два сервиса друг с другом.

    Почему static-методы: класс не хранит состояние — это чистая
    функция в ООП-обёртке. Создавать экземпляр ради вызова одного
    метода не имеет смысла, а наследование здесь не нужно.
    """

    @staticmethod
    def compute_next_date(task, from_date: date,
                          include_today: bool = False) -> Optional[date]:
        """Вычисляет следующую дату генерации от from_date.

        Вход:
            task — PlannerTask-генератор.
            from_date — опорная дата.
            include_today — если True и from_date сама подходит под
                            правило, вернуть её; иначе — строго
                            следующую дату после from_date.

        Выход: date или None (если правило не задано или пустое).
        """
        # Не генератор — правило повторения не применимо.
        if not task.is_generator():
            return None

        rec_type = task.recurrence_type

        match rec_type:
            case "every_n_days":
                n = task.recurrence_value or 1
                return from_date + timedelta(days=n)

            case "weekdays":
                weekdays = task.recurrence_weekdays or []
                if not weekdays:
                    return None
                if include_today and from_date.weekday() in weekdays:
                    return from_date
                for offset in range(1, 8):
                    d = from_date + timedelta(days=offset)
                    if d.weekday() in weekdays:
                        return d
                return None

            case "monthdays":
                monthdays = sorted(task.recurrence_monthdays or [])
                if not monthdays:
                    return None
                if include_today and from_date.day in monthdays:
                    return from_date
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

            case _:
                return None