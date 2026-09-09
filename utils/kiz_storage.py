import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

from utils.path_manager import PathManager


class KizStorage:
    """
    Управляет файлом used_kiz.json в папке Data.
    Хранит словарь {КИЗ: {"sold_date": "DD-MM-YYYY", "returned_date": "DD-MM-YYYY"}}.
    КИЗ всегда должен быть 31-символьной строкой (без криптохвоста).
    """

    def __init__(self, path_manager: PathManager) -> None:
        self._path_manager = path_manager
        self._data: Dict[str, Dict[str, Optional[str]]] = {}
        self._log_path: Optional[Path] = None
        self._file_path = self._path_manager.data_dir / "used_kiz.json"

    def set_log_path(self, work_dir: Path) -> None:
        self._log_path = work_dir / "kiz_validation.log"

    def _log(self, message: str) -> None:
        if self._log_path is None:
            return
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    # ---------- Основные методы ----------

    def load(self) -> None:
        if not self._file_path.exists():
            self._log("Файл used_kiz.json не найден, будет создан новый.")
            self._data = {}
            self.save()
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # --- МИГРАЦИЯ: обрезаем ключи до 31 символа ---
            from utils.kiz_utils import KizUtils
            migrated = False
            new_data = {}
            for kiz, record in raw_data.items():
                storage_list = KizUtils.clean_kiz_for_storage(kiz)
                if storage_list:
                    clean_kiz = storage_list[0]  # обычно один
                    if clean_kiz != kiz:
                        migrated = True
                        self._log(f"Миграция: {kiz[:30]}... → {clean_kiz}")
                    # Если ключ уже существует, перезаписываем (можно объединять даты, но упростим)
                    new_data[clean_kiz] = record
                else:
                    # Некорректный КИЗ – удаляем
                    self._log(f"Миграция: удалена некорректная запись {kiz[:30]}...")
                    migrated = True

            self._data = new_data
            if migrated:
                self.save()
                self._log("Миграция завершена: все ключи обрезаны до 31 символа, некорректные удалены.")
            # -------------------------------------

            self._log(f"Загружено {len(self._data)} записей из used_kiz.json")
        except Exception as e:
            self._log(f"Ошибка чтения: {e}. Создан новый словарь.")
            self._data = {}
            self.save()

    def save(self) -> None:
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception as e:
            self._log(f"Ошибка сохранения used_kiz.json: {e}")

    def get(self, kiz: str) -> Optional[Dict[str, Optional[str]]]:
        return self._data.get(kiz)

    def add_or_update(self, kiz: str, sold_date: str, returned_date: Optional[str] = None) -> None:
        self._data[kiz] = {"sold_date": sold_date, "returned_date": returned_date}
        self.save()

    # ---------- Очистка старых записей ----------

    def clean_old_entries(self, months: int = 1) -> int:
        if not self._data:
            self._log("Очистка: нет записей для удаления.")
            return 0

        cutoff = datetime.now() - timedelta(days=months * 30)
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
                self._log(f"Очистка: некорректная дата продажи '{sold_date_str}' для КИЗа {kiz}, запись пропущена")
                continue

        if not to_delete:
            self._log(f"Очистка: нет записей старше {months} месяца(ев).")
            return 0

        for kiz, sold_date_str in to_delete:
            del self._data[kiz]
            self._log(f"Очистка: удалён КИЗ {kiz} с датой продажи {sold_date_str}")

        self.save()
        self._log(f"Очистка завершена: удалено {len(to_delete)} записей.")
        return len(to_delete)

    # ---------- Дополнительные ----------

    def get_all(self) -> Dict[str, Dict[str, Optional[str]]]:
        return self._data.copy()

    def clear(self) -> None:
        self._data.clear()
        self.save()
        self._log("Все записи удалены.")