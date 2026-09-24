"""
LoggerV2 — точка отправки сообщений.

Содержит методы для каждого канала: status, info, report, notify,
warning, critical, debug. Каждый метод формирует LogRecordV2
и рассылает его во все handlers; те сами решают, обрабатывать
или нет.
"""

from .enums import Severity, Channel
from .record_v2 import LogRecordV2


class LoggerV2:
    """Логгер V2.

    Поля:
        _source — идентификатор источника ("Class.module").
        _handlers — список HandlerV2.
        _debug_enabled — включён ли debug-канал.

    Роль: единая точка отправки сообщений. Сервис создаёт
          LoggerV2 через LogManagerV2 и вызывает методы по смыслу:
          status для UI-статуса, report для пошагового журнала и т.д.
    """

    def __init__(self, source: str, handlers: list,
                 debug_enabled: bool = False):
        """Конструктор.

        Вход:
            source — идентификатор источника.
            handlers — список HandlerV2.
            debug_enabled — если True, debug() реально отправляет
                            сообщение; иначе — игнорирует.
        """
        self._source = source
        self._handlers = handlers
        self._debug_enabled = debug_enabled

    # ---------- Публичные методы ----------

    def status(self, msg: str) -> None:
        """Краткое статусное сообщение для UI (Channel.STATUS)."""
        self._emit(Severity.LOW, Channel.STATUS, msg)

    def info(self, msg: str) -> None:
        """Сводное сообщение домена (Channel.INFO_LOG)."""
        self._emit(Severity.MEDIUM, Channel.INFO_LOG, msg)

    def report(self, msg: str) -> None:
        """Пошаговое сообщение журнала сервиса (Channel.REPORT)."""
        self._emit(Severity.MEDIUM, Channel.REPORT, msg)

    def notify(self, msg: str) -> None:
        """Всплывающее уведомление (Channel.NOTIFICATION)."""
        self._emit(Severity.LOW, Channel.NOTIFICATION, msg)

    def warning(self, msg: str) -> None:
        """Предупреждение (Channel.WARNING_FILE)."""
        self._emit(Severity.HIGH, Channel.WARNING_FILE, msg)

    def critical(self, msg: str, can_influence: bool = True) -> None:
        """Критическое сообщение (Channel.ERROR_FILE).

        Вход:
            msg — текст.
            can_influence — может ли пользователь повлиять на ситуацию.
                            True → MessageDialog, False → NotificationDialog.
        """
        self._emit(
            Severity.CRITICAL, Channel.ERROR_FILE, msg,
            can_influence=can_influence,
        )

    def debug(self, msg: str) -> None:
        """Отладочное сообщение (Channel.DEBUG_FILE).

        Роль: если debug_enabled=False — ничего не делает.
        """
        if self._debug_enabled:
            self._emit(Severity.LOW, Channel.DEBUG_FILE, msg)

    # ---------- Внутренние ----------

    def _emit(self, severity: Severity, channel: Channel,
              message: str, can_influence: bool = None) -> None:
        """Формирует LogRecordV2 и рассылает по handlers.

        Вход:
            severity — важность.
            channel — канал.
            message — текст.
            can_influence — если None, используется дефолт LogRecordV2 (True).
        Роль: единая точка рассылки. Handler'ы фильтруют сами.
        """
        kwargs = {
            "severity": severity,
            "channel": channel,
            "message": message,
            "source": self._source,
        }
        if can_influence is not None:
            kwargs["can_influence"] = can_influence

        record = LogRecordV2(**kwargs)

        for handler in self._handlers:
            if handler._should_handle(record):
                handler.emit(record)