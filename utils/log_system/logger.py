"""
Logger — центральный узел пакета.

Принимает запись от вызывающего кода и рассылает её во все handlers.
Сам не знает о каналах: фильтрация — ответственность handler'ов.
"""

import sys
from typing import List

from utils.log_system.handlers import Handler
from utils.log_system.levels import LogLevel
from utils.log_system.record import LogRecord


class Logger:
    """Рассылает записи лога во все handler'ы.

    Назначение:
        Единая точка входа для кода, который хочет что-то залогировать.
        Никакой фильтрации по уровням здесь нет — только формирование
        LogRecord и последовательный вызов handler.emit().

    Атрибуты:
        _source: str — «класс и модуль», попадает в LogRecord.source.
        _handlers: List[Handler] — список каналов вывода.
        _debug_enabled: bool — нужно ли вообще формировать DEBUG-записи.

    Роль в программе:
        Создаётся через LogManager.create_logger(). Напрямую код
        приложения его не инстанцирует.
    """

    def __init__(
        self,
        source: str,
        handlers: List[Handler],
        debug_enabled: bool = False,
    ) -> None:
        self._source = source
        self._handlers = handlers
        self._debug_enabled = debug_enabled

    def debug(self, message: str) -> None:
        """Отладочное сообщение.

        Если debug выключен — ничего не делаем: даже LogRecord
        не создаём, чтобы не тратить ресурсы.
        """
        if not self._debug_enabled:
            return
        self._dispatch(LogRecord(LogLevel.DEBUG, message, self._source))

    def info(self, message: str) -> None:
        """Информационное сообщение."""
        self._dispatch(LogRecord(LogLevel.INFO, message, self._source))

    def warning(self, message: str) -> None:
        """Предупреждение."""
        self._dispatch(LogRecord(LogLevel.WARNING, message, self._source))

    def error(self, message: str) -> None:
        """Ошибка."""
        self._dispatch(LogRecord(LogLevel.ERROR, message, self._source))

    def _dispatch(self, record: LogRecord) -> None:
        """Рассылает запись во все handler'ы.

        Вход: record — готовая запись лога.
        Выход: нет.

        Роль: единственная точка рассылки. Каждый handler вызывается
              в собственном try/except: падение одного канала не должно
              мешать остальным. Ошибка handler'а уходит в stderr.
        """
        for handler in self._handlers:
            try:
                handler.emit(record)
            except Exception as error:
                # Пишем в stderr напрямую, минуя Logger — так исключаем
                # бесконечную рекурсию, если проблемный handler логирует сам.
                sys.stderr.write(
                    f"[log_system.logger] Ошибка в handler {handler}: {error}\n"
                )