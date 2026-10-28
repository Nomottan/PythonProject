"""
Модель задачи планировщика.

Модуль содержит чистую модель данных и два Enum-а для статуса и приоритета.
Никакой бизнес-логики: генерация task_id, подстановка дат, переходы статусов —
всё это на стороне сервиса (PlannerService). Модель — контейнер для полей
и умеет сериализоваться/десериализоваться в JSON.
"""
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class ThemeKey(Enum):
    """Фиксированный Enum из 8 тем с цветом и дефолтным именем.

    Пользователь может переименовывать темы; цвета и имена — в коде.
    Хранится только diff переименований — через build_diff.
    Значения членов — строки для JSON. Цвет и имя — свойства.
    """

    class _Data:
        COLORS = {
            "white": (80, 80, 80),
            "cyan": (40, 80, 80),
            "magenta": (80, 40, 80),
            "yellow": (80, 80, 40),
            "blue": (40, 40, 80),
            "green": (40, 80, 40),
            "red": (80, 40, 40),
            "black": (40, 40, 40),
        }
        NAMES = {
            "white": "Белая",
            "cyan": "Циан",
            "magenta": "Маджента",
            "yellow": "Жёлтая",
            "blue": "Синяя",
            "green": "Зелёная",
            "red": "Красная",
            "black": "Чёрная",
        }

    WHITE = "white"
    CYAN = "cyan"
    MAGENTA = "magenta"
    YELLOW = "yellow"
    BLUE = "blue"
    GREEN = "green"
    RED = "red"
    BLACK = "black"

    @property
    def color(self) -> tuple:
        """Возвращает кортеж цвета (r, g, b)."""
        return self._Data.COLORS[self.value]

    @property
    def default_name(self) -> str:
        """Возвращает дефолтное имя темы."""
        return self._Data.NAMES[self.value]

    @classmethod
    def resolve_effective_name(cls, key, raw_names: dict) -> str:
        """Возвращает имя темы с учётом сохранённых переименований.

        Вход:
            key — элемент ThemeKey.
            raw_names — словарь сохранённых переименований.

        Выход: строка эффективного имени.

        Роль:
            Защита от невалидных данных: если raw_names не dict,
            значение не строка, пустое или длиннее 10 символов —
            возвращается дефолтное имя.
        """
        if not isinstance(key, cls):
            raise ValueError("key должен быть элементом ThemeKey")
        raw = raw_names.get(key.value) if isinstance(raw_names, dict) else None
        if raw is None:
            return key.default_name
        if not isinstance(raw, str):
            return key.default_name
        stripped = raw.strip()
        if not stripped or len(stripped) > 10:
            return key.default_name
        return stripped

    @classmethod
    def build_diff(cls, effective_names: dict) -> dict:
        """Собирает diff переименований для сохранения в JSON.

        Вход:
            effective_names — {ThemeKey: str}.

        Выход: dict {str: str} только для тем, чьё имя
               отличается от дефолтного. Порядок — по объявлению
               ThemeKey.
        """
        diff = {}
        for key in cls:
            name = effective_names.get(key)
            if name is not None and name != key.default_name:
                diff[key.value] = name
        return diff

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
    EXPIRED = "Истекло"

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
    EVENT = "event"

    @property
    def display_name(self) -> str:
        return {
            "regular": "Обычная",
            "deadline": "Дедлайн",
            "recurring": "Регулярная",
            "instance": "Экземпляр",
            "event": "Событие",
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
    EVENT = 6

    @property
    def display_name(self) -> str:
        return {
            1: "Низкий",
            2: "Средний",
            3: "Высокий",
            4: "Дедлайн",
            5: "Регулярная",
            6: "Событие",
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
                 next_generation_date: Optional[str] = None,
                 event_date: Optional[str] = None,
                 checklist_required: bool = False,
                 checklist: Optional[list] = None,
                 theme: str = "black"):
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
            theme: str — ключ темы задачи (по умолчанию "black").

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
        self.event_date = event_date
        self.checklist_required = checklist_required
        self.checklist = checklist if checklist is not None else []
        self.theme = theme

    @staticmethod
    def _default_priority_for(task_type: TaskType) -> TaskPriority:
        """Единственный источник инварианта "дефолтный priority для типа".

        При добавлении члена TaskType — обновляется этот метод; иначе ValueError.
        """
        match task_type:
            case TaskType.REGULAR:
                return TaskPriority.MEDIUM
            case TaskType.DEADLINE:
                return TaskPriority.DEADLINE
            case TaskType.RECURRING | TaskType.INSTANCE:
                return TaskPriority.RECURRING
            case TaskType.EVENT:
                return TaskPriority.EVENT
            case _:
                raise ValueError(
                    f"_default_priority_for: неизвестный TaskType: {task_type!r}. "
                    f"Добавь его в метод."
                )

    @staticmethod
    def _put(out: dict, key: str, value, skip) -> None:
        """Единый паттерн ленивой сериализации: пишет out[key] = value,
        если value != skip. skip — значение, при котором поле не пишется
        (fallback, который from_dict вернёт при отсутствии ключа).
        """
        if value != skip:
            out[key] = value

    def to_dict(self) -> dict:
        """Сериализация в примитивы для JSON.

        Ленивая: поля с дефолтными значениями не пишутся (см. _put,
        _default_priority_for). Обязательные — task_id, title, created_date.
        Порядок ключей — фиксированный (обязательные → тип/тема → optional).
        """
        out = {}

        # Обязательные (пишутся напрямую)
        out["task_id"] = self.task_id
        out["title"] = self.title
        out["created_date"] = self.created_date

        # Скипаемые (через _put)
        self._put(out, "description", self.description, "")
        self._put(out, "priority", self.priority.value, self._default_priority_for(self.task_type).value)
        self._put(out, "status", self.status.value, TaskStatus.ACTIVE.value)
        self._put(out, "task_type", self.task_type.value, TaskType.REGULAR.value)
        self._put(out, "theme", self.theme, "black")
        self._put(out, "completed_date", self.completed_date, None)
        self._put(out, "spawner_task", self.spawner_task, None)
        self._put(out, "deadline_datetime", self.deadline_datetime, None)
        self._put(out, "created_datetime", self.created_datetime, None)
        self._put(out, "recurrence_type", self.recurrence_type, None)
        self._put(out, "recurrence_value", self.recurrence_value, None)
        self._put(out, "recurrence_weekdays", self.recurrence_weekdays, None)
        self._put(out, "recurrence_monthdays", self.recurrence_monthdays, None)
        self._put(out, "recurrence_use_last_day", self.recurrence_use_last_day, False)
        self._put(out, "next_generation_date", self.next_generation_date, None)
        self._put(out, "event_date", self.event_date, None)
        self._put(out, "checklist_required", self.checklist_required, False)
        self._put(out, "checklist", [item.to_dict() for item in self.checklist], [])

        return out

    @classmethod
    def from_dict(cls, data: dict) -> "PlannerTask":
        """Восстановление из dict.

        "Ключ отсутствует" → дефолт по смыслу (_default_priority_for для priority,
        ACTIVE для status, "black" для theme, REGULAR для task_type).
        "Значение битое" → мягкий fallback (LOW, CANCELLED, REGULAR, "black").
        List-поля recurrence_weekdays / recurrence_monthdays защищены
        isinstance(list); bool-поля — bool(...).
        """
        # Обязательные (KeyError уходит наверх)
        task_id = data["task_id"]
        title = data["title"]

        # task_type (строго перед priority)
        if "task_type" not in data:
            task_type = TaskType.REGULAR
        else:
            try:
                task_type = TaskType(data["task_type"])
            except (ValueError, TypeError):
                task_type = TaskType.REGULAR

        # priority
        if "priority" not in data:
            priority = cls._default_priority_for(task_type)
        else:
            try:
                priority = TaskPriority(data["priority"])
            except (ValueError, TypeError):
                priority = TaskPriority.LOW

        # status
        if "status" not in data:
            status = TaskStatus.ACTIVE
        else:
            try:
                status = TaskStatus(data["status"])
            except (ValueError, TypeError):
                status = TaskStatus.CANCELLED

        # theme
        if "theme" not in data:
            theme_value = "black"
        else:
            try:
                theme_value = ThemeKey(data["theme"]).value
            except (ValueError, TypeError):
                theme_value = "black"

        # Строки
        description = data.get("description", "")
        created_date = data.get("created_date", "")

        # None-поля
        completed_date = data.get("completed_date")
        spawner_task = data.get("spawner_task")
        deadline_datetime = data.get("deadline_datetime")
        created_datetime = data.get("created_datetime")
        next_generation_date = data.get("next_generation_date")
        event_date = data.get("event_date")
        recurrence_type = data.get("recurrence_type")
        recurrence_value = data.get("recurrence_value")

        # Списки
        rw = data.get("recurrence_weekdays")
        if not isinstance(rw, list):
            rw = None

        rm = data.get("recurrence_monthdays")
        if not isinstance(rm, list):
            rm = None

        # Байты (bool)
        ruld = bool(data.get("recurrence_use_last_day", False))
        ch_req = bool(data.get("checklist_required", False))

        # Чек-лист (walrus + фильтр None)
        checklist_data = data.get("checklist") or []
        checklist = [
            item for raw in checklist_data
            if (item := ChecklistItem.from_dict(raw)) is not None
        ]

        return cls(
            task_id=task_id,
            title=title,
            description=description,
            priority=priority,
            status=status,
            created_date=created_date,
            completed_date=completed_date,
            spawner_task=spawner_task,
            deadline_datetime=deadline_datetime,
            created_datetime=created_datetime,
            task_type=task_type,
            recurrence_type=recurrence_type,
            recurrence_value=recurrence_value,
            recurrence_weekdays=rw,
            recurrence_monthdays=rm,
            recurrence_use_last_day=ruld,
            next_generation_date=next_generation_date,
            event_date=event_date,
            checklist_required=ch_req,
            checklist=checklist,
            theme=theme_value,
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

    def is_event(self) -> bool:
        """True, если задача — событие.

        Выход: bool.
        Роль: быстрая проверка типа для UI и сервисов. События
              отличаются от обычных задач поведением: создаются
              в WAITING, активируются в день события, архивируются
              на следующий день.
        """
        return self.task_type == TaskType.EVENT

# Плоский пункт чек-листа.
@dataclass
class ChecklistItem:
    """Плоский пункт чек-листа, без иерархии.

    Поля:
        checked — выполнен ли пункт.
        short — краткое название (в списке).
        detail — подробное описание (в диалоге).
        order — позиция для сортировки внутри группы
                (checked совпадает).
    """
    checked: bool = False
    short: str = ""
    detail: str = ""
    order: int = 0

    def to_dict(self) -> dict:
        """Сериализация в примитивы для JSON."""
        return {
            "checked": self.checked,
            "short": self.short,
            "detail": self.detail,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data) -> "ChecklistItem | None":
        """Восстановление из dict. None — если data не dict.

        Мягкая деградация: отсутствующие поля — дефолты.
        """
        if not isinstance(data, dict):
            return None
        return cls(
            checked=bool(data.get("checked", False)),
            short=str(data.get("short", "")),
            detail=str(data.get("detail", "")),
            order=int(data.get("order", 0)),
        )