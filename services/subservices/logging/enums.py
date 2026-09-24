"""
Перечисления для подсистемы логирования V2.

Содержит Severity (важность) и Channel (канал доставки).
Разделение важно: одна важность может идти в разные каналы
(например, WARNING — в файл предупреждений, CRITICAL — в errors.txt
и UI).
"""

from enum import Enum


class Severity(Enum):
    """Важность сообщения.

    Значения:
        LOW      — общая информация (статусы, отладочные сообщения).
        MEDIUM   — значимая информация (отчёты, сводки).
        HIGH     — предупреждения.
        CRITICAL — критические события, требующие внимания пользователя.

    Роль: определяет, насколько сообщение важно. Handler'ы могут
          фильтровать по severity, а UI — подсвечивать цветом.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Channel(Enum):
    """Канал доставки сообщения.

    Значения:
        NOTIFICATION  — всплывающее уведомление в UI.
        STATUS        — обновление статусной строки в UI.
        INFO_LOG      — сводный Info-файл домена.
        REPORT        — пошаговый журнал сервиса.
        WARNING_FILE  — файл предупреждений.
        ERROR_FILE    — файл ошибок в корне приложения.
        DEBUG_FILE    — отладочный файл.

    Роль: определяет, куда именно handler должен доставить запись.
          Один LoggerV2 рассылает запись во все handlers, а те сами
          решают по каналу, обрабатывать её или нет.
    """
    NOTIFICATION = "notification"
    STATUS = "status"
    INFO_LOG = "info_log"
    REPORT = "report"
    WARNING_FILE = "warning_file"
    ERROR_FILE = "error_file"
    DEBUG_FILE = "debug_file"