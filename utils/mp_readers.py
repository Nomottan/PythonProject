"""
Читатели отчётов МП: ЧЗ_МП, WB, Ozon.

Три класса-читателя плюс общая база:
    ChzMpReportReader     — разбирает файлы ЧЗ_МП.
    WBReportReader        — разбирает WB-отчёты МП.
    OZONReportReader      — разбирает Ozon-отчёты.
    MpReportTypeDetector  — определяет тип отчёта по первому листу.

Роль в программе:
    Читатели отвечают только за разбор Excel и возврат типизированных
    данных. Batch-контекст KizStorage, запись .txt — ответственность
    вызывающих сервисов. WB и Ozon наследуются от BaseMpReportReader,
    который держит общий каркас; специфика — в наследниках.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from utils.excel_helper import ExcelHelper, WorkbookOpener
from utils.kiz_utils import KizUtils, KizOccurrences
from utils.parsers import DateParser
from utils.text_utils import TextUtils
from services.kiz_validator import ValidationResult

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2


@dataclass
class ChzMpEntry:
    """Одна запись о КИЗе, прочитанном из файла ЧЗ_МП.

    Роль:
        Промежуточный результат ChzMpReportReader.read. Вызывающий
        код собирает из списка таких записей итоговые структуры
        (kiz_by_seller, счётчики), фильтруя по result.

    Поля:
        seller_name — имя продавца, определённого по имени листа.
        full_kiz — полный КИЗ, прошедший очистку.
        storage_kiz — 31-символьный КИЗ для записи в хранилище.
        result — результат KizValidator.validate_for_sale.
    """
    seller_name: str
    full_kiz: str
    storage_kiz: str
    result: ValidationResult


class MpReportTypeDetector:
    """Определяет тип отчёта МП по имени первого листа.

    Роль:
        WB-отчёты имеют первый лист «Сборочные задания»,
        Ozon-отчёты — «Отчет». Нормализация имени листа — через
        TextUtils.normalize + замена «ё» → «е» (на случай опечаток
        и раскладки). Иначе — None, файл копируется как неопознанный.
    """

    @staticmethod
    def detect(wb) -> Optional[str]:
        """Возвращает "wb", "ozon" или None.

        Вход: wb — открытый openpyxl workbook.
        Выход: тип отчёта или None.
        Роль: единая точка определения типа по первому листу.
        """
        if not wb.sheetnames:
            return None
        first = TextUtils.normalize(wb.sheetnames[0]).replace("ё", "е")
        if first == "отчет":
            return "ozon"
        if first == "сборочные задания":
            return "wb"
        return None


@dataclass
class MpReportData:
    """Агрегированный результат разбора одного отчёта МП.

    Роль:
        Возвращается BaseMpReportReader.read. Содержит и счётчики,
        и полезные данные (цены, полные КИЗы) для мержа в
        общесервисные структуры.

    Поля:
        seller — продавец, определённый по имени файла.
        added — сколько КИЗов прошло валидацию (result == ADDED).
        prices — dict {storage_kiz: int_price} для добавленных КИЗов.
        full_kizs — set полных КИЗов, добавленных в этом отчёте.
        skipped_dup — сколько вхождений отброшено как дубликаты.
        skipped_no_return — КИЗы, проданные без возврата.
        skipped_date_before_return — дата продажи раньше возврата.
        total_unique — всего уникальных storage_kiz в отчёте.
        skipped_by_type — dict {operation_type: count}.
    """
    seller: "Seller"
    added: int
    prices: dict
    full_kizs: set
    skipped_dup: int
    skipped_no_return: int
    skipped_date_before_return: int
    total_unique: int
    skipped_by_type: dict


class BaseMpReportReader:
    """База для читателей отчётов МП (WB, Ozon).

    Роль:
        Общий каркас: найти продавца, открыть workbook, проверить
        обязательные листы, загрузить вхождения, валидировать,
        собрать результат. Специфика — в наследниках.

    Атрибуты класса:
        _REQUIRED_SHEETS — обязательные листы. Пустое — не проверять.
        COLLECT_PRICES — собирать ли цены из отчёта.
        _DESCRIPTION — описание для сообщений WorkbookOpener.
    """

    _REQUIRED_SHEETS: tuple = ()
    COLLECT_PRICES: bool = False
    _DESCRIPTION: str = "отчёт МП"

    @classmethod
    def read(cls, report_path, sellers, kiz_validator,
             logger) -> Optional[MpReportData]:
        """Читает один отчёт МП.

        Вход:
            report_path — путь к файлу.
            sellers — список Seller.
            kiz_validator — KizValidator.
            logger — LoggerV2.

        Выход:
            MpReportData или None (файл не открылся, продавец не
            найден, нет обязательного листа).
        """
        seller = cls._find_seller(report_path, sellers, logger)
        if seller is None:
            return None

        wb = cls._open_workbook(report_path, logger)
        if wb is None:
            return None

        KizUtils.start_stats()
        try:
            if not cls._has_required_sheets(wb, logger):
                return None

            occurrences, skipped_by_type = cls._load_occurrences(wb, logger)
            dates = cls._load_dates(wb)

            result_dict = cls._validate_occurrences(
                occurrences, dates, kiz_validator, logger, seller,
            )

            return cls._build_result(seller, result_dict, skipped_by_type)
        finally:
            try:
                wb.close()
            except Exception:
                pass
            stats = KizUtils.pop_stats()
            cls._log_stats(logger, report_path, stats)

    # ---------- Точки переопределения ----------

    @classmethod
    def _find_seller(cls, report_path, sellers, logger):
        """Ищет продавца по имени файла.

        Дефолт: TextUtils.find_seller_by_file_name(stem.lower(), sellers).
        Наследник может переопределить.
        """
        report_path = Path(report_path)
        seller = TextUtils.find_seller_by_file_name(
            report_path.stem.lower(), sellers,
        )
        if seller is None:
            logger.report("  Не удалось определить продавца – пропущен")
        else:
            logger.report(f"  Продавец определён: {seller.name}")
        return seller

    @classmethod
    def _open_workbook(cls, report_path, logger):
        """Открывает workbook через WorkbookOpener."""
        report_path = Path(report_path)
        logger.report(f"Обработка отчёта: {report_path.name}")
        return WorkbookOpener.open(
            report_path, logger=logger, read_only=True,
            description=cls._DESCRIPTION,
        )

    @classmethod
    def _has_required_sheets(cls, wb, logger) -> bool:
        """Проверяет наличие обязательных листов."""
        for name in cls._REQUIRED_SHEETS:
            if name not in wb.sheetnames:
                logger.report(f"  Лист '{name}' отсутствует – пропущен")
                return False
        return True

    @classmethod
    def _load_dates(cls, wb) -> dict:
        """Загружает словарь дат. По умолчанию пустой."""
        return {}

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Загружает вхождения КИЗов.

        Выход:
            (KizOccurrences, skipped_by_type: dict[str, int]).

        Наследник обязан переопределить.
        """
        raise NotImplementedError

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки для одного вхождения.

        Вход:
            entry — (full_kiz, sort_value, price).
            dates — словарь из _load_dates.

        Выход:
            datetime или None.

        Наследник обязан переопределить.
        """
        raise NotImplementedError

    # ---------- Общая валидация ----------

    @classmethod
    def _validate_occurrences(cls, occurrences, dates, kiz_validator,
                              logger, seller) -> dict:
        """Общая валидация всех вхождений.

        Выход:
            dict с ключами:
                added, skipped_dup, skipped_no_return,
                skipped_date_before_return, prices, full_kizs,
                total_unique.
        """
        added = 0
        skipped_dup = 0
        skipped_no_return = 0
        skipped_date_before_return = 0
        prices: dict = {}
        full_kizs: set = set()

        for storage_kiz, _entries in occurrences.items():
            def key_func(entry):
                return cls._get_sort_key(entry, dates)

            chosen = occurrences.pick_latest(storage_kiz, key_func)
            if chosen is None:
                continue

            skipped_dup += chosen.skipped_dup_count

            sale_date_str = chosen.sale_date_str
            if sale_date_str is None:
                sale_date_str = datetime.now().strftime("%d-%m-%Y")

            result = kiz_validator.validate_for_sale(
                storage_kiz, sale_date_str,
            )

            if result == ValidationResult.ADDED:
                full_kizs.add(chosen.full_kiz)
                added += 1
                if cls.COLLECT_PRICES and chosen.price is not None:
                    prices[storage_kiz] = int(chosen.price)
            elif result == ValidationResult.SKIPPED_NO_RETURN:
                skipped_no_return += 1
            elif result == ValidationResult.SKIPPED_DATE_BEFORE_RETURN:
                skipped_date_before_return += 1

        total_unique = (
            added + skipped_no_return + skipped_date_before_return
            + skipped_dup
        )

        cls._log_skipped(
            logger, skipped_dup, skipped_no_return,
            skipped_date_before_return, total_unique, added, seller,
        )

        return {
            "added": added,
            "skipped_dup": skipped_dup,
            "skipped_no_return": skipped_no_return,
            "skipped_date_before_return": skipped_date_before_return,
            "prices": prices,
            "full_kizs": full_kizs,
            "total_unique": total_unique,
        }

    @classmethod
    def _log_skipped(cls, logger, skipped_dup, skipped_no_return,
                     skipped_date_before_return, total_unique,
                     added, seller) -> None:
        """Логирует пропущенные КИЗы и добавленные."""
        logger.report("  Пропущено КИЗов:")
        logger.report(
            f"    нет в одном экземпляре (дубликаты в отчёте): "
            f"{skipped_dup}"
        )
        logger.report(
            f"    уже проданы без возврата: {skipped_no_return}"
        )
        logger.report(
            f"    дата продажи раньше даты возврата: "
            f"{skipped_date_before_return}"
        )
        logger.report(
            f"    Итого уникальных КИЗов в отчёте: {total_unique}"
        )
        logger.report(
            f"  Добавлено {added} записей для продавца '{seller.name}'"
        )

    @classmethod
    def _build_result(cls, seller, result_dict,
                      skipped_by_type) -> MpReportData:
        """Собирает MpReportData из результатов валидации."""
        return MpReportData(
            seller=seller,
            added=result_dict["added"],
            prices=result_dict["prices"],
            full_kizs=result_dict["full_kizs"],
            skipped_dup=result_dict["skipped_dup"],
            skipped_no_return=result_dict["skipped_no_return"],
            skipped_date_before_return=result_dict["skipped_date_before_return"],
            total_unique=result_dict["total_unique"],
            skipped_by_type=skipped_by_type,
        )

    @classmethod
    def _log_stats(cls, logger, report_path, stats) -> None:
        """Финальный info-лог со статистикой KizUtils."""
        logger.info(
            f"{Path(report_path).name}: успешно {stats['processed']}, "
            f"отброшено коротких {stats['dropped_short']}, "
            f"без '01' {stats['dropped_no_01']}, "
            f"транслитерировано {stats['transliterated']}."
        )


class ChzMpReportReader:
    """Читатель файлов ЧЗ_МП.

    Роль:
        Обрабатывает один файл ЧЗ_МП: находит продавца по имени
        листа, читает столбец КИЗ, чистит и валидирует каждое
        значение. Возвращает список записей ChzMpEntry. Управляет
        статистикой KizUtils (start_stats / pop_stats).
    """

    @staticmethod
    def read(report_path, sellers, kiz_validator,
             logger: "LoggerV2") -> List[ChzMpEntry]:
        """Читает один файл ЧЗ_МП.

        Вход:
            report_path — путь к файлу (.xlsx).
            sellers — список Seller.
            kiz_validator — KizValidator для валидации КИЗов.
            logger — LoggerV2 для пошаговых и сводных сообщений.

        Выход:
            Список ChzMpEntry — по одной записи на каждый
            валидированный КИЗ. Пустой список, если файл не
            открылся или ничего не прошло очистку.

        Роль:
            Один файл — один вызов. Batch-контекст KizStorage
            вызывающий код открывает снаружи. Внутри читателя
            статистика KizUtils включается на входе и сбрасывается
            в finally — независимо от того, чем закончилось чтение.
        """
        entries: List[ChzMpEntry] = []
        logger.report(f"Обработка ЧЗ_МП: {Path(report_path).name}")

        wb = WorkbookOpener.open(
            report_path, logger=logger, description="ЧЗ_МП",
            read_only=True,
        )
        if wb is None:
            return entries

        KizUtils.start_stats()
        try:
            for sheet_name in wb.sheetnames:
                seller = ExcelHelper.find_seller_by_sheet_name(
                    wb, sellers, sheet_name
                )
                if seller is None:
                    logger.report(
                        f"  Лист '{sheet_name}' не соответствует ни одному "
                        f"продавцу – пропущен"
                    )
                    continue

                sheet = wb[sheet_name]
                raw_kiz_list = ExcelHelper.read_column_values(
                    sheet, col_index=1, start_row=1
                )
                for raw_kiz in raw_kiz_list:
                    full_cleaned_list = KizUtils.clean_kiz_full(
                        raw_kiz, logger=logger
                    )
                    if not full_cleaned_list:
                        logger.report(
                            f"    Некорректный КИЗ (очистка не дала "
                            f"результатов): {str(raw_kiz)[:50]}..."
                        )
                        continue

                    for full_kiz in full_cleaned_list:
                        storage_list = KizUtils.clean_kiz_for_storage(
                            full_kiz, logger=logger
                        )
                        if not storage_list:
                            continue
                        storage_kiz = storage_list[0]
                        result = kiz_validator.validate_for_sale(storage_kiz)
                        entries.append(ChzMpEntry(
                            seller_name=seller.name,
                            full_kiz=full_kiz,
                            storage_kiz=storage_kiz,
                            result=result,
                        ))
                logger.report(
                    f"  Лист '{sheet_name}' → продавец '{seller.name}': "
                    f"обработано {len(raw_kiz_list)} записей"
                )
        finally:
            try:
                wb.close()
            except Exception:
                pass
            stats = KizUtils.pop_stats()
            logger.info(
                f"ЧЗ_МП {Path(report_path).name}: "
                f"успешно {stats['processed']}, "
                f"отброшено коротких {stats['dropped_short']}, "
                f"без '01' {stats['dropped_no_01']}, "
                f"транслитерировано {stats['transliterated']}."
            )

        return entries


class WBReportReader(BaseMpReportReader):
    """Читатель WB-отчётов МП.

    Роль:
        Обрабатывает один файл WB-отчёта: читает лист «КИЗ» с
        фильтром по типу операции «ПРОДАЖА», группирует вхождения
        одного КИЗа через KizOccurrences, читает даты из листа
        «Сборочные задания», выбирает самое позднее вхождение
        и валидирует. Возвращает MpReportData.
    """

    _REQUIRED_SHEETS = ("КИЗ",)
    COLLECT_PRICES = True
    _DESCRIPTION = "отчёт МП"

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Читает лист «КИЗ», фильтр по типу операции «ПРОДАЖА»."""
        sheet = wb["КИЗ"]
        occurrences = KizOccurrences()
        skipped_by_type: dict = {}

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if len(row) < 9:
                continue
            task_num = row[0]
            raw_kiz = row[2]
            operation_type = row[8]
            price_raw = row[4] if len(row) > 4 else None

            if not (raw_kiz and task_num and operation_type and
                    str(operation_type).strip().upper() == "ПРОДАЖА"):
                op_key = (
                    str(operation_type).strip()
                    if operation_type else "(пусто)"
                )
                skipped_by_type[op_key] = (
                    skipped_by_type.get(op_key, 0) + 1
                )
                continue

            full_cleaned = KizUtils.clean_kiz_full(raw_kiz, logger=logger)
            if not full_cleaned:
                logger.report(
                    f"    Некорректный КИЗ (очистка не дала "
                    f"результатов): {str(raw_kiz)[:50]}..."
                )
                continue

            task_num_str = str(task_num).strip()

            price_value = None
            try:
                price_value = float(price_raw)
            except (TypeError, ValueError):
                pass
            if price_value is not None and price_value <= 0:
                price_value = None

            for full_kiz in full_cleaned:
                storage_list = KizUtils.clean_kiz_for_storage(
                    full_kiz, logger=logger
                )
                if not storage_list:
                    continue
                storage_kiz = storage_list[0]
                occurrences.add(
                    storage_kiz, full_kiz, task_num_str, price_value
                )

        if skipped_by_type:
            logger.report("  Пропущено строк по типу операции:")
            for op_type, count in sorted(
                skipped_by_type.items(), key=lambda x: x[0].lower()
            ):
                logger.report(f"    '{op_type}': {count}")
        else:
            logger.report(
                "  Все строки прошли фильтр по типу операции 'Продажа'"
            )

        return occurrences, skipped_by_type

    @classmethod
    def _load_dates(cls, wb) -> dict:
        """Читает task_to_date из листа «Сборочные задания»."""
        task_to_date: dict = {}
        if "Сборочные задания" in wb.sheetnames:
            sheet_tasks = wb["Сборочные задания"]
            for row in sheet_tasks.iter_rows(
                min_row=2, values_only=True
            ):
                if len(row) >= 4:
                    task_num = row[0]
                    date_created = row[3]
                    if task_num and date_created:
                        task_to_date[str(task_num).strip()] = (
                            str(date_created).strip()
                        )
        return task_to_date

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки — дата из task_to_date по task_num."""
        date_str = dates.get(entry[1])
        return DateParser.parse_any(date_str, DateParser.KIZ_FORMATS)


class OZONReportReader(BaseMpReportReader):
    """Читатель Ozon-отчётов «Продажи маркированных товаров».

    Роль:
        Читает лист «Отчет», фильтрует строки по Схема продажи == FBS
        и Тип чека == Продажа, группирует КИЗы по storage_kiz через
        KizOccurrences (ключ сортировки — готовый datetime из ячейки).
        Возвращает MpReportData. Цены не собираются.
    """

    _REQUIRED_SHEETS = ("Отчет",)
    COLLECT_PRICES = False
    _DESCRIPTION = "отчёт Ozon"

    HEADER_VARIANTS = {
        "sale_date":  ["Дата фискализации"],
        "check_type": ["Тип чека"],
        "scheme":     ["Схема продажи"],
        "kiz":        ["Код маркировки"],
    }

    FALLBACK_COLUMNS = {
        "sale_date": 0, "check_type": 2, "scheme": 6, "kiz": 8,
    }

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Читает лист «Отчет», фильтр FBS + ПРОДАЖА."""
        sheet = wb["Отчет"]
        header_row, columns = ExcelHelper.find_header_row_and_columns(
            sheet, cls.HEADER_VARIANTS,
        )
        if header_row is None or columns is None:
            logger.warning(
                "Не удалось найти заголовки Ozon-отчёта по именам, "
                "использую фиксированные индексы (0, 2, 6, 8)"
            )
            header_row = 1
            columns = dict(cls.FALLBACK_COLUMNS)

        col_sale_date = columns["sale_date"]
        col_check_type = columns["check_type"]
        col_scheme = columns["scheme"]
        col_kiz = columns["kiz"]

        occurrences = KizOccurrences()
        skipped_by_type: dict = {}

        for row in sheet.iter_rows(min_row=header_row + 1,
                                    values_only=True):
            scheme = (
                str(row[col_scheme]).strip()
                if len(row) > col_scheme and row[col_scheme] is not None
                else ""
            )
            check_type = (
                str(row[col_check_type]).strip()
                if len(row) > col_check_type
                   and row[col_check_type] is not None
                else ""
            )

            if scheme.upper() != "FBS":
                key = f"схема: {scheme or '(пусто)'}"
                skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                continue
            if check_type.upper() != "ПРОДАЖА":
                key = f"тип чека: {check_type or '(пусто)'}"
                skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                continue

            raw_kiz = row[col_kiz] if len(row) > col_kiz else None
            raw_date = (
                row[col_sale_date] if len(row) > col_sale_date else None
            )
            if not raw_kiz or not raw_date:
                continue

            storage_list = KizUtils.clean_kiz_for_storage(
                raw_kiz, logger=logger
            )
            full_list = KizUtils.clean_kiz_full(
                raw_kiz, logger=logger
            )
            if not storage_list or not full_list:
                continue
            storage_kiz = storage_list[0]
            full_kiz = full_list[0]

            dt = DateParser.parse_iso_datetime(str(raw_date).strip())
            if dt is None:
                logger.warning(
                    f"Не удалось распарсить дату '{raw_date}' "
                    f"для КИЗа {storage_kiz}. Использую сегодняшнюю."
                )
                dt = datetime.now()

            occurrences.add(storage_kiz, full_kiz, dt, None)

        if skipped_by_type:
            logger.report("  Пропущено строк по типу:")
            for key, count in sorted(
                skipped_by_type.items(), key=lambda x: x[0].lower()
            ):
                logger.report(f"    '{key}': {count}")

        return occurrences, skipped_by_type

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки — уже готовый datetime из entry[1]."""
        return entry[1]
