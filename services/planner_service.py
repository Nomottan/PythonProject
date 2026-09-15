from datetime import date

class PlannerService:
    """Сервис планировщика задач. Единый источник данных о задачах.

    Назначение:
        Хранит и отдаёт список задач. В будущем будет читать/писать
        JSON-файл, а сейчас возвращает демо-данные для визуальной
        оценки UI-каркаса.

    Роль в программе:
        Создаётся в main.py и передаётся в PlannerWindow. UI владеет
        отображением, сервис — данными и доменными списками.
    """

    def __init__(self, log_manager=None):
        """Конструктор.

        Вход:
            log_manager — зарезервирован для будущего логирования.
                          Сейчас не используется.

        Роль: сохраняет log_manager на будущее, не выполняет другой работы.
        """
        self._log_manager = log_manager

    def get_tasks(self) -> list:
        """Возвращает список задач. Пока — одна демо-задача."""
        return [self._get_demo_task()]

    def _get_demo_task(self) -> dict:
        """Возвращает демонстрационную задачу для визуальной оценки каркаса.

        Выход: dict с полями id, task_type, description, priority,
               status, created_date.
        """
        return {
            "id": 1,
            "task_type": "default",
            "description": "Пример задачи для оценки каркаса",
            "priority": "Средний",
            "status": "Активная",
            "created_date": "14.09.2026",
        }

    def get_priorities(self) -> list:
        """Возвращает список доступных приоритетов."""
        return ["Высокий", "Средний", "Низкий"]

    def get_statuses(self) -> list:
        """Возвращает список доступных статусов."""
        return ["Активная", "Выполнена", "Отменена"]

    def get_default_task_values(self) -> dict:
        """Возвращает дефолтные значения для новой задачи.

        Вход: нет.
        Выход: dict с task_type, status, priority, created_date (сегодня).

        Роль: используется только для тестирования. В UI не подключается —
              диалог NewTaskDialog сам берёт приоритеты и статусы через
              get_priorities() / get_statuses().
        """
        return {
            "task_type": "default",
            "status": "Активная",
            "priority": "Средний",
            "created_date": date.today().strftime("%d.%m.%Y"),
        }

    def add_task(self, task_data: dict) -> None:
        """Добавляет задачу. Заглушка — логика появится отдельной задачей."""
        pass

    def update_task(self, task_id: int, task_data: dict) -> None:
        """Обновляет задачу. Заглушка."""
        pass

    def delete_task(self, task_id: int) -> None:
        """Удаляет задачу. Заглушка."""
        pass
