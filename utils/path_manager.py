import sys
from pathlib import Path
from typing import Union


class PathManager:
    """
    Единый источник путей для всего приложения.

    Автоматически определяет корневую папку:
        - при запуске скомпилированного .exe — папка, где лежит .exe
        - при разработке (из скрипта) — папка на два уровня выше от этого файла
          (предполагается, что класс лежит в utils/)
    """

    def __init__(self) -> None:
        # 1. Определяем корень программы
        if getattr(sys, 'frozen', False):
            # Скомпилированный .exe
            self._base_dir = Path(sys.executable).parent
        else:
            # Режим разработки: файл лежит в utils/, поднимаемся на два уровня вверх
            self._base_dir = Path(__file__).parent.parent

        # 2. Папка со служебными данными — всегда рядом с корнем
        self._data_dir = self._base_dir / "Data"

        # 3. Создаём Data, если её нет
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Не удалось создать служебную папку Data: {e}")

    # ---------- Свойства для доступа к основным служебным файлам ----------

    @property
    def config_file(self) -> Path:
        """Путь к файлу конфигурации config.json (находится внутри Data)."""
        return self._data_dir / "config.json"

    @property
    def mappings_file(self) -> Path:
        """Путь к файлу маппингов mappings.json (находится внутри Data)."""
        return self._data_dir / "mappings.json"

    # ---------- Универсальный метод для получения любого файла внутри Data ----------

    def get_data_file(self, filename: str) -> Path:
        """
        Возвращает путь к произвольному файлу внутри папки Data.

        Пример: get_data_file("temp/report.xlsx") -> Path(Data/temp/report.xlsx)
        """
        return self._data_dir / filename

    # ---------- Работа с пользовательскими папками ----------

    @staticmethod
    def ensure_dir(path: Union[str, Path]) -> Path:
        """
        Создаёт все родительские папки по указанному пути (если их нет)
        и возвращает объект Path.

        Используется для гарантии, что пользовательская папка существует
        перед записью в неё файлов.
        """
        path_obj = Path(path)
        path_obj.mkdir(parents=True, exist_ok=True)
        return path_obj

    @staticmethod
    def get_subdir(base_path: Union[str, Path],
                   subfolder: str,
                   create: bool = True) -> Path:
        """
        Строит путь base_path / subfolder.
        Если create=True (по умолчанию), создаёт эту подпапку (со всеми родителями).

        Пример: get_subdir("C:/Reports", "2026-09-07") -> C:/Reports/2026-09-07
        """
        full_path = Path(base_path) / subfolder
        if create:
            full_path.mkdir(parents=True, exist_ok=True)
        return full_path

    # ---------- Вспомогательный метод для разрешения относительных путей ----------

    def resolve(self, path: Union[str, Path]) -> Path:
        """
        Преобразует переданный путь в абсолютный.
        Если путь относительный, он считается относительно папки Data.
        Если абсолютный — возвращается как есть.

        Это полезно, если в будущем ты захочешь хранить в конфиге
        относительные пути (например, "./templates").
        """
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return (self._data_dir / path_obj).resolve()

    # ---------- Свойство для получения корня (на случай, если понадобится) ----------

    @property
    def app_root(self) -> Path:
        """Корневая папка приложения (где лежит .exe или main.py)."""
        return self._base_dir

    @property
    def data_dir(self) -> Path:
        """Папка Data (служебная)."""
        return self._data_dir
