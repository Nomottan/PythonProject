"""
Модель задачи планировщика.

Модуль содержит чистую модель данных и два Enum-а для статуса и приоритета.
Никакой бизнес-логики: генерация task_id, подстановка дат, переходы статусов —
всё это на стороне сервиса (PlannerService). Модель — контейнер для полей
и умеет сериализоваться/десериализоваться в JSON.
"""
from datetime import date
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    """Статус задачи.

    Значения — человекочитаемые строки, которые пишутся в JSON как есть.
    """
    ACTIVE = "Активная"
    COMPLETED = "Выполнена"
    CANCELLED = "Отменена"

    @property
    def display_name(self) -> str:
        """Человекочитаемое имя для отображения в UI."""
        return self.value


class TaskPriority(Enum):
    """Приоритет задачи.

    1 — самый важный, 3 — наименее важный. Значения — числа, пишутся в JSON.
    """
    HIGH = 1
    MEDIUM = 2
    LOW = 3

    @property
    def display_name(self) -> str:
        """Человекочитаемое имя для отображения в UI."""
        return {1: "Высокий", 2: "Средний", 3: "Низкий"}[self.value]

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
    """

    def __init__(self, task_id: int, title: str,
                 description: str = "",
                 priority: TaskPriority = TaskPriority.MEDIUM,
                 status: TaskStatus = TaskStatus.ACTIVE,
                 created_date: str = "",
                 completed_date: Optional[str] = None):
        """Конструктор.

        Вход:
            task_id — обязательный, целое.
            title — обязательный, строка.
            description — по умолчанию "".
            priority — по умолчанию MEDIUM.
            status — по умолчанию ACTIVE.
            created_date — по умолчанию "".
            completed_date — по умолчанию None.

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
        )