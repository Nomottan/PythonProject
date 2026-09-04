import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from utils.logger import ILogger


class PersistenceManager:
    """
    Сохраняет и восстанавливает состояние процесса между сессиями.
    Хранит JSON-файл в рабочей папке.
    """

    def __init__(self, work_folder: Path, logger: ILogger, filename: str = ".process_state.json"):
        self.logger = logger
        self.storage_path = work_folder / filename

    def load_state(self) -> Dict[str, Any]:
        """Загружает состояние из файла."""
        if not self.storage_path.exists():
            return {}

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.logger.debug(f"Загружено состояние из {self.storage_path.name}")
            return data
        except (json.JSONDecodeError, IOError) as e:
            self.logger.error(f"Ошибка загрузки состояния: {e}")
            return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        """Сохраняет состояние в файл."""
        try:
            # Добавляем мета-информацию
            state["_version"] = "1.0"
            state["_last_modified"] = datetime.now().isoformat()

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"Состояние сохранено в {self.storage_path.name}")
        except IOError as e:
            self.logger.error(f"Ошибка сохранения состояния: {e}")

    def reset_state(self) -> None:
        """Удаляет файл состояния."""
        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
                self.logger.debug("Файл состояния удалён")
            except Exception as e:
                self.logger.error(f"Ошибка удаления файла состояния: {e}")

    def reset_state(self) -> None:
        """Удаляет файл состояния."""
        if self.storage_path.exists():
            try:
                self.storage_path.unlink()
                self.logger.debug("Файл состояния удалён")
            except Exception as e:
                self.logger.error(f"Ошибка удаления файла состояния: {e}")