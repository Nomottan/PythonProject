"""
LogManager — фабрика логгеров.

Хранит общий флаг debug и ui_callback, а по запросу собирает Logger
с правильным набором handler'ов для конкретной задачи.
"""

from pathlib import Path
from typing import Callable, List, Optional

from utils.log_system.handlers import (
    DebugFileHandler,
    ErrorFileHandler,
    Handler,
    TaskFileHandler,
    UICallbackHandler,
)
from utils.log_system.logger import Logger
from utils.path_manager import PathManager


class LogManager:
    """Создаёт Logger'ы с нужным набором каналов.

    Назначение:
        Одна точка конфигурации логирования на всё приложение. Задаёт
        ui_callback и флаг debug, а create_logger() собирает под каждую
        задачу корректный список handler'ов.

    Атрибуты:
        _ui_callback: Optional[Callable[[str, str], None]] — колбэк в UI.
        _debug_enabled: bool — флаг отладки в памяти (не сохраняется).

    Важно:
        Не потокобезопасен. set_debug может вызываться из UI-потока,
        а Logger — из фонового. Это потенциальная гонка, но вне
        текущего скоупа — сейчас приложение однопоточное в этом месте.

    Роль в программе:
        Создаётся один раз (не синглтон!) и передаётся сервисам,
        которым нужно получать логгеры.
    """

    def __init__(
        self,
        ui_callback: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        # Сохраняем колбэк, если он был передан. Используется при
        # создании UICallbackHandler в каждом логгере.
        self._ui_callback = ui_callback
        # Флаг debug — только в памяти, между запусками не сохраняется.
        self._debug_enabled = False

    def set_debug(self, enabled: bool) -> None:
        """Включает или выключает режим отладки.

        Вход: enabled — True, если debug нужно включить.
        Выход: нет.
        Роль: переключатель для UI-кнопки (в следующем этапе).
        """
        self._debug_enabled = enabled

    def is_debug(self) -> bool:
        """Возвращает текущее состояние флага debug."""
        return self._debug_enabled

    def create_logger(
        self,
        source: str,
        work_folder: Optional[Path] = None,
        log_filename: Optional[str] = None,
    ) -> Logger:
        """Собирает Logger с набором handler'ов под конкретную задачу.

        Вход:
            source — «класс и модуль» для префикса [source].
            work_folder — рабочая папка задачи; None, если её нет.
            log_filename — имя task-лога; None → "log_task.txt".

        Выход: Logger с готовым списком handler'ов.

        Роль: единственный способ создать логгер. Матрица каналов:
            - work_folder=None: только errors.txt.
            - work_folder задан: errors.txt + task-лог (+ UI, + debug.txt).
        """
        handlers: List[Handler] = []

        # 1. errors.txt — всегда. Путь берём из PathManager, чтобы
        #    файл лежал рядом с main.py / .exe, а не в рабочей папке.
        app_root = PathManager().app_root
        handlers.append(ErrorFileHandler(app_root / "errors.txt"))

        # 2. Task-лог — только если есть рабочая папка.
        if work_folder is not None:
            # Имя по умолчанию, если явно не задано.
            filename = log_filename if log_filename is not None else "log_task.txt"
            handlers.append(TaskFileHandler(work_folder / filename))

        # 3. UI-канал — только если был передан ui_callback.
        if self._ui_callback is not None:
            handlers.append(
                UICallbackHandler(
                    self._ui_callback,
                    debug_enabled=self._debug_enabled,
                )
            )

        # 4. debug.txt — только при включённом debug и наличии work_folder.
        #    Если work_folder нет, писать debug.txt некуда.
        if self._debug_enabled and work_folder is not None:
            handlers.append(DebugFileHandler(work_folder / "debug.txt"))

        return Logger(source, handlers, debug_enabled=self._debug_enabled)