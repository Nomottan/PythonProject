"""
Сервис-контроллер мини-планировщика для MainWindow.

Содержит:
    PrioritySlotFiller — управляет слотами одного приоритета.
    PlannerQuickViewController — распределяет 6 слотов между тремя
    приоритетами, крутит карусели, открывает диалог задачи.
"""

import random
from typing import Optional

from PySide6.QtCore import QObject, QTimer

from models.planner_task import PlannerTask, TaskPriority
from services.planner_service import PlannerService


class PrioritySlotFiller:
    """Управляет слотами одного приоритета.

    Один экземпляр на приоритет. Контроллер создаёт три штуки и
    распределяет между ними 6 слотов.
    """

    def __init__(self, priority: TaskPriority, default_slots: int):
        """Конструктор.

        Вход: priority — приоритет; default_slots — базовое число слотов
              (3 для HIGH, 2 для MEDIUM, 1 для LOW).
        """
        self.priority = priority
        self.default_slots = default_slots
        self.assigned_slots = default_slots
        self._tasks: list[PlannerTask] = []
        self._filled: list[PlannerTask] = []

    def reset(self, all_tasks: list[PlannerTask]) -> None:
        """Пересобирает список своих задач и сбрасывает состояние.

        Вход: all_tasks — все активные задачи.
        Роль: фильтр по приоритету, сортировка по task_id возрастанию.
              Сбрасывает assigned_slots к default и очищает _filled.
        """
        self._tasks = sorted(
            [t for t in all_tasks if t.priority == self.priority],
            key=lambda t: t.task_id,
        )
        self.assigned_slots = self.default_slots
        self._filled = []

    def fill(self) -> int:
        """Заполняет доступные слоты из _tasks.

        Выход: количество заполненных слотов после операции.
        """
        self._filled = self._tasks[:self.assigned_slots]
        return len(self._filled)

    def add_slots(self, count: int) -> None:
        """Увеличивает assigned_slots на count."""
        self.assigned_slots += count

    def report(self) -> dict:
        """Возвращает {'filled': int, 'free': int, 'unshown': int}.

        unshown — задачи, которым не хватило слотов (уйдут в карусель).
        """
        return {
            "filled": len(self._filled),
            "free": self.assigned_slots - len(self._filled),
            "unshown": len(self._tasks) - len(self._filled),
        }

    def get_shown(self) -> list[PlannerTask]:
        """Задачи в фиксированных слотах (копия)."""
        return list(self._filled)

    def get_unshown(self) -> list[PlannerTask]:
        """Задачи, которым не хватило слотов."""
        return self._tasks[len(self._filled):]

    def get_carousel_tasks(self) -> list[PlannerTask]:
        """Список задач для карусели.

        Вход: нет.
        Выход: [последняя показанная, ...все неотображённые]. Пусто,
               если неотображённых нет.
        Роль: карусель занимает последний слот приоритета и меняет
              задачу в нём по кругу, начиная с последней фиксированной,
              чтобы переход был плавным.
        """
        if len(self._tasks) <= len(self._filled):
            return []
        start = max(0, len(self._filled) - 1)
        return self._tasks[start:]


class PlannerQuickViewController(QObject):
    """Контроллер мини-планировщика.

    Распределяет 6 слотов между приоритетами HIGH/MEDIUM/LOW, реагирует
    на tasks_changed, крутит карусели, открывает диалог задачи.
    """

    TOTAL_SLOTS = 6
    # Диапазон случайного интервала карусели, мс.
    CAROUSEL_MIN_MS = 15_000
    CAROUSEL_MAX_MS = 45_000

    def __init__(self, service: PlannerService, view):
        """Конструктор.

        Вход:
            service — PlannerService с сигналом tasks_changed.
            view — PlannerQuickView с сигналом task_clicked.
        """
        super().__init__()
        self._service = service
        self._view = view

        # Три филлера — по одному на приоритет.
        self._fillers = {
            TaskPriority.HIGH:   PrioritySlotFiller(TaskPriority.HIGH, 3),
            TaskPriority.MEDIUM: PrioritySlotFiller(TaskPriority.MEDIUM, 2),
            TaskPriority.LOW:    PrioritySlotFiller(TaskPriority.LOW, 1),
        }

        # Таймеры каруселей: по одному на приоритет.
        self._timers: dict[TaskPriority, QTimer] = {}
        # Текущий индекс в карусели каждого приоритета.
        self._carousel_state: dict[TaskPriority, int] = {}
        # Список задач карусели каждого приоритета.
        self._carousel_tasks: dict[TaskPriority, list] = {}
        # Индекс слота в виджете, который занят каруселью приоритета.
        self._carousel_slot_index: dict[TaskPriority, int] = {}

        # Защита от повторного открытия диалога (двойной клик).
        self._dialog_open = False

        # Подписки.
        self._service.tasks_changed.connect(self.refresh)
        self._view.task_clicked.connect(self._on_task_clicked)

        # Первая отрисовка.
        self.refresh()

    # ---------- Публичный API ----------

    def refresh(self) -> None:
        """Пересобирает раскладку слотов.

        Роль: единая точка перерисовки. Вызывается при старте
              и при каждом tasks_changed.
        """
        # 1. Останавливаем и сбрасываем всё, что связано с каруселями.
        for timer in self._timers.values():
            timer.stop()
        self._timers.clear()
        self._carousel_state.clear()
        self._carousel_tasks.clear()
        self._carousel_slot_index.clear()

        # 2. Берём активные задачи.
        tasks = self._service.get_tasks()

        # 3. Пустой список — специальный режим.
        if not tasks:
            self._view.show_empty()
            return

        # 4. Сбрасываем филлеры.
        for filler in self._fillers.values():
            filler.reset(tasks)

        # 5. Фаза 1: базовое заполнение.
        for p in (TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW):
            self._fillers[p].fill()

        # 6. Фаза 2: редистрибуция свободных слотов.
        self._redistribute()

        # 7. Фазы 3–5: строим slots, попутно инициализируем карусели.
        slots = self._build_slots()

        # 8. Отдаём в виджет.
        self._view.set_slots(slots)

    # ---------- Внутренние ----------

    def _redistribute(self) -> None:
        """Отдаёт свободные слоты приоритетам с неотображёнными задачами.

        Идёт по приоритетам сверху вниз и отдаёт все свободные слоты
        первому, у кого есть unshown. Если он их не заполнил — переходим
        к следующему. Цикл прерывается, когда свободных слотов нет
        или никто не смог их занять.
        """
        while True:
            total_filled = sum(
                len(f.get_shown()) for f in self._fillers.values()
            )
            free = self.TOTAL_SLOTS - total_filled
            if free <= 0:
                break

            # Ищем высший приоритет с неотображёнными задачами.
            candidate = None
            for p in (TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW):
                if self._fillers[p].report()["unshown"] > 0:
                    candidate = self._fillers[p]
                    break
            if candidate is None:
                break

            before = len(candidate.get_shown())
            candidate.add_slots(free)
            candidate.fill()
            after = len(candidate.get_shown())
            if after == before:
                # Не смог занять ни одного слота — защита от зацикливания.
                break

    def _build_slots(self) -> list:
        """Собирает список слотов для view и инициализирует карусели.

        Выход: list длиной TOTAL_SLOTS. Элемент:
            None — пусто;
            (task, color) — заполненный слот.

        Роль: единая точка сборки. Попутно вычисляет _carousel_slot_index
              и запускает таймеры для приоритетов с overflow.
        """
        slots: list = []
        # Цвета по приоритету — контроллер передаёт их во view.
        colors = {
            TaskPriority.HIGH:   (150, 100, 90, 0.85),
            TaskPriority.MEDIUM: (70, 90, 150, 0.85),
            TaskPriority.LOW:    (100, 100, 100, 0.85),
        }
        priorities = (TaskPriority.HIGH, TaskPriority.MEDIUM, TaskPriority.LOW)

        for p in priorities:
            filler = self._fillers[p]
            shown = filler.get_shown()
            report = filler.report()

            if not shown:
                continue  # у этого приоритета нет задач — пропускаем блок

            # Есть ли карусель у этого приоритета?
            carousel_tasks = filler.get_carousel_tasks() if report["unshown"] > 0 else []
            has_carousel = len(carousel_tasks) > 0

            for i, task in enumerate(shown):
                is_last = (i == len(shown) - 1)
                if is_last and has_carousel:
                    # Последний слот приоритета становится каруселью.
                    self._carousel_slot_index[p] = len(slots)
                    self._carousel_tasks[p] = carousel_tasks
                    self._carousel_state[p] = 0
                    slots.append((carousel_tasks[0], colors[p]))
                else:
                    slots.append((task, colors[p]))

        # Добиваем None до TOTAL_SLOTS.
        while len(slots) < self.TOTAL_SLOTS:
            slots.append(None)

        # Запускаем таймеры для всех каруселей.
        for p in self._carousel_tasks:
            self._start_carousel_timer(p)

        return slots

    def _start_carousel_timer(self, priority: TaskPriority) -> None:
        """Создаёт и запускает таймер карусели для приоритета.

        Вход: priority — приоритет.
        Роль: случайный интервал 1–5 мин. При срабатывании — _advance_carousel.
        """
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(
            lambda p=priority: self._advance_carousel(p)
        )
        timer.start(random.randint(self.CAROUSEL_MIN_MS, self.CAROUSEL_MAX_MS))
        self._timers[priority] = timer

    def _advance_carousel(self, priority: TaskPriority) -> None:
        """Переключает задачу в слоте-карусели на следующую.

        Вход: priority — приоритет.
        Роль: циклический переход (index + 1) % len. Обновляет слот во view
              и перезапускает таймер со случайным интервалом.
        """
        tasks = self._carousel_tasks.get(priority)
        if not tasks:
            return
        index = (self._carousel_state[priority] + 1) % len(tasks)
        self._carousel_state[priority] = index

        slot_index = self._carousel_slot_index[priority]
        colors = {
            TaskPriority.HIGH:   (75, 50, 45, 0.85),
            TaskPriority.MEDIUM: (35, 45, 75, 0.85),
            TaskPriority.LOW:    (50, 50, 50, 0.85),
        }
        self._view.update_slot(slot_index, tasks[index], colors[priority])

        # Перезапуск таймера с новым случайным интервалом.
        timer = self._timers.get(priority)
        if timer is not None:
            timer.start(random.randint(self.CAROUSEL_MIN_MS, self.CAROUSEL_MAX_MS))

    # ---------- Обработчик клика ----------

    def _on_task_clicked(self, task_id: int) -> None:
        """Открывает диалог задачи по клику на слот.

        Вход: task_id — идентификатор задачи.
        Роль: защита от двойного открытия через _dialog_open.
        """
        if self._dialog_open:
            return

        # Находим задачу в текущем списке активных.
        task = next(
            (t for t in self._service.get_tasks() if t.task_id == task_id),
            None,
        )
        if task is None:
            return

        self._dialog_open = True
        try:
            from ui.windows.planner_task_main_commentary import PlannerTaskMainCommentary
            dialog = PlannerTaskMainCommentary(
                parent=self._view.window(),
                task=task,
                planner_service=self._service,
            )
            dialog.exec()
        finally:
            self._dialog_open = False