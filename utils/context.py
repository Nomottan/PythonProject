import sys
from pathlib import Path
from datetime import date
from typing import Optional
from utils.path_manager import PathManager
from utils.log_system.manager import LogManager
from utils.log_system.logger import Logger


class TaskContext:
    """Контекст выполнения задачи: рабочая папка, дата, логирование.

    Подпапки создаются ЛЕНИВО — при первом обращении к свойству.
    Набор разрешённых подпапок задаётся параметром subfolders при создании.
    Подпапка «Логи» создаётся всегда: она нужна LogManager для task-лога.

    Пример:
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_подготовка.txt",
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.reports_dir   # создаст work_folder/Отчёты при первом обращении
        ctx.processing_dir  # создаст work_folder/Обработка
    """

    # Допустимые имена подпапок.
    ALL_SUBFOLDERS = {"Логи", "Отчёты", "Продажи", "Обработка"}

    def __init__(self, target_dir: str, subfolder_template: str,
                 log_filename: str, log_callback=None,
                 log_manager: Optional[LogManager] = None,
                 source: str = "",
                 subfolders=None):
        """Контекст выполнения задачи.

        Вход:
            target_dir — корневая папка, куда складываются задачи.
            subfolder_template — шаблон имени подпапки, например "ЧЗ_МП_{date}".
            log_filename — имя task-лога, например "log_подготовка.txt".
            log_callback — старый UI-колбэк (msg) -> None. Сохранён для совместимости.
            log_manager — LogManager из пакета log_system.
            source — «класс и модуль» для префикса [source].
            subfolders — список разрешённых подпапок. None или [] — только «Логи».
                         Значения вне ALL_SUBFOLDERS игнорируются.

        Роль: единая точка доступа к рабочей папке и логированию.
              Подпапки создаются лениво, чтобы не плодить пустые папки
              в сервисах, которые их не используют.
        """
        self.today = date.today()
        self.date_str = f"{self.today.day}_{self.today.month}_{self.today.year}"
        subfolder_name = subfolder_template.format(date=self.date_str)
        self.work_folder = PathManager.ensure_dir(Path(target_dir) / self.date_str / subfolder_name)

        # NEW: разрешённые подпапки и кэш уже созданных.
        # «Логи» добавляется всегда — нужна LogManager.
        requested = set(subfolders or [])
        # Отсекаем неизвестные имена — защита от опечаток.
        self._enabled = (requested & self.ALL_SUBFOLDERS) | {"Логи"}
        self._subfolder_cache = {}

        # Логи создаются сразу — LogManager должен иметь путь.
        logs_path = self._get_subfolder("Логи")
        self.log_path = logs_path / log_filename

        self.callback = log_callback or print
        self.log_manager = log_manager
        if log_manager is not None:
            self.logger: Optional[Logger] = log_manager.create_logger(
                source=source,
                work_folder=logs_path,
                log_filename=log_filename,
            )
        else:
            self.logger = None

    # ---------- Ленивое создание подпапок ----------

    def _get_subfolder(self, name: str) -> Optional[Path]:
        """Лениво создаёт подпапку при первом обращении.

        Вход: name — имя подпапки (Логи, Отчёты, Продажи, Обработка).
        Выход: Path к папке или None, если папка не разрешена.

        Роль: единая точка создания подпапок. Кэширует результат,
              чтобы не вызывать mkdir повторно.
        """
        if name not in self._enabled:
            return None
        if name not in self._subfolder_cache:
            self._subfolder_cache[name] = PathManager.ensure_dir(self.work_folder / name)
        return self._subfolder_cache[name]

    @property
    def logs_dir(self) -> Optional[Path]:
        """Папка Логи/ — task-логи и kiz_validation.log."""
        return self._get_subfolder("Логи")

    @property
    def reports_dir(self) -> Optional[Path]:
        """Папка Отчёты/ — скопированные отчёты МП и ЧЗ_МП."""
        return self._get_subfolder("Отчёты")

    @property
    def sales_dir(self) -> Optional[Path]:
        """Папка Продажи/ — файлы продаж между продавцами."""
        return self._get_subfolder("Продажи")

    @property
    def processing_dir(self) -> Optional[Path]:
        """Папка Обработка/ — txt, предитоговые xlsx, prices_from_mp.json."""
        return self._get_subfolder("Обработка")

    # ---------- Логирование (без изменений) ----------

    def log(self, msg: str) -> None:
        """Информационное сообщение (синоним info)."""
        self.info(msg)

    def info(self, msg: str) -> None:
        """Информационное сообщение."""
        if self.logger is not None:
            self.logger.info(msg)
            self._safe_callback(msg)
        else:
            self._old_log(msg)

    def debug(self, msg: str) -> None:
        """Отладочное сообщение. Идёт только в debug.txt при debug."""
        if self.logger is not None:
            self.logger.debug(msg)

    def warning(self, msg: str) -> None:
        """Предупреждение. Идёт в task-лог и errors.txt."""
        if self.logger is not None:
            self.logger.warning(msg)
            self._safe_callback(f"[WARNING] {msg}")
        else:
            self._old_log(f"[WARNING] {msg}")

    def error(self, msg: str) -> None:
        """Ошибка. Идёт в task-лог и errors.txt."""
        if self.logger is not None:
            self.logger.error(msg)
            self._safe_callback(f"[ERROR] {msg}")
        else:
            self._old_log(f"[ERROR] {msg}")

    def log_separator(self, char="=", length=60):
        """Разделитель из символов — идёт через info()."""
        self.log(char * length)

    def log_statistics(self, title, data_dict, sorted_keys=True):
        """Блок статистики — идёт через info()."""
        self.log(title)
        self.log_separator()
        if data_dict:
            keys = sorted(data_dict.keys(), key=lambda x: str(x).lower()) if sorted_keys else data_dict.keys()
            for key in keys:
                self.log(f"   {key}: {data_dict[key]}")
        else:
            self.log("   Нет данных")

    # ---------- Приватные помощники ----------

    def _old_log(self, msg: str) -> None:
        """Старое поведение: запись в файл + callback (fallback)."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception as e:
            sys.stderr.write(
                f"[TaskContext] Не удалось записать в {self.log_path}: {e}\n"
            )
        self._safe_callback(msg)

    def _safe_callback(self, msg: str) -> None:
        """Вызывает self.callback, не роняя основную логику."""
        if not self.callback:
            return
        try:
            self.callback(msg)
        except Exception as e:
            sys.stderr.write(f"[TaskContext] Ошибка callback: {e}\n")

    # ---------- Файлы ----------

    def format_filename(self, template: str, extension: str = ".xlsx") -> str:
        """Формирует имя файла с подстановкой даты."""
        return template.format(date=self.date_str) + extension