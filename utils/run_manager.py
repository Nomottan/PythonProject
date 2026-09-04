from pathlib import Path
from datetime import date
from typing import Optional, List
from utils.logger import ILogger
from utils.log_templates import LogTemplates


class RunManager:
    """
    Управление прогонами процесса.
    Хранит номер текущего прогона, управляет рабочей папкой и архивацией.
    """

    def __init__(self, target_dir: str, process_name: str, logger: ILogger):
        self.logger = logger
        self.process_name = process_name
        self.target_dir = Path(target_dir)

        # Определяем рабочую папку
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        self.work_folder_name = f"{process_name}_{date_str}"
        self.work_folder = self.target_dir / date_str / self.work_folder_name
        self.work_folder.mkdir(parents=True, exist_ok=True)

        # Файл с номером прогона
        self.run_number_file = self.work_folder / ".run_number"
        self.current_run_number = self._load_run_number()

    def _load_run_number(self) -> int:
        """Загружает номер прогона из файла, если есть."""
        if self.run_number_file.exists():
            try:
                return int(self.run_number_file.read_text().strip())
            except ValueError:
                return 1
        return 1

    def _save_run_number(self):
        """Сохраняет номер прогона в файл."""
        self.run_number_file.write_text(str(self.current_run_number))

    def get_work_folder(self) -> Path:
        """Возвращает текущую рабочую папку."""
        return self.work_folder

    def get_run_number(self) -> int:
        """Возвращает номер текущего прогона."""
        return self.current_run_number

    def is_work_folder_empty(self) -> bool:
        """Проверяет, есть ли в рабочей папке файлы (кроме служебных)."""
        for item in self.work_folder.iterdir():
            if item.name != ".run_number":
                return False
        return True

    def archive_current_run(self) -> int:
        """
        Архивирует текущий прогон: перемещает все файлы (кроме .run_number)
        в подпапку с номером прогона.
        Возвращает номер нового прогона.
        """
        if self.is_work_folder_empty():
            self.logger.debug("Рабочая папка пуста, архивация не требуется")
            return self.current_run_number

        # Создаём папку для архива
        archive_folder = self.work_folder / f"{self.current_run_number} прогон"
        archive_folder.mkdir(exist_ok=True)

        # Перемещаем все файлы и папки, кроме .run_number и самого архива
        for item in self.work_folder.iterdir():
            if item.name == ".run_number" or item == archive_folder:
                continue
            try:
                item.rename(archive_folder / item.name)
            except Exception as e:
                self.logger.error(f"Ошибка перемещения {item.name}: {e}")

        LogTemplates.run_archived(self.logger, self.current_run_number, archive_folder)

        # Увеличиваем номер прогона
        self.current_run_number += 1
        self._save_run_number()

        return self.current_run_number

    def get_archive_folders(self) -> List[Path]:
        """Возвращает список папок архива, отсортированных по номеру."""
        folders = []
        for item in self.work_folder.iterdir():
            if item.is_dir() and item.name.endswith(" прогон"):
                try:
                    num = int(item.name.split()[0])
                    folders.append((num, item))
                except ValueError:
                    continue
        # Сортируем по номеру
        folders.sort(key=lambda x: x[0])
        return [path for _, path in folders]

    def cleanup_old_archives(self, max_count: int = 5):
        """Удаляет старые архивы, оставляя только последние max_count."""
        folders = self.get_archive_folders()
        if len(folders) <= max_count:
            return
        for folder in folders[:-max_count]:
            try:
                import shutil
                shutil.rmtree(folder)
                self.logger.debug(f"Удалён старый архив: {folder.name}")
            except Exception as e:
                self.logger.error(f"Ошибка удаления {folder.name}: {e}")