"""
Утилиты для работы с правилами повторения регулярных задач.

Содержит класс RecurrenceCalculator — чистый вычислитель дат.
Не знает про storage и UI; оперирует только полями PlannerTask.
"""

import calendar
from datetime import date, datetime, timedelta
from typing import Optional


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

        Роль: единая точка вычисления. Раньше жила в
              PlannerRecurrenceService.compute_next_date; вынесена
              в утилиту, чтобы PlannerService тоже мог её использовать
              без циклического импорта (PlannerService не должен
              зависеть от PlannerRecurrenceService).
        """
        # Не генератор — правило повторения не применимо.
        if not task.is_generator():
            return None

        rec_type = task.recurrence_type

        # «Каждые N дней»: from_date + N. include_today не имеет
        # смысла: цикл всегда идёт вперёд.
        if rec_type == "every_n_days":
            n = task.recurrence_value or 1
            return from_date + timedelta(days=n)

        # «Дни недели»: from_date.weekday() даёт 0=пн..6=вс.
        if rec_type == "weekdays":
            weekdays = task.recurrence_weekdays or []
            if not weekdays:
                return None
            # Если include_today и сегодня подходит — вернуть сразу.
            if include_today and from_date.weekday() in weekdays:
                return from_date
            # Иначе — следующая подходящая дата в пределах недели.
            for offset in range(1, 8):
                d = from_date + timedelta(days=offset)
                if d.weekday() in weekdays:
                    return d
            return None

        # «Определённые числа месяца»: перебираем дни в списке.
        if rec_type == "monthdays":
            monthdays = sorted(task.recurrence_monthdays or [])
            if not monthdays:
                return None
            # Если include_today и сегодняшнее число подходит — вернуть сразу.
            if include_today and from_date.day in monthdays:
                return from_date
            y, m = from_date.year, from_date.month
            # Ограничение в 24 месяца — страховка от зацикливания
            # на правилах с отсутствующими числами (например, 31
            # в феврале без use_last_day).
            for _ in range(24):
                for day in monthdays:
                    try:
                        candidate = date(y, m, day)
                    except ValueError:
                        # Числа нет в этом месяце. Если стоит
                        # use_last_day — берём последний день.
                        if task.recurrence_use_last_day:
                            last_day = calendar.monthrange(y, m)[1]
                            candidate = date(y, m, last_day)
                        else:
                            continue
                    # Строго после from_date (include_today уже обработан).
                    if candidate > from_date:
                        return candidate
                m += 1
                if m > 12:
                    m = 1
                    y += 1
            return None

        return None

    @staticmethod
    def catch_up_date(task, today: date) -> Optional[date]:
        """Догоняет пропущенные даты до today включительно.

        Вход:
            task — PlannerTask-генератор, у которого может быть
                   next_generation_date в прошлом.
            today — текущая дата.

        Выход: ближайшая дата >= today по правилу, либо None.

        Роль: при выходе из паузы пересчитывает next_generation_date,
              «пропуская» просроченные генерации. Пример: правило
              «каждые 3 дня», пользователь стоял на паузе 10 дней.
              Пропущенные 3 генерации не создаются — catch_up
              вернёт первую дату >= today.

        Логика:
            - Если next_generation_date задано — шагаем по правилу,
              пока дата не станет >= today.
            - Ограничение в 1000 итераций — страховка от зацикливания
              на некорректных правилах.
            - Fallback: если за 1000 шагов не дошли (или правило сломано)
              — считаем от today с include_today=True.
        """
        current = None
        if task.next_generation_date:
            try:
                current = datetime.strptime(
                    task.next_generation_date, "%d.%m.%Y"
                ).date()
            except ValueError:
                current = None

        # Нет валидной даты — считаем от сегодня включительно.
        if current is None:
            return RecurrenceCalculator.compute_next_date(
                task, today, include_today=True
            )

        # Шагаем по правилу, пока не «догоним» today.
        for _ in range(1000):
            if current >= today:
                return current
            current = RecurrenceCalculator.compute_next_date(
                task, current, include_today=False
            )
            if current is None:
                return None

        # Fallback — правило сломано или слишком длинная пауза.
        return RecurrenceCalculator.compute_next_date(
            task, today, include_today=True
        )