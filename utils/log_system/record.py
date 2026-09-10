"""
Запись лога.

Модуль определяет класс LogRecord — неизменяемую структуру, которая
передаётся от Logger к Handler'ам. Содержит уровень, сообщение и source.
"""

from dataclasses import dataclass

from utils.log_system.levels import LogLevel


@dataclass(frozen=True)
class LogRecord:
    """Одна запись лога.

    Назначение:
        Единица информации, которую Logger рассылает во все handlers.
        Handler'ы сами решают, писать ли её (по уровню) и куда.

    Поля:
        level: LogLevel — уровень записи.
        message: str — текст сообщения (может быть многострочным).
        source: str — «класс и модуль», например ExportKizService.sells_fbs_service.
                 Формируется вызывающим кодом и передаётся в Logger при создании.

    Почему frozen=True:
        Запись не должна меняться после создания — handler'ы могут читать
        её параллельно. Иммутабельность защищает от случайных мутаций.

    Почему без extra:
        Служебные данные передаются уже в готовой строке через LogMessages.
        Это упрощает API и убирает класс ошибок, связанных с типизацией
        произвольных полей.
    """

    level: LogLevel
    message: str
    source: str