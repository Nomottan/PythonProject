import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from utils.path_manager import PathManager


class KizStorage:
    """
    Управляет файлом used_kiz.json в папке Data.
    Хранит словарь {КИЗ: {"sold_date": "DD-MM-YYYY", "returned_date": "DD-MM-YYYY"}}.
    """

    def __init__(self, path_manager: PathManager) -> None:
        """
        Сохраняет ссылку на PathManager и инициализирует пустые данные.
        """
        self._path_manager = path_manager
        self._data: Dict[str, Dict[str, Optional[str]]] = {}
        self._log_path: Optional[Path] = None

        # Полный путь к файлу used_kiz.json
        self._file_path = self._path_manager.data_dir / "used_kiz.json"

    # ---------- Настройка логирования ----------

    def set_log_path(self, work_dir: Path) -> None:
        """
        Устанавливает путь к файлу kiz_validation.log в рабочей папке.
        Должен быть вызван перед началом работы с КИЗами в каждой сессии.
        """
        self._log_path = work_dir / "kiz_validation.log"

    def _log(self, message: str) -> None:
        """
        Записывает сообщение в kiz_validation.log с временной меткой.
        Если путь не установлен или запись невозможна, ошибка игнорируется.
        """
        if self._log_path is None:
            return
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            # Не прерываем работу программы из-за ошибки логирования
            pass

    # ---------- Основные методы работы с данными ----------

    def load(self) -> None:
        """
        Загружает данные из used_kiz.json.
        Если файл отсутствует или повреждён, создаёт новый пустой словарь.
        """
        if not self._file_path.exists():
            self._log("Файл used_kiz.json не найден, будет создан новый.")
            self._data = {}
            self.save()
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
            self._log(f"Загружено {len(self._data)} записей из used_kiz.json")
        except json.JSONDecodeError as e:
            self._log(f"Ошибка парсинга JSON: {e}. Будет создан новый пустой словарь.")
            self._data = {}
            self.save()
        except Exception as e:
            self._log(f"Ошибка чтения файла: {e}. Будет создан новый пустой словарь.")
            self._data = {}
            self.save()

    def save(self) -> None:
        """
        Сохраняет текущие данные в used_kiz.json.
        """
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception as e:
            self._log(f"Ошибка сохранения used_kiz.json: {e}")

    def get(self, kiz: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Возвращает запись для указанного КИЗа (словарь с sold_date и returned_date)
        или None, если КИЗ отсутствует.
        """
        return self._data.get(kiz)

    def add_or_update(self, kiz: str, sold_date: str, returned_date: Optional[str] = None) -> None:
        """
        Добавляет или обновляет запись для КИЗа.
        После изменения автоматически сохраняет файл.
        """
        self._data[kiz] = {
            "sold_date": sold_date,
            "returned_date": returned_date
        }
        self.save()

    # ---------- Очистка старых записей ----------

    def clean_old_entries(self, months: int = 1) -> int:
        """
        Удаляет записи, у которых дата продажи старше указанного количества месяцев.
        Возвращает количество удалённых записей.
        Каждая удалённая запись логируется в kiz_validation.log.
        """
        if not self._data:
            self._log("Очистка: нет записей для удаления.")
            return 0

        # Вычисляем граничную дату (текущая дата минус months месяцев)
        cutoff = datetime.now() - timedelta(days=months * 30)  # приблизительно

        to_delete = []
        for kiz, record in self._data.items():
            sold_date_str = record.get("sold_date")
            if not sold_date_str:
                continue
            try:
                sold_date = datetime.strptime(sold_date_str, "%d-%m-%Y")
                if sold_date < cutoff:
                    to_delete.append((kiz, sold_date_str))
            except ValueError:
                # Некорректный формат даты – пропускаем запись
                self._log(f"Очистка: некорректная дата продажи '{sold_date_str}' для КИЗа {kiz}, запись пропущена")
                continue

        if not to_delete:
            self._log(f"Очистка: нет записей старше {months} месяца(ев).")
            return 0

        # Удаляем записи
        for kiz, sold_date_str in to_delete:
            del self._data[kiz]
            self._log(f"Очистка: удалён КИЗ {kiz} с датой продажи {sold_date_str}")

        self.save()
        self._log(f"Очистка завершена: удалено {len(to_delete)} записей.")
        return len(to_delete)

    # ---------- Дополнительные методы (для удобства) ----------

    def get_all(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Возвращает копию всех данных (для отладки)."""
        return self._data.copy()

    def clear(self) -> None:
        """Очищает все данные (использовать с осторожностью)."""
        self._data.clear()
        self.save()
        self._log("Все записи удалены.")