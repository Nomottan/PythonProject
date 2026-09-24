"""
Запись лога V2.

LogRecordV2 — иммутабельный снимок одного сообщения: важность,
канал, текст, источник, время. Передаётся от LoggerV2 к handlers.
"""

from dataclasses import dataclass, field
from datetime import datetime

from .enums import Severity, Channel


@dataclass(frozen=True)
class LogRecordV2:
    """Иммутабельная запись лога.

    Поля:
        severity — важность сообщения.
        channel — канал доставки.
        message — текст сообщения.
        source — идентификатор источника ("Class.module").
        timestamp — момент создания. Если не передан — текущее время.
        can_influence — может ли пользователь повлиять на ситуацию
                        (для CriticalHandler: показывать MessageDialog
                        или NotificationDialog). По умолчанию True.

    Роль: единица передачи между LoggerV2 и HandlerV2. Иммутабельность
          гарантирует, что handler не сможет случайно изменить запись.
    """
    severity: Severity
    channel: Channel
    message: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    can_influence: bool = True