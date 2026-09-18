"""
Генератор task_id для задач планировщика.

Утилита: единая точка генерации идентификаторов формата YYYYMMDDNNN.
Не имеет состояния, не зависит от сервисов — принимает любой storage
с методом get_all().
"""

from datetime import date


class TaskIdGenerator:
    """Генератор task_id формата YYYYMMDDNNN.

    Роль: единая точка генерации id. Логика: NNN — порядковый номер
          задачи за сегодня, начиная с 001. Дырки от удалённых задач
          не заполняются, id не переиспользуются.
    """

    @staticmethod
    def generate(storage) -> int:
        """Генерирует task_id: YYYYMMDDNNN.

        Вход: storage — объект с методом get_all(), возвращающим
              список задач с атрибутом task_id.
        Выход: int — новый идентификатор.
        """
        today_str = date.today().strftime("%Y%m%d")
        existing = storage.get_all()
        today_nnn = [
            t.task_id % 1000
            for t in existing
            if str(t.task_id).startswith(today_str)
        ]
        max_nnn = max(today_nnn, default=0)
        return int(today_str) * 1000 + max_nnn + 1
