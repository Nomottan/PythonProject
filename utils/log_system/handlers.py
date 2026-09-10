"""
Handler'ы логирования.

Каждый handler — это канал вывода: файл errors.txt, task-лог, debug.txt
или UI-колбэк. Handler сам фильтрует записи по уровню и сам защищает
себя от падений при ошибке записи.

Logger не знает о каналах — он просто вызывает emit() у каждого handler'а
в списке. Вся логика «куда и что писать» — здесь.
"""

import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from utils.log_system.levels import LogLevel
from utils.log_system.record import LogRecord


class Handler(ABC):
    """Базовый класс handler'а.

    Назначение:
        Общий каркас для всех каналов вывода. Задаёт метод _format
        и защиту _write_safe, которые используют наследники.

    Атрибуты:
        _path: Optional[Path] — путь к файлу (для файловых handler'ов)
               или None (для UI-колбэка).

    Роль в программе:
        Абстрактный родитель. Logger работает с ним через emit().
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        # Путь к файлу. Для UICallbackHandler — None, потому что запись
        # идёт не в файл, а через callback.
        self._path = path

    @abstractmethod
    def emit(self, record: LogRecord) -> None:
        """Обрабатывает одну запись.

        Вход: record — запись лога.
        Выход: нет.
        Роль: единственный метод, который вызывается из Logger._dispatch.
              Конкретные handler'ы решают, писать ли запись и куда.
        """

    def _format(self, record: LogRecord) -> str:
        """Формирует текст для записи.

        Вход: record — запись лога.
        Выход: строка вида "[source] message". Для многострочного
               сообщения префикс [source] ставится на КАЖДУЮ строку.

        Роль: единый формат для всех файловых handler'ов.
        """
        prefix = f"[{record.source}] "
        # Разбиваем по \n и к каждой непустой строке добавляем префикс.
        # Пустые строки оставляем как есть — чтобы не превращать
        # двойной перенос в строку из одного префикса.
        lines = record.message.split("\n")
        formatted = "\n".join(
            prefix + line if line else line for line in lines
        )
        return formatted

    def _write_safe(self, text: str) -> None:
        """Записывает текст в файл с защитой от исключений.

        Вход: text — готовый текст (результат _format).
        Выход: нет.
        Роль: общая точка записи для файловых handler'ов. При любой
              ошибке пишет сообщение в stderr и НЕ пробрасывает —
              логирование не должно ронять программу.
        """
        if self._path is None:
            # Файловые handler'ы всегда имеют путь. Если его нет —
            # это ошибка конфигурации; сообщаем в stderr.
            sys.stderr.write(
                f"[log_system.handlers] Handler без пути: {self.__class__.__name__}\n"
            )
            return

        try:
            # append-режим, utf-8 — не перезаписываем предыдущие записи.
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception as error:
            # Ошибку записи НЕ пробрасываем: программа должна работать,
            # даже если файл недоступен. Пишем в stderr напрямую,
            # минуя Logger — так исключаем рекурсию логирования.
            sys.stderr.write(
                f"[log_system.handlers] Не удалось записать в {self._path}: {error}\n"
            )


class ErrorFileHandler(Handler):
    """Handler для errors.txt в корне приложения.

    Назначение:
        Собирает все WARNING и ERROR в один файл рядом с main.py / .exe.
        Чтобы при сбое можно было быстро посмотреть, что пошло не так.

    Фильтр: только LogLevel.WARNING и LogLevel.ERROR.

    Роль в программе:
        Создаётся LogManager'ом всегда, независимо от задачи.
    """

    def emit(self, record: LogRecord) -> None:
        # Отсекаем INFO и DEBUG — в errors.txt попадают только проблемы.
        if record.level not in (LogLevel.WARNING, LogLevel.ERROR):
            return
        self._write_safe(self._format(record))


class TaskFileHandler(Handler):
    """Handler для task-лога (log_*.txt) в рабочей папке задачи.

    Назначение:
        Основной лог задачи. Пишет INFO, WARNING и ERROR. DEBUG сюда
        не попадает, даже если debug включён — это отдельный канал.

    Фильтр: всё, кроме LogLevel.DEBUG.

    Роль в программе:
        Создаётся LogManager'ом, если передан work_folder.
    """

    def emit(self, record: LogRecord) -> None:
        # DEBUG отсекаем, всё остальное пишем.
        if record.level == LogLevel.DEBUG:
            return
        self._write_safe(self._format(record))


class DebugFileHandler(Handler):
    """Handler для debug.txt в рабочей папке задачи.

    Назначение:
        Полный поток записей, включая DEBUG. Используется для отладки.

    Фильтр: все уровни без исключения.

    Роль в программе:
        Создаётся LogManager'ом ТОЛЬКО при включённом debug.
        При выключенном debug этот handler не должен появляться в списке.
    """

    def emit(self, record: LogRecord) -> None:
        # Никакой фильтрации — пишем всё.
        self._write_safe(self._format(record))


class UICallbackHandler(Handler):
    """Handler для вывода в UI через callback.

    Назначение:
        Передаёт сообщения в интерфейс, вызывая callback(message, level).
        DEBUG передаётся только при включённом debug.

    Атрибуты:
        _callback: Callable[[str, str], None] — функция из UI.
        _debug_enabled: bool — флаг, пропускать ли DEBUG.

    Роль в программе:
        Создаётся LogManager'ом, если в конструктор передан ui_callback.
    """

    def __init__(
        self,
        callback: Callable[[str, str], None],
        debug_enabled: bool = False,
    ) -> None:
        # У UI-канала нет файла — путь None.
        super().__init__(path=None)
        self._callback = callback
        self._debug_enabled = debug_enabled

    def emit(self, record: LogRecord) -> None:
        # Если запись — DEBUG, а debug выключен — тихо пропускаем.
        if record.level == LogLevel.DEBUG and not self._debug_enabled:
            return

        try:
            # Передаём текст сообщения без префикса [source]:
            # UI сам решает, как оформлять (метка, цвет, отдельная колонка).
            # level.value — строка вида "INFO", "WARNING", ...
            self._callback(record.message, record.level.value)
        except Exception as error:
            # Ошибка UI-колбэка не должна ронять логгер.
            sys.stderr.write(
                f"[log_system.handlers] Ошибка UI-колбэка: {error}\n"
            )