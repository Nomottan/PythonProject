from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional
from utils.kiz_storage import KizStorage

class ValidationResult(Enum):
    """Результат валидации КИЗа для продажи.

    ADDED — КИЗ прошёл валидацию и записан в used_kiz.json.
    SKIPPED_NO_RETURN — КИЗ уже продан и не возвращён → отсев.
    SKIPPED_DATE_BEFORE_RETURN — дата продажи не позже даты возврата → отсев.
    SKIPPED_DUPLICATE — дубликат внутри отчёта (используется сервисом,
                        не самим валидатором).
    """
    ADDED = "added"
    SKIPPED_NO_RETURN = "skipped_no_return"
    SKIPPED_DATE_BEFORE_RETURN = "skipped_date_before_return"
    SKIPPED_DUPLICATE = "skipped_duplicate"

class KizValidator:
    """
    Валидатор КИЗов. Использует KizStorage для доступа к данным.
    Реализует бизнес-логику для Отчётов МП, ЧЗ МП и Возвратов.
    """

    def __init__(self, storage: KizStorage) -> None:
        self.storage = storage

    # ---------- Управление хранилищем ----------

    def load(self) -> None:
        """Загружает данные из used_kiz.json."""
        self.storage.load()

    def batch(self):
        """Прокси к KizStorage.batch().

        Возвращает контекстный менеджер, чтобы сервисы могли писать
        with self.kiz_validator.batch(): и не зависеть от внутреннего
        устройства KizStorage.

        Вход: нет.
        Выход: _BatchContext.
        Роль: единая точка группировки сохранений для всех сервисов.
        """
        return self.storage.batch()

    def set_log_path(self, work_dir: Path) -> None:
        """Устанавливает путь к логу kiz_validation.log в рабочей папке."""
        self.storage.set_log_path(work_dir)

    def clean_old_entries(self, months: int = 1) -> int:
        """Очищает старые записи и логирует результат."""
        deleted = self.storage.clean_old_entries(months)
        self.storage._log(f"Очистка старых записей: удалено {deleted} записей.")
        return deleted

    # ---------- Валидация для продаж (Отчёты МП и ЧЗ МП) ----------

    def validate_for_sale(self, kiz: str, sale_date_str: Optional[str] = None) -> ValidationResult:
        """Проверяет КИЗ для списания (продажа).

        Вход:
            kiz — 31-символьный КИЗ.
            sale_date_str — дата продажи из отчёта МП (формат "HH:MM:SS DD.MM.YYYY"
                            или "DD.MM.YYYY"). None — для ЧЗ_МП.

        Выход: ValidationResult.

        Роль: ЧЗ_МП — всегда ADDED с сегодняшней датой.
              Отчёт МП — правила отсева: продано без возврата, дата продажи
              раньше возврата. Обновление записи при возврате.
        """
        # --- ЧЗ_МП: без проверок, всегда списываем ---
        if sale_date_str is None:
            today_str = datetime.now().strftime("%d-%m-%Y")
            self.storage.add_or_update(kiz, today_str, None)
            self.storage._log(f"Списание (ЧЗ_МП): {kiz} – сегодня {today_str}")
            return ValidationResult.ADDED

        # --- Отчёт МП: парсим дату ---
        sale_dt = self._parse_date(sale_date_str)
        if sale_dt is None:
            sale_dt = datetime.now()
            self.storage._log(
                f"Не удалось распарсить дату '{sale_date_str}' для КИЗа {kiz}. "
                f"Использую сегодняшнюю."
            )
        sale_str = sale_dt.strftime("%d-%m-%Y")

        existing = self.storage.get(kiz)

        # 1. Новый КИЗ — списываем.
        if existing is None:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage._log(f"Списание (новый): {kiz} – продажа {sale_str}")
            return ValidationResult.ADDED

        existing_sold_str = existing.get("sold_date")
        existing_returned_str = existing.get("returned_date")

        # 2. Аномалия: нет даты продажи — списываем.
        if existing_sold_str is None:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage._log(f"Списание (аномалия, нет sold_date): {kiz} – продажа {sale_str}")
            return ValidationResult.ADDED

        # 3. Продано без возврата — отсев.
        if existing_returned_str is None:
            self.storage._log(f"Отсев (продано без возврата): {kiz}, продажа {existing_sold_str}")
            return ValidationResult.SKIPPED_NO_RETURN

        # 4. Есть и продажа, и возврат — сравниваем даты.
        existing_returned_dt = self._parse_date(existing_returned_str)
        if existing_returned_dt is None:
            self.storage._log(f"Отсев (битая дата возврата): {kiz}")
            return ValidationResult.SKIPPED_DATE_BEFORE_RETURN

        if sale_dt > existing_returned_dt:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage._log(f"Списание (возврат был раньше): {kiz}, продажа {sale_str}")
            return ValidationResult.ADDED
        else:
            self.storage._log(f"Отсев (дата продажи раньше возврата): {kiz}")
            return ValidationResult.SKIPPED_DATE_BEFORE_RETURN

    # ---------- Валидация для возвратов ----------
    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Парсит дату в одном из поддерживаемых форматов.

        Вход: date_str — строка даты.
        Выход: datetime или None, если не удалось распарсить.

        Роль: единая точка парсинга. Поддерживает формат отчёта МП
              ("HH:MM:SS DD.MM.YYYY" и "DD.MM.YYYY") и формат хранилища
              ("DD-MM-YYYY").
        """
        if not date_str:
            return None
        for fmt in ("%H:%M:%S %d.%m.%Y", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        return None

    def validate_for_return(self, kiz: str) -> bool:
        """
        Проверяет КИЗ для возврата.
        Если КИЗ есть в хранилище, обновляет дату возврата на сегодня и возвращает True.
        Если КИЗа нет – логирует и возвращает False.
        """
        existing = self.storage.get(kiz)
        if existing is None:
            self.storage._log(f"Возврат: КИЗ {kiz} отсутствует в хранилище, дата возврата не была зафиксирована")
            return True

        # КИЗ есть – обновляем дату возврата
        return_date = datetime.now().strftime("%d-%m-%Y")
        self.storage.add_or_update(kiz, existing["sold_date"], return_date)
        self.storage._log(f"Возврат: для КИЗа {kiz} установлена дата возврата {return_date}")
        return True