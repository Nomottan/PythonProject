"""
Модель задачи планировщика.

Модуль содержит чистую модель данных и два Enum-а для статуса и приоритета.
Никакой бизнес-логики: генерация task_id, подстановка дат, переходы статусов —
всё это на стороне сервиса (PlannerService). Модель — контейнер для полей
и умеет сериализоваться/десериализоваться в JSON.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    """Статус задачи.

    Значения — человекочитаемые строки, которые пишутся в JSON как есть.
    """
    ACTIVE = "Активная"
    COMPLETED = "Выполнена"
    CANCELLED = "Отменена"
    OVERDUE = "Просрочено"
    PAUSED = "Пауза"
    WAITING = "Ожидание"

    @property
    def display_name(self) -> str:
        """Человекочитаемое имя для отображения в UI."""
        return self.value

class TaskType(Enum):
    """Тип задачи.

    REGULAR — обычная задача, созданная вручную.
    DEADLINE — задача с дедлайном.
    RECURRING — генератор экземпляров (регулярная).
    INSTANCE — экземпляр, порождённый генератором.
    """
    REGULAR = "regular"
    DEADLINE = "deadline"
    RECURRING = "recurring"
    INSTANCE = "instance"

    @property
    def display_name(self) -> str:
        return {
            "regular": "Обычная",
            "deadline": "Дедлайн",
            "recurring": "Регулярная",
            "instance": "Экземпляр",
        }[self.value]

class TaskPriority(Enum):
    """Приоритет задачи.

    1 — самый низкий, 5 — регулярная. Значения — числа, пишутся в JSON.
    """
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    DEADLINE = 4
    RECURRING = 5

    @property
    def display_name(self) -> str:
        return {
            1: "Низкий",
            2: "Средний",
            3: "Высокий",
            4: "Дедлайн",
            5: "Регулярная",
        }[self.value]

class PlannerTask:
    """Модель задачи планировщика.

    Чистый контейнер данных. Генерация task_id, подстановка дат,
    управление переходами статусов — на стороне сервиса.

    Поля:
        task_id: int — целое, формат YYYYMMDDNNN (например, 20260916001).
                       Генерируется снаружи сервисом.
        title: str — название задачи.
        description: str — подробное описание.
        priority: TaskPriority — приоритет (по умолчанию MEDIUM).
        status: TaskStatus — статус (по умолчанию ACTIVE).
        created_date: str — дата создания в формате %d.%m.%Y.
        completed_date: Optional[str] — дата завершения/отмены в формате
                        %d.%m.%Y. None для ACTIVE.
        spawner_task: Optional[int] — task_id архивной задачи, из которой
                      была порождена эта задача при восстановлении COMPLETED.
                      None для обычных задач, созданных вручную.
        deadline_datetime: Optional[str] — дата и время дедлайна в формате
                      "%d.%m.%Y %H:%M". None для не-дедлайн задач.
        created_datetime: Optional[str] — точный момент создания в формате
                      "%d.%m.%Y %H:%M". None для старых записей.
        task_type: TaskType — тип задачи. По умолчанию REGULAR.
        recurrence_type: Optional[str] — правило повторения: "every_n_days",
                      "weekdays", "monthdays". None для не-регулярных.
        recurrence_value: Optional[int] — N для every_n_days.
        recurrence_weekdays: Optional[list] — номера дней недели (0=пн..6=вс).
        recurrence_monthdays: Optional[list] — числа месяца (1–31).
        recurrence_use_last_day: bool — если число не существует в месяце,
                      использовать последний день месяца.
        next_generation_date: Optional[str] — дата следующей генерации
                      экземпляра ("%d.%m.%Y"). None для не-генераторов.
    """

    def __init__(self, task_id: int, title: str,
                 description: str = "",
                 priority: TaskPriority = TaskPriority.MEDIUM,
                 status: TaskStatus = TaskStatus.ACTIVE,
                 created_date: str = "",
                 completed_date: Optional[str] = None,
                 spawner_task: Optional[int] = None,
                 deadline_datetime: Optional[str] = None,
                 created_datetime: Optional[str] = None,
                 task_type: TaskType = TaskType.REGULAR,
                 recurrence_type: Optional[str] = None,
                 recurrence_value: Optional[int] = None,
                 recurrence_weekdays: Optional[list] = None,
                 recurrence_monthdays: Optional[list] = None,
                 recurrence_use_last_day: bool = False,
                 next_generation_date: Optional[str] = None):
        """Конструктор.

        Вход:
            task_id — обязательный, целое.
            title — обязательный, строка.
            description — по умолчанию "".
            priority — по умолчанию MEDIUM.
            status — по умолчанию ACTIVE.
            created_date — по умолчанию "".
            completed_date — по умолчанию None.
            spawner_task — task_id архивной задачи-родителя. По умолчанию None.

        Роль: сохраняет поля без валидации. Ответственность за корректность
              переданных значений — на стороне сервиса.
        """
        self.task_id = task_id
        self.title = title
        self.description = description
        self.priority = priority
        self.status = status
        self.created_date = created_date
        self.completed_date = completed_date
        self.spawner_task = spawner_task
        self.deadline_datetime = deadline_datetime
        self.created_datetime = created_datetime
        self.task_type = task_type
        self.recurrence_type = recurrence_type
        self.recurrence_value = recurrence_value
        self.recurrence_weekdays = recurrence_weekdays
        self.recurrence_monthdays = recurrence_monthdays
        self.recurrence_use_last_day = recurrence_use_last_day
        self.next_generation_date = next_generation_date

    def to_dict(self) -> dict:
        """Сериализация в примитивы для JSON.

        Выход: dict с полями task_id, title, description, priority (число),
               status (строка), created_date, completed_date.

        Роль: Enum-значения разворачиваются в .value; даты — строки как есть.
        """
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "created_date": self.created_date,
            "completed_date": self.completed_date,
            "spawner_task": self.spawner_task,
            "deadline_datetime": self.deadline_datetime,
            "created_datetime": self.created_datetime,
            "task_type": self.task_type.value,
            "recurrence_type": self.recurrence_type,
            "recurrence_value": self.recurrence_value,
            "recurrence_weekdays": self.recurrence_weekdays,
            "recurrence_monthdays": self.recurrence_monthdays,
            "recurrence_use_last_day": self.recurrence_use_last_day,
            "next_generation_date": self.next_generation_date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlannerTask":
        """Восстановление объекта из dict.

        Вход: data — словарь, например результат json.load.
        Выход: объект PlannerTask.

        Обработка ошибок:
            - Неизвестный priority → fallback на TaskPriority.LOW.
            - Неизвестный status → fallback на TaskStatus.CANCELLED.
            - Отсутствует task_id или title → KeyError (уйдёт наверх).

        Роль: обратное преобразование к to_dict. Мягкое поведение при
              неизвестных Enum-значениях — чтобы не терять задачу целиком
              из-за одной опечатки в JSON.
        """
        # REPLACE: priority — при неизвестном значении подставляем LOW.
        try:
            priority = TaskPriority(data["priority"])
        except (ValueError, KeyError):
            priority = TaskPriority.LOW

        try:
            status = TaskStatus(data["status"])
        except (ValueError, KeyError):
            status = TaskStatus.CANCELLED

            # NEW: task_type — при неизвестном значении подставляем REGULAR.
        try:
            task_type = TaskType(data.get("task_type", "regular"))
        except (ValueError, KeyError):
            task_type = TaskType.REGULAR

            # task_id и title обязательны — KeyError уйдёт наверх.
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            description=data.get("description", ""),
            priority=priority,
            status=status,
            created_date=data.get("created_date", ""),
            completed_date=data.get("completed_date"),
            spawner_task=data.get("spawner_task"),
            deadline_datetime=data.get("deadline_datetime"),
            created_datetime=data.get("created_datetime"),
            task_type=task_type,
            recurrence_type=data.get("recurrence_type"),
            recurrence_value=data.get("recurrence_value"),
            recurrence_weekdays=data.get("recurrence_weekdays"),
            recurrence_monthdays=data.get("recurrence_monthdays"),
            recurrence_use_last_day=data.get("recurrence_use_last_day", False),
            next_generation_date=data.get("next_generation_date"),
        )

    def get_deadline_datetime(self) -> Optional[datetime]:
        """Возвращает момент дедлайна.

        Парсит self.deadline_datetime в формате "%d.%m.%Y %H:%M".
        Если строка пустая или не парсится — возвращает None.
        """
        if not self.deadline_datetime:
            return None
        try:
            return datetime.strptime(self.deadline_datetime, "%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            return None

    def get_created_datetime(self) -> Optional[datetime]:
        """Возвращает момент создания.

        Если self.created_datetime есть — парсит "%d.%m.%Y %H:%M".
        Иначе — fallback на начало дня self.created_date ("%d.%m.%Y").
        """
        if self.created_datetime:
            try:
                return datetime.strptime(self.created_datetime, "%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                pass
        if self.created_date:
            try:
                return datetime.strptime(self.created_date, "%d.%m.%Y")
            except (ValueError, TypeError):
                pass
        return None

    def is_overdue(self) -> bool:
        """True, если задача дедлайн и текущее время > дедлайна."""
        if self.priority != TaskPriority.DEADLINE:
            return False
        dl = self.get_deadline_datetime()
        if dl is None:
            return False
        return datetime.now() > dl

    def is_generator(self) -> bool:
        """True, если задача — генератор экземпляров (регулярная)."""
        return self.task_type == TaskType.RECURRING

    def is_recurring_instance(self) -> bool:
        """True, если задача — экземпляр, порождённый генератором."""
        return self.task_type == TaskType.INSTANCE