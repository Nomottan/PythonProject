import sys
from pathlib import Path

class PathManager:
    """
    Управление путями приложения.
    Определяет базовую папку (где находится .exe или скрипт) и предоставляет методы
    для получения стандартных путей к data, logs, рабочей папке и т.д.
    """
    _instance = None  # можно сделать синглтон, если нужно, но не обязательно

    def __init__(self):
        self._base_path = self._determine_base_path()

    def _determine_base_path(self) -> Path:
        """Определяет базовую папку приложения."""
        if getattr(sys, 'frozen', False):
            return Path(sys.executable).parent
        else:
            # В режиме разработки — папка проекта (на уровень выше utils)
            return Path(__file__).parent.parent

    def get_base_path(self) -> Path:
        return self._base_path

    def get_data_path(self) -> Path:
        """Возвращает путь к папке data."""
        return self._base_path / "data"

    def get_logs_path(self) -> Path:
        """Возвращает путь к папке logs (для отладочных логов)."""
        return self._base_path / "logs"

    def get_default_working_dir(self) -> Path:
        """Возвращает путь к папке по умолчанию для рабочих файлов."""
        return self._base_path / "рабочие_папки"

    def ensure_data_dir(self) -> Path:
        """Создаёт папку data, если её нет, и возвращает путь."""
        path = self.get_data_path()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_logs_dir(self) -> Path:
        """Создаёт папку logs, если её нет, и возвращает путь."""
        path = self.get_logs_path()
        path.mkdir(parents=True, exist_ok=True)
        return path


class AppPaths:
    """
    Класс для работы с путями приложения.
    Определяет базовую директорию (где находится .exe или исходный скрипт)
    и предоставляет методы для получения путей к подпапкам.
    """
    def __init__(self):
        self._base_path = self._determine_base_path()

    def _determine_base_path(self) -> Path:
        """Определяет базовую директорию приложения."""
        if getattr(sys, 'frozen', False):
            # Запущено из собранного .exe
            return Path(sys.executable).parent
        else:
            # Запущено из скрипта – поднимаемся на уровень выше папки utils
            return Path(__file__).parent.parent

    def get_base_path(self) -> Path:
        """Возвращает базовую директорию."""
        return self._base_path

    def get_data_path(self) -> Path:
        """Возвращает путь к папке data."""
        return self._base_path / "data"

    def get_logs_path(self) -> Path:
        """Возвращает путь к папке logs (для отладочных логов)."""
        return self._base_path / "logs"

    def get_config_path(self) -> Path:
        """Возвращает путь к файлу config.json."""
        return self.get_data_path() / "config.json"

    def get_tasks_path(self) -> Path:
        """Возвращает путь к файлу tasks.json."""
        return self.get_data_path() / "tasks.json"

    def get_archive_path(self) -> Path:
        """Возвращает путь к файлу archive.json."""
        return self.get_data_path() / "archive.json"

    def get_mappings_path(self) -> Path:
        """Возвращает путь к файлу mappings.json."""
        return self.get_data_path() / "mappings.json"

    def ensure_directories(self):
        """Создаёт все необходимые папки, если их нет."""
        self.get_data_path().mkdir(parents=True, exist_ok=True)
        self.get_logs_path().mkdir(parents=True, exist_ok=True)