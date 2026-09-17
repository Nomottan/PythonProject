import json
import os
import sys
import tempfile
from pathlib import Path

from models.planner_task import PlannerTask


class PlannerTaskStorage:
    """Хранилище задач планировщика в JSON-файле.

    Формат файла: список словарей (результат PlannerTask.to_dict()).
    Не потокобезопасен — вне текущего скоупа.

    Роль в программе:
        Инфраструктурный слой между PlannerService и файлом
        planner_tasks.json в Data/. Не содержит бизнес-логики.
    """

    def __init__(self, file_path: Path, log_manager=None):
        """Конструктор.

        Вход:
            file_path — путь к JSON-файлу.
            log_manager — LogManager для логирования. Если None — только stderr.

        Роль: сохраняет путь, создаёт logger, загружает существующие задачи.
        """
        self._file_path = Path(file_path)
        self._logger = None
        if log_manager is not None:
            # Логгер без work_folder: пишет только в errors.txt и UI.
            self._logger = log_manager.create_logger(
                source="PlannerTaskStorage.planner_task_storage",
                work_folder=None,
            )
        self._tasks: list[PlannerTask] = []
        self.load()

    def load(self) -> None:
        """Загружает задачи из файла.

        Если файла нет — self._tasks = [].
        Если файл битый — логирует warning, self._tasks = [].
        """
        if not self._file_path.exists():
            # Ленивое создание файла: при первом сохранении.
            self._tasks = []
            return
        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # from_dict может бросить KeyError, если нет task_id/title.
            self._tasks = [PlannerTask.from_dict(item) for item in data]
        except (json.JSONDecodeError, KeyError, IOError, OSError) as e:
            self._log_warning(f"Ошибка загрузки {self._file_path.name}: {e}")
            self._tasks = []

    def save(self) -> None:
        """Атомарно сохраняет список задач в JSON.

        Запись во временный файл + os.replace. Ошибки пробрасываются.
        """
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        data = [task.to_dict() for task in self._tasks]
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=self._file_path.parent, delete=False,
                suffix=".tmp", encoding="utf-8"
            ) as f:
                tmp_path = f.name
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._file_path)
        except Exception as e:
            self._log_error(f"Ошибка сохранения {self._file_path.name}: {e}")
            # Подчищаем tmp-файл, если os.replace не сработал.
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    def get_all(self) -> list[PlannerTask]:
        """Возвращает копию списка задач."""
        return list(self._tasks)

    def add(self, task: PlannerTask) -> None:
        """Добавляет задачу и сохраняет на диск.

        Вход: task — PlannerTask.
        Роль: append + save. Ошибка сохранения пробрасывается.
        """
        self._tasks.append(task)
        self.save()

    # ---------- Приватные методы ----------

    def _log_warning(self, message: str) -> None:
        """Пишет WARNING в logger или stderr."""
        if self._logger is not None:
            self._logger.warning(message)
        else:
            sys.stderr.write(f"[PlannerTaskStorage] WARNING: {message}\n")

    def _log_error(self, message: str) -> None:
        """Пишет ERROR в logger или stderr."""
        if self._logger is not None:
            self._logger.error(message)
        else:
            sys.stderr.write(f"[PlannerTaskStorage] ERROR: {message}\n")