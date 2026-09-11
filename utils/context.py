import sys
from pathlib import Path
from datetime import date
from typing import Optional
from utils.path_manager import PathManager
from utils.log_system.manager import LogManager
from utils.log_system.logger import Logger


class TaskContext:
    """
    Контекст выполнения задачи: рабочая папка, дата, логирование.
    """

    def __init__(self, target_dir: str, subfolder_template: str,
                 log_filename: str, log_callback=None,
                 log_manager: Optional[LogManager] = None,
                 source: str = ""):
        """Контекст выполнения задачи.

            Вход:
                target_dir — корневая папка, куда складываются задачи.
                subfolder_template — шаблон имени подпапки, например "Возвраты_{date}".
                log_filename — имя task-лога, например "log_возвраты.txt".
                log_callback — старый UI-колбэк с сигнатурой (msg) -> None.
                               Сохранён для обратной совместимости.
                log_manager — LogManager из пакета log_system. Если передан,
                              создаёт self.logger с source и work_folder.
                source — «класс и модуль» для префикса [source] в логах.

            Роль: единая точка доступа к рабочей папке и логированию для сервисов.
                  Если log_manager не передан — работает по-старому (пишет в файл
                  и в callback). Если передан — пишет через Logger (task-лог,
                  errors.txt) + дублирует в callback для UI.
            """
        self.today = date.today()
        self.date_str = f"{self.today.day}_{self.today.month}_{self.today.year}"
        subfolder_name = subfolder_template.format(date=self.date_str)
        from utils.path_manager import PathManager
        self.work_folder = PathManager.ensure_dir(Path(target_dir) / self.date_str / subfolder_name)
        self.log_path = self.work_folder / log_filename
        # Оставляем callback как есть — код вызывает его для обновления UI.
        self.callback = log_callback or print

        # NEW: если передан LogManager — создаём Logger с task-логом
        # в рабочей папке задачи. Источник — из аргумента source.
        self.log_manager = log_manager
        if log_manager is not None:
            self.logger: Optional[Logger] = log_manager.create_logger(
                source=source,
                work_folder=self.work_folder,
                log_filename=log_filename,
            )
        else:
            self.logger = None

    def log(self, msg: str) -> None:
        """Информационное сообщение (синоним info).

        Вход: msg — текст.
        Выход: нет.

        Роль: сохраняет совместимость со всем существующим кодом, который
              вызывает ctx.log(...). Внутри — делегирует в info(), где уже
              решается, идти через Logger или по-старому.
        """
        self.info(msg)

    def debug(self, msg: str) -> None:
        """Отладочное сообщение. Идёт только в debug.txt при включённом debug.

        При отсутствии logger — игнорируется (в старом _log уровня DEBUG нет).
        """
        if self.logger is not None:
            self.logger.debug(msg)

    def info(self, msg: str) -> None:
        """Информационное сообщение.

        Если есть logger — пишет через Logger (task-лог + UI-канал если
        настроен). Иначе — старый log(): файл + callback.
        """
        if self.logger is not None:
            self.logger.info(msg)
            # Дублируем в UI через старый callback — пока UICallbackHandler
            # в LogManager не настроен (это следующий этап).
            self._safe_callback(msg)
        else:
            self._old_log(msg)

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

    def _old_log(self, msg: str) -> None:
        """Старое поведение: запись в файл + callback.

        Используется только при отсутствии logger (fallback).
        Ошибки записи не глотаем молча — пишем в stderr.
        """
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception as e:
            sys.stderr.write(
                f"[TaskContext] Не удалось записать в {self.log_path}: {e}\n"
            )
        self._safe_callback(msg)

    def _safe_callback(self, msg: str) -> None:
        """Вызывает self.callback, не роняя основную логику.

        Обёрнут в try/except: падение UI не должно ломать сервис.
        """
        if not self.callback:
            return
        try:
            self.callback(msg)
        except Exception as e:
            sys.stderr.write(f"[TaskContext] Ошибка callback: {e}\n")

    def log_separator(self, char="=", length=60):
        self.log(char * length)

    def log_statistics(self, title, data_dict, sorted_keys=True):
        self.log(title)
        self.log_separator()
        if data_dict:
            keys = sorted(data_dict.keys(), key=lambda x: str(x).lower()) if sorted_keys else data_dict.keys()
            for key in keys:
                self.log(f"   {key}: {data_dict[key]}")
        else:
            self.log("   Нет данных")

    def format_filename(self, template: str, extension: str = ".xlsx") -> str:
        return template.format(date=self.date_str) + extension

    def get_work_file(self, template: str, extension: str = ".xlsx") -> Path:
        return self.work_folder / self.format_filename(template, extension)