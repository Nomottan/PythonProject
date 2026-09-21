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

    @property
    def display_name(self) -> str:
        """Человекочитаемое имя для отображения в UI."""
        return self.value


class TaskPriority(Enum):
    """Приоритет задачи.

    1 — самый важный, 3 — наименее важный. Значения — числа, пишутся в JSON.
    """
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    DEADLINE = 4

    @property
    def display_name(self) -> str:
        return {
            1: "Низкий",
            2: "Средний",
            3: "Высокий",
            4: "Дедлайн",
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
    """

    def __init__(self, task_id: int, title: str,
                 description: str = "",
                 priority: TaskPriority = TaskPriority.MEDIUM,
                 status: TaskStatus = TaskStatus.ACTIVE,
                 created_date: str = "",
                 completed_date: Optional[str] = None,
                 spawner_task: Optional[int] = None,
                 deadline_datetime: Optional[str] = None,
                 created_datetime: Optional[str] = None):
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

        # REPLACE: status — при неизвестном значении подставляем CANCELLED.
        try:
            status = TaskStatus(data["status"])
        except (ValueError, KeyError):
            status = TaskStatus.CANCELLED

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