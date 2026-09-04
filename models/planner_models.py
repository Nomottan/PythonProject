import uuid
from datetime import datetime, date, timedelta


class RepeatRule:
    """
    Правила повторения задачи.
    Поддерживаемые типы:
      - daily: каждый interval_days дней (по умолчанию 1)
      - weekly: в указанные дни недели (0=Пн, 1=Вт, ..., 6=Вс)
      - monthly: конкретные числа месяца или по дню недели в месяце
      - interval: раз в interval_days дней
    """
    def __init__(self, repeat_type="none", interval_days=1,
                 weekdays=None, monthly_type=None, days_of_month=None,
                 week_number=None, weekday=None, max_occurrences=None):
        self.repeat_type = repeat_type
        self.interval_days = interval_days
        self.weekdays = weekdays if weekdays is not None else []
        self.monthly_type = monthly_type  # "specific_day" или "weekday_pattern"
        self.days_of_month = days_of_month if days_of_month is not None else []
        self.week_number = week_number    # 1-5 (5 = последняя неделя месяца)
        self.weekday = weekday            # 0-6
        self.max_occurrences = max_occurrences
        self.occurrences_generated = 0

    def next_occurrence(self, after_date: date) -> date | None:
        """
        Возвращает ближайшую дату, строго большую after_date, удовлетворяющую правилу.
        Если лимит исчерпан, возвращает None.
        """
        if self.is_finished():
            return None

        if self.repeat_type == "daily":
            next_date = after_date + timedelta(days=self.interval_days)
        elif self.repeat_type == "interval":
            next_date = after_date + timedelta(days=self.interval_days)
        elif self.repeat_type == "weekly":
            # Ищем следующий день, попадающий в список weekdays
            next_date = after_date
            while True:
                next_date += timedelta(days=1)
                if next_date.weekday() in self.weekdays:
                    break
        elif self.repeat_type == "monthly":
            next_date = self._next_monthly(after_date)
        else:
            return None

        return next_date

    def _next_monthly(self, after_date: date) -> date | None:
        """Вычисляет следующую дату для ежемесячного повторения."""
        if self.monthly_type == "specific_day":
            # Сортируем дни месяца
            valid_days = sorted(self.days_of_month)
            if not valid_days:
                return None
            # Пробуем в текущем месяце после after_date
            year, month = after_date.year, after_date.month
            for day in valid_days:
                try:
                    candidate = date(year, month, day)
                    if candidate > after_date:
                        return candidate
                except ValueError:
                    continue
            # Если не нашли, переходим к следующему месяцу
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            for day in valid_days:
                try:
                    return date(year, month, day)
                except ValueError:
                    continue
            return None
        elif self.monthly_type == "weekday_pattern":
            if self.week_number is None or self.weekday is None:
                return None
            # Вычисляем день недели в указанной неделе месяца
            # week_number 1-4: первый/второй/третий/четвертый
            # week_number 5: последний
            # Начинаем с текущего месяца
            year, month = after_date.year, after_date.month
            while True:
                candidate = self._nth_weekday_of_month(year, month, self.week_number, self.weekday)
                if candidate and candidate > after_date:
                    return candidate
                year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        return None

    @staticmethod
    def _nth_weekday_of_month(year, month, week_number, weekday):
        """Возвращает дату n-го по счёту weekday месяца."""
        if week_number == 5:
            # Последний weekday месяца
            last_day = date(year, month, 1) + timedelta(days=31)
            last_day = last_day.replace(day=1) - timedelta(days=1)
            while last_day.month != month or last_day.weekday() != weekday:
                last_day -= timedelta(days=1)
            return last_day
        else:
            # Первый weekday месяца
            first_day = date(year, month, 1)
            offset = (weekday - first_day.weekday()) % 7
            result = first_day + timedelta(days=offset + (week_number - 1) * 7)
            if result.month != month:
                return None
            return result

    def is_finished(self) -> bool:
        """Проверяет, исчерпан ли лимит повторений."""
        if self.max_occurrences is not None:
            return self.occurrences_generated >= self.max_occurrences
        return False

    def to_dict(self) -> dict:
        return {
            "repeat_type": self.repeat_type,
            "interval_days": self.interval_days,
            "weekdays": self.weekdays,
            "monthly_type": self.monthly_type,
            "days_of_month": self.days_of_month,
            "week_number": self.week_number,
            "weekday": self.weekday,
            "max_occurrences": self.max_occurrences,
            "occurrences_generated": self.occurrences_generated
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RepeatRule':
        return cls(
            repeat_type=data.get("repeat_type", "none"),
            interval_days=data.get("interval_days", 1),
            weekdays=data.get("weekdays", []),
            monthly_type=data.get("monthly_type"),
            days_of_month=data.get("days_of_month", []),
            week_number=data.get("week_number"),
            weekday=data.get("weekday"),
            max_occurrences=data.get("max_occurrences")
        )


class PlannerTask:
    """Модель задачи (шаблон или экземпляр)."""

    def __init__(self, title: str, description: str = "",
                 task_type: str = "one_time", priority: int = 3,
                 repeat_rule: RepeatRule | None = None,
                 deadline: datetime | None = None,
                 deadline_duration: dict | None = None,
                 created_at: datetime | None = None,
                 is_template: bool = True,
                 parent_id: str | None = None,
                 status: str = "active"):
        self.id = str(uuid.uuid4())
        self.title = title
        self.description = description
        self.task_type = task_type   # "one_time", "deadline", "recurring", "recurring_deadline"
        self.priority = priority     # 1..5
        self.repeat_rule = repeat_rule
        self.deadline = deadline
        self.deadline_duration = deadline_duration
        self.created_at = created_at or datetime.now()
        self.next_generation_date = None
        self.paused = False
        self.is_template = is_template
        self.parent_id = parent_id
        self.status = status
        self.archived_at = None

    def generate_instance(self) -> 'PlannerTask':
        """
        Создаёт одноразовый экземпляр на основе шаблона.
        """
        instance = PlannerTask(
            title=self.title,
            description=self.description,
            task_type=self.task_type,
            priority=self.priority,
            deadline_duration=self.deadline_duration,
            created_at=datetime.now(),
            is_template=False,
            parent_id=self.id
        )
        # Если у шаблона есть длительность дедлайна, вычисляем конечный deadline
        if self.deadline_duration:
            days = self.deadline_duration.get("days", 0)
            hours = self.deadline_duration.get("hours", 0)
            instance.deadline = instance.created_at + timedelta(days=days, hours=hours)
        else:
            instance.deadline = self.deadline  # если шаблон одноразовый с конкретной датой (не повторяющийся)
        instance.repeat_rule = None
        instance.next_generation_date = None
        return instance

    def should_generate(self, current_date: date) -> bool:
        """Проверяет, нужно ли породить экземпляр в указанную дату."""
        if not self.is_template:
            return False
        if self.paused:
            return False
        if self.next_generation_date is None:
            return False
        if self.next_generation_date > current_date:
            return False
        return True

    def toggle_pause(self):
        """Переключает паузу для шаблона."""
        self.paused = not self.paused

    def mark_completed(self):
        self.status = "completed"
        self.archived_at = datetime.now()

    def mark_deleted_template(self):
        self.status = "deleted_template"
        self.archived_at = datetime.now()

    def mark_expired_not_completed(self):
        self.status = "expired_not_completed"
        self.archived_at = datetime.now()

    def set_next_generation_date(self, value: date | None):
        self.next_generation_date = value

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "priority": self.priority,
            "repeat_rule": self.repeat_rule.to_dict() if self.repeat_rule else None,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "deadline_duration": self.deadline_duration,
            "created_at": self.created_at.isoformat(),
            "next_generation_date": self.next_generation_date.isoformat() if self.next_generation_date else None,
            "paused": self.paused,
            "is_template": self.is_template,
            "parent_id": self.parent_id,
            "status": self.status,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PlannerTask':
        task = cls(
            title=data["title"],
            description=data.get("description", ""),
            task_type=data.get("task_type", "one_time"),
            priority=data.get("priority", 3),
            repeat_rule=RepeatRule.from_dict(data["repeat_rule"]) if data.get("repeat_rule") else None,
            deadline=datetime.fromisoformat(data["deadline"]) if data.get("deadline") else None,
            deadline_duration=data.get("deadline_duration"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            is_template=data.get("is_template", True),
            parent_id=data.get("parent_id"),
            status=data.get("status", "active")
        )
        task.id = data.get("id", task.id)
        task.next_generation_date = date.fromisoformat(data["next_generation_date"]) if data.get("next_generation_date") else None
        task.paused = data.get("paused", False)
        task.archived_at = datetime.fromisoformat(data["archived_at"]) if data.get("archived_at") else None
        return task

class TaskFilter:
    """
    Фильтр задач по различным критериям.
    Все критерии опциональны; если критерий не задан (None или пустой список),
    он не применяется.
    """
    def __init__(self,
                 task_type: list[str] | None = None,
                 priority: list[int] | None = None,
                 status: list[str] | None = None,
                 created_from: date | None = None,
                 created_to: date | None = None,
                 deadline_from: date | None = None,
                 deadline_to: date | None = None,
                 next_generation_from: date | None = None,
                 next_generation_to: date | None = None,
                 archived_from: date | None = None,
                 archived_to: date | None = None):
        self.task_type = task_type
        self.priority = priority
        self.status = status
        self.created_from = created_from
        self.created_to = created_to
        self.deadline_from = deadline_from
        self.deadline_to = deadline_to
        self.next_generation_from = next_generation_from
        self.next_generation_to = next_generation_to
        self.archived_from = archived_from
        self.archived_to = archived_to

    def apply(self, tasks: list['PlannerTask']) -> list['PlannerTask']:
        """Возвращает отфильтрованный список задач."""
        result = []

        for task in tasks:
            if self.task_type and task.task_type not in self.task_type:
                continue
            if self.priority and task.priority not in self.priority:
                continue
            if self.status and task.status not in self.status:
                continue

            # Диапазоны дат
            if self.created_from and task.created_at.date() < self.created_from:
                continue
            if self.created_to and task.created_at.date() > self.created_to:
                continue

            if self.deadline_from:
                if not task.deadline or task.deadline.date() < self.deadline_from:
                    continue
            if self.deadline_to:
                if not task.deadline or task.deadline.date() > self.deadline_to:
                    continue

            if self.next_generation_from:
                if not task.next_generation_date or task.next_generation_date < self.next_generation_from:
                    continue
            if self.next_generation_to:
                if not task.next_generation_date or task.next_generation_date > self.next_generation_to:
                    continue

            if self.archived_from:
                if not task.archived_at or task.archived_at.date() < self.archived_from:
                    continue
            if self.archived_to:
                if not task.archived_at or task.archived_at.date() > self.archived_to:
                    continue

            result.append(task)

        return result

class TaskSorter:
    """
    Сортировка задач по заданному полю.
    Поддерживаемые поля:
      - "created_at" (дата создания)
      - "deadline" (дедлайн)
      - "priority" (приоритет)
      - "title" (название)
      - "task_type" (тип задачи)
      - "next_generation_date" (дата следующей генерации)
      - "archived_at" (дата архивации)
      - "status" (статус)
    """
    def __init__(self, sort_by: str = "created_at", ascending: bool = True):
        self.sort_by = sort_by
        self.ascending = ascending

    def sort(self, tasks: list['PlannerTask']) -> list['PlannerTask']:
        """Возвращает отсортированную копию списка задач."""
        # Определяем ключ сортировки с учётом None значений
        def key_func(task: 'PlannerTask'):
            value = getattr(task, self.sort_by, None)

            if value is None:
                # Для дат: None помещаем в конец при возрастании, в начало при убывании
                if self.sort_by in ("deadline", "next_generation_date", "archived_at"):
                    if self.ascending:
                        return (1, None)
                    else:
                        return (0, None)
                # Для остальных полей используем пустую строку или минимальное число
                if self.sort_by == "title":
                    return ""
                if self.sort_by in ("priority", "occurrences_generated"):
                    return float('-inf') if self.ascending else float('inf')
                return ""

            if isinstance(value, date):
                return (0, value)
            if isinstance(value, str):
                return value.lower()
            return value

        return sorted(tasks, key=key_func, reverse=not self.ascending)