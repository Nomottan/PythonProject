"""
Подсистема логирования V2.

Параллельная инфраструктура для логирования. Не заменяет
старую utils/log_system/ — работает независимо, пока сервисы
не переведены на неё.

Реэкспортирует публичные классы для удобного импорта:
    from services.subservices.logging import (
        LoggerV2, LogManagerV2, Severity, Channel, LogRecordV2,
    )
"""

from .enums import Severity, Channel
from .record_v2 import LogRecordV2
from .handlers_v2 import (
    HandlerV2,
    NotificationHandler,
    StatusHandler,
    InfoFileHandler,
    InfoUIHandler,
    ReportHandler,
    WarningFileHandler,
    CriticalHandler,
    DebugFileHandler,
)
from .logger_v2 import LoggerV2
from .manager_v2 import LogManagerV2

__all__ = [
    "Severity",
    "Channel",
    "LogRecordV2",
    "HandlerV2",
    "NotificationHandler",
    "StatusHandler",
    "InfoFileHandler",
    "InfoUIHandler",
    "ReportHandler",
    "WarningFileHandler",
    "CriticalHandler",
    "DebugFileHandler",
    "LoggerV2",
    "LogManagerV2",
]