"""
Уровни логирования.

Модуль определяет единственный класс LogLevel — перечисление уровней,
используемых в пакете log_system. Значения используются в handler'ах
для фильтрации записей и в UICallbackHandler для передачи уровня
во внешний callback (в виде строки .value).
"""

from enum import Enum


class LogLevel(Enum):
    """Уровни логирования.

    Значения:
        DEBUG — отладочная информация, пишется только в debug.txt
                и в UI при включённом debug.
        INFO — обычные информационные сообщения.
        WARNING — предупреждения, попадают в errors.txt и task-лог.
        ERROR — ошибки, попадают во все каналы.

    Роль в программе:
        Единственный источник правды об уровнях. Handler'ы сравнивают
        record.level с LogLevel.*, а UI получает level.value в виде строки.
    """

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"