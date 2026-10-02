"""
Валидатор КИЗов.

Реализует бизнес-логику для Отчётов МП, ЧЗ МП и Возвратов поверх
KizStorage. Собственного состояния не хранит — вся память в storage.

Логирование — через публичные каналы storage (info / warning / error),
которые транслируются в LoggerV2. Отдельного лог-файла
kiz_validation.log больше нет: сообщения идут в errors.txt и UI-канал.
"""

from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional

from storage.fbs_kiz_storage import KizStorage
from utils.parsers import DateParser


class ValidationResult(Enum):
    """Результат валидации КИЗа для продажи.

    ADDED — КИЗ прошёл валидацию и записан в used_kiz.json.
    SKIPPED_NO_RETURN — КИЗ уже продан и не возвращён → отсев.
    SKIPPED_DATE_BEFORE_RETURN — дата продажи не позже даты возврата → отсев.
    """
    ADDED = "added"
    SKIPPED_NO_RETURN = "skipped_no_return"
    SKIPPED_DATE_BEFORE_RETURN = "skipped_date_before_return"


class KizValidator:
    """Валидатор КИЗов.

    Роль:
        Единая точка проверки КИЗа перед списанием/возвратом.
        Использует KizStorage для чтения и записи. Публичные
        методы возвращают ValidationResult или bool.
    """

    def __init__(self, storage: KizStorage) -> None:
        """Конструктор.

        Вход: storage — KizStorage с загруженными данными.
        Роль: сохраняет ссылку. Логгера своего нет — используется
              logger внутри storage (публичные каналы debug/info/
              warning/error).
        """
        self.storage = storage

    # ---------- Управление хранилищем ----------

    def load(self) -> None:
        """Загружает данные из used_kiz.json."""
        self.storage.load()

    def batch(self):
        """Прокси к KizStorage.batch().

        Выход: контекстный менеджер для групповой записи.
        Роль: единая точка группировки сохранений для сервисов.
        """
        return self.storage.batch()

    def set_log_path(self, work_dir: Path) -> None:
        """Совместимость с существующими вызовами.

        Вход: work_dir — рабочая папка задачи (не используется).

        Выход: нет.

        Роль:
            Заглушка. Раньше KizStorage писал в отдельный
            kiz_validation.log, и сервис передавал путь к нему.
            Теперь лог идёт через LoggerV2 (errors.txt + UI), а
            work_folder знает сам логгер. Метод сохранён, чтобы не
            править эталонные sells_fbs_service.py — там он
            вызывается из трёх мест.

        REPLACE: тело метода убрано. KizStorage.set_log_path
        удалён в Порции 4, а вызовы из сервисов сохранены.
        """
        # no-op: см. docstring.

    def clean_old_entries(self, months: int = 1) -> int:
        """Очищает старые записи в хранилище.

        Вход: months — порог в месяцах.
        Выход: количество удалённых записей.

        Роль:
            Делегирует в KizStorage. Логирование делает сам storage
            (info о результате). Здесь дополнительно не пишем —
            иначе в логе был бы дубль.

        REPLACE: было self.storage._log(f"Очистка старых записей:
        удалено {deleted} записей.") — убрано, KizStorage пишет это
        сам в своём info.
        """
        return self.storage.clean_old_entries(months)

    def remove_kizs(self, keys) -> int:
        """Удаляет пачку КИЗов из хранилища.

        Вход:
            keys — итерируемое ключей (КИЗов).

        Выход:
            int — сколько записей реально удалено.

        Роль:
            Тонкая обёртка над KizStorage.remove_many. Своего
            логирования нет: факт изменения памяти и пометка
            dirty — ответственность storage. Сохранение на диск —
            через self.batch() снаружи.
        """
        return self.storage.remove_many(keys)

    # ---------- Валидация для продаж (Отчёты МП и ЧЗ МП) ----------

    def validate_for_sale(self, kiz: str,
                          sale_date_str: Optional[str] = None
                          ) -> ValidationResult:
        """Проверяет КИЗ для списания (продажа).

        Вход:
            kiz — 31-символьный КИЗ.
            sale_date_str — дата продажи из отчёта МП
                            ("HH:MM:SS DD.MM.YYYY" или "DD.MM.YYYY").
                            None — для ЧЗ_МП.

        Выход: ValidationResult.

        Роль:
            ЧЗ_МП — всегда ADDED с сегодняшней датой.
            Отчёт МП — правила отсева: продано без возврата, дата
            продажи раньше возврата. Обновление записи при возврате.
        """
        # --- ЧЗ_МП: без проверок, всегда списываем ---
        if sale_date_str is None:
            today_str = datetime.now().strftime("%d-%m-%Y")
            self.storage.add_or_update(kiz, today_str, None)
            self.storage.info(
                f"Списание (ЧЗ_МП): {kiz} – сегодня {today_str}"
            )
            return ValidationResult.ADDED

        # --- Отчёт МП: парсим дату ---
        sale_dt = DateParser.parse_any(sale_date_str, DateParser.KIZ_FORMATS)
        if sale_dt is None:
            sale_dt = datetime.now()
            self.storage.warning(
                f"Не удалось распарсить дату '{sale_date_str}' "
                f"для КИЗа {kiz}. Использую сегодняшнюю."
            )
        sale_str = sale_dt.strftime("%d-%m-%Y")

        existing = self.storage.get(kiz)

        # 1. Новый КИЗ — списываем.
        if existing is None:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage.info(
                f"Списание (новый): {kiz} – продажа {sale_str}"
            )
            return ValidationResult.ADDED

        existing_sold_str = existing.get("sold_date")
        existing_returned_str = existing.get("returned_date")

        # 2. Аномалия: нет даты продажи — списываем.
        if existing_sold_str is None:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage.warning(
                f"Списание (аномалия, нет sold_date): {kiz} – "
                f"продажа {sale_str}"
            )
            return ValidationResult.ADDED

        # 3. Продано без возврата — отсев.
        if existing_returned_str is None:
            self.storage.info(
                f"Отсев (продано без возврата): {kiz}, "
                f"продажа {existing_sold_str}"
            )
            return ValidationResult.SKIPPED_NO_RETURN

        # 4. Есть и продажа, и возврат — сравниваем даты.
        existing_returned_dt = DateParser.parse_any(
            existing_returned_str, DateParser.KIZ_FORMATS,
        )
        if existing_returned_dt is None:
            self.storage.warning(
                f"Отсев (битая дата возврата): {kiz}"
            )
            return ValidationResult.SKIPPED_DATE_BEFORE_RETURN

        if sale_dt > existing_returned_dt:
            self.storage.add_or_update(kiz, sale_str, None)
            self.storage.info(
                f"Списание (возврат был раньше): {kiz}, "
                f"продажа {sale_str}"
            )
            return ValidationResult.ADDED
        else:
            self.storage.info(
                f"Отсев (дата продажи раньше возврата): {kiz}"
            )
            return ValidationResult.SKIPPED_DATE_BEFORE_RETURN

    # ---------- Валидация для возвратов ----------

    def validate_for_return(self, kiz: str) -> bool:
        """Проверяет КИЗ для возврата.

        Вход: kiz — 31-символьный КИЗ.
        Выход: True — обработано (даже если КИЗа не было в хранилище).

        Роль:
            Если КИЗ есть в хранилище — обновляет дату возврата на
            сегодня. Если нет — warning и возвращает True (сервис
            продолжает работу).
        """
        existing = self.storage.get(kiz)
        if existing is None:
            self.storage.warning(
                f"Возврат: КИЗ {kiz} отсутствует в хранилище, "
                f"дата возврата не была зафиксирована"
            )
            return True

        # КИЗ есть — обновляем дату возврата.
        return_date = datetime.now().strftime("%d-%m-%Y")
        self.storage.add_or_update(kiz, existing["sold_date"], return_date)
        self.storage.info(
            f"Возврат: для КИЗа {kiz} установлена дата возврата "
            f"{return_date}"
        )
        return True