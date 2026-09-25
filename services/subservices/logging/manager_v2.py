"""
LogManagerV2 — фабрика логгеров V2.

Создаёт LoggerV2 с набором handlers для каждого источника.
"""

from .logger_v2 import LoggerV2
from .handlers_v2 import (
    InfoFileHandler, InfoUIHandler, ReportHandler,
    WarningFileHandler, DebugFileHandler,
    NotificationHandler, StatusHandler, CriticalHandler,
)


class LogManagerV2:
    """Менеджер логгеров V2.

    Поля:
        _debug_enabled — включён ли debug.
        _paths — PathManager.
        _active_child_getter — callable для получения active_child.
                               Пока None — UI-каналы не работают.

    Роль: единая точка создания LoggerV2. Каждый логгер получает
          одинаковый набор handlers, настроенных на source и
          work_folder конкретного сервиса.
    """

    def __init__(self, debug_enabled: bool, paths,
                 active_child_getter=None):
        """Конструктор.

        Вход:
            debug_enabled — если True, debug.txt очищается при старте,
                            и debug() начинает писать.
            paths — PathManager.
            active_child_getter — опциональный callable, возвращающий
                                  active_child. Пока не используется.
        """
        self._debug_enabled = debug_enabled
        self._paths = paths
        self._active_child_getter = active_child_getter

        # Чистим debug.txt при включённом debug.
        if debug_enabled and paths is not None:
            debug_path = paths.app_root / "debug.txt"
            if debug_path.exists():
                try:
                    debug_path.unlink()
                except OSError:
                    pass

    def create_logger_v2(self, source: str, domain: str,
                         work_folder=None,
                         log_filename: str | None = None) -> LoggerV2:
        """Создаёт LoggerV2 для источника.

        Вход:
            source — идентификатор источника ("Class.module").
            domain — домен (пока не используется, зарезервирован
                     под реестр типов).
            work_folder — рабочая папка задачи (может быть None).
            log_filename — опциональное имя файла журнала сервиса
                           (Channel.REPORT). Если None — используется
                           fallback log_{source}.txt в папке «Логи».
                           Пример: "log_подготовка.txt".

        Выход: LoggerV2.

        Роль: создаёт полный набор handlers и собирает LoggerV2.
              UI-каналы (Notification, Status, Critical) работают
              через _active_child_getter: если active_child есть —
              показывают UI, иначе уходят в fallback (Info-файл +
              errors.txt).
        """
        handlers = [
            # Файловые каналы.
            InfoFileHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            # REPLACE: в ReportHandler пробрасывается log_filename.
            ReportHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
                log_filename,
            ),
            WarningFileHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            DebugFileHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            # UI-каналы.
            InfoUIHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            NotificationHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            StatusHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
            CriticalHandler(
                source, work_folder, self._paths,
                self._active_child_getter,
            ),
        ]
        return LoggerV2(source, handlers, self._debug_enabled)