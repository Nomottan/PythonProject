"""
Handler'ы подсистемы логирования V2.

HandlerV2 — абстрактный базовый класс: получает LogRecordV2 и решает,
доставлять его или нет. Наследники реализуют конкретные каналы:
UI-уведомления, статус, файлы (Info, Report, Warning, Error, Debug).

Роль в программе:
    Каждый handler отвечает ровно за один канал. LoggerV2 не знает,
    куда идут сообщения — он просто рассылает запись во все handlers,
    а они фильтруют по _should_handle.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, QThread
from PySide6.QtWidgets import QApplication

from .enums import Severity, Channel
from .record_v2 import LogRecordV2
from utils.log_tools.formatters import (
    format_timestamp, format_source, format_severity,
)


class HandlerV2(ABC):
    """Абстрактный handler.

    Поля:
        _source — идентификатор источника (для форматирования).
        _work_folder — рабочая папка задачи (если есть).
        _paths — PathManager (для app_root и т.п.).
        _active_child_getter — callable, возвращающий active_child
                               (окно, которому можно отправить UI-сообщение).
                               Может быть None — тогда UI-каналы
                               уходят в fallback.

    Публичный API:
        emit(record) — обработать запись.
        _should_handle(record) — фильтр (по умолчанию True).
    """

    def __init__(self, source: str, work_folder=None, paths=None,
                 active_child_getter=None):
        """Конструктор.

        Вход:
            source — идентификатор источника ("Class.module").
            work_folder — рабочая папка задачи (может быть None).
            paths — PathManager (для app_root/errors.txt, debug.txt).
            active_child_getter — callable, возвращающий active_child
                                  или None. Нужен для NotificationHandler
                                  и StatusHandler.
        """
        self._source = source
        self._work_folder = Path(work_folder) if work_folder else None
        self._paths = paths
        self._active_child_getter = active_child_getter

    # ---------- Публичный API ----------

    @abstractmethod
    def emit(self, record: LogRecordV2) -> None:
        """Доставляет запись по каналу handler'а.

        Вход: record — LogRecordV2.
        Роль: абстрактный. Наследник решает, что делать с записью:
              писать в файл, вызывать UI, комбинировать.
        """
        raise NotImplementedError

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Фильтр по каналу/важности.

        Вход: record — запись.
        Выход: True — обрабатывать; False — пропустить.
        Роль: по умолчанию True. Наследники переопределяют,
              чтобы слушать только свой канал или severity.
        """
        return True

    # ---------- Вспомогательные ----------

    def _get_active_child(self):
        """Возвращает active_child через getter или None.

        Выход: активное дочернее окно или None.
        Роль: единая точка получения active_child. Если getter
              не задан — считаем, что окна нет.
        """
        if self._active_child_getter is None:
            return None
        try:
            return self._active_child_getter()
        except Exception:
            return None

    def _run_in_ui_thread(self, callback) -> None:
        """Вызывает callback в главном потоке Qt.

        Вход: callback — callable без аргументов.
        Роль: если мы уже в главном потоке — вызываем сразу.
              Иначе — через QTimer.singleShot(0, ...): он выполнится
              в том потоке, где есть event loop (обычно — главный).
        """
        app = QApplication.instance()
        if app is None:
            # Qt ещё не запущен — вызываем как есть.
            callback()
            return
        if QThread.currentThread() == app.thread():
            callback()
        else:
            QTimer.singleShot(0, callback)

    def _format_line(self, record: LogRecordV2) -> str:
        """Форматирует запись в строку для файла.

        Вход: record — запись.
        Выход: строка "[ts] [SEVERITY] [source] message".
        Роль: единая точка форматирования строк — все файловые
              handler'ы используют её.
        """
        return (
            f"[{format_timestamp(record.timestamp)}] "
            f"[{format_severity(record.severity)}] "
            f"{format_source(record.source)} "
            f"{record.message}"
        )

    def _append_to_file(self, path: Path, line: str) -> None:
        """Добавляет строку в файл, создавая папки.

        Вход: path — путь к файлу; line — строка.
        Роль: общая утилита для всех файловых handler'ов.
              Ошибки записи не поднимаются — логирование не должно
              ронять приложение.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except (IOError, OSError):
            # Молча — логирование не должно ронять основную логику.
            pass

    def _info_file_path(self) -> Path:
        """Путь к Info-файлу домена.

        Выход: work_folder / "Логи" / f"Отчёт от {date}.txt".
        Роль: используется InfoFileHandler и как fallback
              для UI-каналов, когда active_child недоступен.
        """
        date_str = datetime.now().strftime("%d_%m_%Y")
        return self._work_folder / "Логи" / f"Отчёт от {date_str}.txt"

    def _errors_file_path(self) -> Path:
        """Путь к errors.txt в корне приложения.

        Выход: paths.app_root / "errors.txt".
        Роль: используется CriticalHandler и как fallback
              для UI-каналов.
        """
        if self._paths is None:
            return Path("errors.txt")
        return Path(self._paths.app_root) / "errors.txt"

    def _write_fallback(self, record: LogRecordV2) -> None:
        """Fallback для UI-каналов, когда active_child недоступен.

        Вход: record — запись.
        Роль: пишет запись в Info-файл (если есть work_folder)
              и в errors.txt с уровнем WARNING. Так пользователь
              не теряет сообщение, даже если окна нет.
        """
        line = self._format_line(record)

        # Info-файл — только если есть рабочая папка.
        if self._work_folder is not None:
            self._append_to_file(self._info_file_path(), line)

        # errors.txt — всегда, с пометкой WARNING.
        warning_record_line = (
            f"[{format_timestamp(record.timestamp)}] "
            f"[WARNING] "
            f"{format_source(record.source)} "
            f"{record.message}"
        )
        self._append_to_file(self._errors_file_path(), warning_record_line)


class NotificationHandler(HandlerV2):
    """Handler уведомлений (Channel.NOTIFICATION).

    Роль: показывает всплывающее уведомление через active_child.
          Если active_child недоступен — пишет в Info-файл и
          errors.txt (WARNING).
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал NOTIFICATION."""
        return record.channel == Channel.NOTIFICATION

    def emit(self, record: LogRecordV2) -> None:
        """Показывает уведомление.

        Вход: record — запись.
        Роль: если active_child есть — вызывает notify(msg) в UI-потоке.
              Иначе — fallback.
        """
        active_child = self._get_active_child()
        if active_child is not None:
            msg = record.message
            self._run_in_ui_thread(
                lambda: active_child.notify(msg)
            )
        else:
            self._write_fallback(record)


class StatusHandler(HandlerV2):
    """Handler статуса (Channel.STATUS).

    Роль: обновляет статусную строку в active_child. Если окна
          нет — пишет в Info-файл и errors.txt (WARNING).
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал STATUS."""
        return record.channel == Channel.STATUS

    def emit(self, record: LogRecordV2) -> None:
        """Обновляет статус.

        Вход: record — запись.
        Роль: если у active_child есть метод set_status — вызывает его
              в UI-потоке. Иначе — fallback.
        """
        active_child = self._get_active_child()
        if active_child is not None and hasattr(active_child, "set_status"):
            msg = record.message
            self._run_in_ui_thread(
                lambda: active_child.set_status(msg)
            )
        else:
            self._write_fallback(record)


class InfoFileHandler(HandlerV2):
    """Handler Info-файла (Channel.INFO_LOG).

    Роль: пишет сводные сообщения домена в
          work_folder / "Логи" / f"Отчёт от {date}.txt".
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал INFO_LOG."""
        return record.channel == Channel.INFO_LOG

    def emit(self, record: LogRecordV2) -> None:
        """Пишет строку в Info-файл."""
        if self._work_folder is None:
            return
        self._append_to_file(
            self._info_file_path(), self._format_line(record)
        )


class ReportHandler(HandlerV2):
    """Handler журнала сервиса (Channel.REPORT).

    Роль: пишет пошаговый журнал сервиса в
          work_folder / "Логи" / f"log_{source}.txt".
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал REPORT."""
        return record.channel == Channel.REPORT

    def emit(self, record: LogRecordV2) -> None:
        """Пишет строку в файл журнала сервиса."""
        if self._work_folder is None:
            return
        path = self._work_folder / "Логи" / f"log_{self._source}.txt"
        self._append_to_file(path, self._format_line(record))


class WarningFileHandler(HandlerV2):
    """Handler файла предупреждений (Channel.WARNING_FILE).

    Роль: пишет предупреждения в work_folder / "Логи" / "warnings.txt".
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал WARNING_FILE."""
        return record.channel == Channel.WARNING_FILE

    def emit(self, record: LogRecordV2) -> None:
        """Пишет строку в warnings.txt."""
        if self._work_folder is None:
            return
        path = self._work_folder / "Логи" / "warnings.txt"
        self._append_to_file(path, self._format_line(record))


class CriticalHandler(HandlerV2):
    """Handler критических событий (Severity.CRITICAL).

    Роль: пишет в errors.txt в корне приложения и показывает диалог.
          Если record.can_influence — MessageDialog (пользователь
          может повлиять), иначе — NotificationDialog.
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только записи с severity CRITICAL."""
        return record.severity == Severity.CRITICAL

    def emit(self, record: LogRecordV2) -> None:
        """Пишет в errors.txt и показывает диалог.

        Вход: record — запись.
        Роль: файл пишем сразу, диалог — в UI-потоке.
        """
        # 1. Запись в errors.txt.
        self._append_to_file(
            self._errors_file_path(), self._format_line(record)
        )

        # 2. Диалог в UI-потоке.
        msg = record.message
        can_influence = record.can_influence

        def show_dialog():
            from ui.windows.message_dialog import (
                MessageDialog, NotificationDialog,
            )
            if can_influence:
                MessageDialog.question(
                    None, msg, title_text="Критическая ошибка"
                )
            else:
                NotificationDialog.notify(
                    None, msg, title_text="Критическая ошибка"
                )

        self._run_in_ui_thread(show_dialog)


class DebugFileHandler(HandlerV2):
    """Handler отладочного файла (Channel.DEBUG_FILE).

    Роль: пишет отладочные сообщения в paths.app_root / "debug.txt".
    """

    def _should_handle(self, record: LogRecordV2) -> bool:
        """Обрабатывает только канал DEBUG_FILE."""
        return record.channel == Channel.DEBUG_FILE

    def emit(self, record: LogRecordV2) -> None:
        """Пишет строку в debug.txt."""
        if self._paths is None:
            return
        path = Path(self._paths.app_root) / "debug.txt"
        self._append_to_file(path, self._format_line(record))