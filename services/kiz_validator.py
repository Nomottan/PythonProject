"""
Валидатор КИЗов.

Реализует бизнес-логику для Отчётов МП, ЧЗ МП и Возвратов поверх
KizStorage. Собственного состояния не хранит — вся память в storage.

Логирование — через публичные каналы storage (report/warning/info),
которые транслируются в LoggerV2.
"""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Optional

from storage.fbs_kiz_storage import KizStorage
from utils.parsers import DateParser


class ValidationResult(Enum):
    """Результат валидации КИЗа для продажи.

    ADDED — КИЗ прошёл валидацию; при apply_sale будет записан
            в used_kiz.json.
    SKIPPED_NO_RETURN — КИЗ уже продан и не возвращён → отсев.
    SKIPPED_DATE_BEFORE_RETURN — дата продажи не позже даты возврата → отсев.
    """
    ADDED = "added"
    SKIPPED_NO_RETURN = "skipped_no_return"
    SKIPPED_DATE_BEFORE_RETURN = "skipped_date_before_return"

@dataclass
class SaleEvaluation:
    """Результат оценки КИЗа для продажи.

    Поля:
        result — ValidationResult решения.
        sold_date — дата продажи "DD-MM-YYYY", которую нужно
                    записать при ADDED; иначе None.

    Роль:
        Возвращается evaluate_for_sale. Позволяет отделить оценку
        от фактической записи в хранилище.
    """
    result: ValidationResult
    sold_date: Optional[str]

class KizValidator:
    """Валидатор КИЗов.

    Роль:
        Единая точка проверки КИЗа перед списанием/возвратом.
        Использует KizStorage для чтения и записи. Оценка продажи
        (evaluate_for_sale) не пишет; запись выполняет apply_sale.
        Публичные методы возвращают SaleEvaluation, ValidationResult
        или bool.
    """

    def __init__(self, storage: KizStorage, dry_run: bool = False,
                 ignore_existing: bool = False) -> None:
        """Конструктор.

        Вход:
            storage — KizStorage с загруженными данными.
            dry_run — если True, apply_sale и validate_for_return
                      не вызывают storage.add_or_update.
                      report/warning идут в storage как обычно.
            ignore_existing — если True, evaluate_for_sale ведёт
                      себя так, будто КИЗа в базе нет (ADDED с
                      fallback по дате). Допустим только при
                      dry_run=True — иначе ValueError.
                      Смысл: DataVerificationService считает
                      «что было бы в чистой базе», не завися от
                      истории списаний.

        Роль: сохраняет ссылку и флаги. Логгера своего нет —
              используется logger внутри storage (публичные
              каналы debug/report/warning/error).
        """
        if ignore_existing and not dry_run:
            raise ValueError(
                "ignore_existing допустим только при dry_run=True"
            )
        self.storage = storage
        self._dry_run = dry_run
        self._ignore_existing = ignore_existing

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

    def clean_old_entries(self, months: int = 1) -> int:
        """Очищает старые записи в хранилище.

        Вход: months — порог в месяцах.
        Выход: количество удалённых записей.

        Роль:
            Делегирует в KizStorage. Логирование делает сам storage
            (report о результате). Здесь дополнительно не пишем —
            иначе в логе был бы дубль.

        REPLACE: было self.storage._log(f"Очистка старых записей:
        удалено {deleted} записей.") — убрано, KizStorage пишет это
        сам в своём report.
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

    def evaluate_for_sale(self, kiz: str,
                          sale_date_str: Optional[str] = None
                          ) -> SaleEvaluation:
        """Оценивает КИЗ для списания, не записывая в хранилище.

        Вход:
            kiz — 31-символьный КИЗ.
            sale_date_str — дата продажи из отчёта МП
                            ("HH:MM:SS DD.MM.YYYY" или "DD.MM.YYYY").
                            None — для ЧЗ_МП.

        Выход:
            SaleEvaluation — результат оценки и дата продажи,
            которую нужно записать при ADDED.

        Роль:
            ЧЗ_МП — всегда ADDED с сегодняшней датой.
            Отчёт МП — правила отсева: продано без возврата, дата
            продажи раньше возврата. Метод ничего не пишет;
            фактическую запись выполняет apply_sale.
        """
        # --- ЧЗ_МП: без проверок, всегда списываем ---
        if sale_date_str is None:
            today_str = datetime.now().strftime("%d-%m-%Y")
            self.storage.report(
                f"Списание (ЧЗ_МП): {kiz} – сегодня {today_str}"
            )
            return SaleEvaluation(
                result=ValidationResult.ADDED,
                sold_date=today_str,
            )

        # --- Отчёт МП: парсим дату ---
        sale_dt = DateParser.parse_any(sale_date_str, DateParser.KIZ_FORMATS)
        if sale_dt is None:
            sale_dt = datetime.now()
            self.storage.warning(
                f"Не удалось распарсить дату '{sale_date_str}' "
                f"для КИЗа {kiz}. Использую сегодняшнюю."
            )
        sale_str = sale_dt.strftime("%d-%m-%Y")

        if self._ignore_existing:
            existing = None
        else:
            existing = self.storage.get(kiz)

        # 1. Новый КИЗ — списываем.
        if existing is None:
            self.storage.report(
                f"Списание (новый): {kiz} – продажа {sale_str}"
            )
            return SaleEvaluation(
                result=ValidationResult.ADDED,
                sold_date=sale_str,
            )

        existing_sold_str = existing.get("sold")
        existing_returned_str = existing.get("return")

        # 2. Аномалия: нет даты продажи — списываем.
        if existing_sold_str is None:
            self.storage.warning(
                f"Списание (аномалия, нет sold): {kiz} – "
                f"продажа {sale_str}"
            )
            return SaleEvaluation(
                result=ValidationResult.ADDED,
                sold_date=sale_str,
            )

        # 3. Продано без возврата — отсев.
        if existing_returned_str is None:
            self.storage.report(
                f"Отсев (продано без возврата): {kiz}, "
                f"продажа {existing_sold_str}"
            )
            return SaleEvaluation(
                result=ValidationResult.SKIPPED_NO_RETURN,
                sold_date=None,
            )

        # 4. Есть и продажа, и возврат — сравниваем даты.
        existing_returned_dt = DateParser.parse_any(
            existing_returned_str, DateParser.KIZ_FORMATS,
        )
        if existing_returned_dt is None:
            self.storage.warning(
                f"Отсев (битая дата возврата): {kiz}"
            )
            return SaleEvaluation(
                result=ValidationResult.SKIPPED_DATE_BEFORE_RETURN,
                sold_date=None,
            )

        if sale_dt > existing_returned_dt:
            self.storage.report(
                f"Списание (возврат был раньше): {kiz}, "
                f"продажа {sale_str}"
            )
            return SaleEvaluation(
                result=ValidationResult.ADDED,
                sold_date=sale_str,
            )
        else:
            self.storage.report(
                f"Отсев (дата продажи раньше возврата): {kiz}"
            )
            return SaleEvaluation(
                result=ValidationResult.SKIPPED_DATE_BEFORE_RETURN,
                sold_date=None,
            )

    def apply_sale(self, kiz: str, sold_date: str) -> None:
        """Записывает решение о продаже в хранилище.

        Вход:
            kiz — 31-символьный КИЗ.
            sold_date — дата продажи "DD-MM-YYYY".

        Выход: нет.

        Роль:
            Единственная точка фактической записи продажи. При
            dry_run=True ничего не делает. Вызывается либо из
            validate_for_sale (совместимость), либо из completion
            после создания ИТОГ.
        """
        if self._dry_run:
            return
        self.storage.add_or_update(kiz, sold_date, None)

    # ---------- Валидация для возвратов ----------

    def validate_for_return(self, kiz: str) -> bool:
        """Проверяет КИЗ для возврата.

        Вход: kiz — 31-символьный КИЗ.
        Выход: True — обработано (даже если КИЗа не было в хранилище).

        Роль:
            Если КИЗ есть в хранилище — обновляет дату возврата на
            сегодня. Если нет — warning и возвращает True (сервис
            продолжает работу). При dry_run=True add_or_update не
            вызывается; предупреждение и результат — те же.
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
        if not self._dry_run:
            self.storage.add_or_update(
                kiz, existing["sold"], return_date,
            )
        self.storage.report(
            f"Возврат: для КИЗа {kiz} установлена дата возврата "
            f"{return_date}"
        )
        return True