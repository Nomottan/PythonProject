from abc import ABC, abstractmethod
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class ILogger:
    """Интерфейс логгера (без ABC, чтобы избежать конфликта метаклассов с QObject)."""
    def debug(self, msg: str) -> None:
        raise NotImplementedError
    def info(self, msg: str) -> None:
        raise NotImplementedError
    def warning(self, msg: str) -> None:
        raise NotImplementedError
    def error(self, msg: str) -> None:
        raise NotImplementedError
    def report(self, msg: str) -> None:
        raise NotImplementedError


class ConsoleLogger(ILogger):
    def debug(self, msg): print(f"[DEBUG] {msg}")
    def info(self, msg): print(f"[INFO] {msg}")
    def warning(self, msg): print(f"[WARNING] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def report(self, msg): print(f"[REPORT] {msg}")


class FileLogger(ILogger):
    def __init__(self, filepath: str | Path, level: str = "debug"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.level = level
        self._levels = {"debug": 0, "info": 1, "warning": 2, "error": 3, "report": 4}
        with open(self.filepath, 'w', encoding='utf-8') as f:
            pass

    def _write(self, level_name: str, msg: str):
        if self._levels.get(level_name, 0) >= self._levels.get(self.level, 0):
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(f"{level_name.upper()}: {msg}\n")

    def debug(self, msg): self._write('debug', msg)
    def info(self, msg): self._write('info', msg)
    def warning(self, msg): self._write('warning', msg)
    def error(self, msg): self._write('error', msg)
    def report(self, msg): self._write('report', msg)


class ReportFileLogger(ILogger):
    def __init__(self, filepath: str | Path):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            pass

    def _write(self, level_name: str, msg: str):
        if level_name in ('report', 'error'):
            with open(self.filepath, 'a', encoding='utf-8') as f:
                f.write(f"{level_name.upper()}: {msg}\n")

    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): self._write('error', msg)
    def report(self, msg): self._write('report', msg)


class QtStatusLogger(QObject, ILogger):
    log_signal = Signal(str, int)

    def __init__(self, min_level: int = 1):  # 0=DEBUG, 1=INFO, 2=WARNING, 3=ERROR, 4=REPORT
        super().__init__()
        self.min_level = min_level

    def debug(self, msg):
        if 0 >= self.min_level:
            self.log_signal.emit(msg, 0)

    def info(self, msg):
        if 1 >= self.min_level:
            self.log_signal.emit(msg, 1)

    def warning(self, msg):
        if 2 >= self.min_level:
            self.log_signal.emit(msg, 2)

    def error(self, msg):
        if 3 >= self.min_level:
            self.log_signal.emit(msg, 3)

    def report(self, msg):
        if 4 >= self.min_level:
            self.log_signal.emit(msg, 4)


class CompositeLogger(ILogger):
    def __init__(self, loggers: list[ILogger] = None):
        self._loggers = loggers or []

    def add_logger(self, logger: ILogger):
        self._loggers.append(logger)

    def remove_logger(self, logger: ILogger):
        if logger in self._loggers:
            self._loggers.remove(logger)

    def debug(self, msg):
        for l in self._loggers:
            l.debug(msg)

    def info(self, msg):
        for l in self._loggers:
            l.info(msg)

    def warning(self, msg):
        for l in self._loggers:
            l.warning(msg)

    def error(self, msg):
        for l in self._loggers:
            l.error(msg)

    def report(self, msg):
        for l in self._loggers:
            l.report(msg)