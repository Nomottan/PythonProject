"""
Пакет log_system — единый механизм логирования для проекта.

Публичный API:
    LogLevel — уровни логирования.
    LogRecord — одна запись лога.
    Handler — базовый класс канала вывода.
    Logger — рассылает записи по каналам.
    LogManager — фабрика логгеров.
    LogMessages — шаблоны сообщений.

Пакет изолирован: существующий код его не импортирует, кроме
test_logger.py. Интеграция — отдельный этап.
"""

from utils.log_system.levels import LogLevel
from utils.log_system.record import LogRecord
from utils.log_system.handlers import Handler
from utils.log_system.logger import Logger
from utils.log_system.manager import LogManager
from utils.log_system.messages import LogMessages

__all__ = [
    "LogLevel",
    "LogRecord",
    "Handler",
    "Logger",
    "LogManager",
    "LogMessages",
]