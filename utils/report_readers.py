"""
Читатели Excel-отчётов.

Пять классов-читателей, сгруппированных по домену:

    Пайплайн ЧЗ МП:
        ChzMpReportReader — разбирает файлы ЧЗ_МП.
        MpReportReader    — разбирает отчёты МП.

    Пайплайн возвратов:
        ReturnsSourceReportReader — фильтрует исходный файл возвратов.
        ReturnsKizReader          — выгружает КИЗы для возврата.
        ReturnsTransferReader     — готовит строки передач между продавцами.

Роль в программе:
    Читатели отвечают только за разбор Excel и возврат типизированных
    данных. Batch-контекст KizStorage, запись .txt, сборка итоговых
    файлов — ответственность вызывающих сервисов.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from utils.excel_helper import ExcelHelper, WorkbookOpener
from utils.kiz_utils import KizUtils, KizOccurrences
from utils.text_utils import TextUtils
from utils.parsers import ReturnsRow, DateParser
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
        Возвращается MpReportReader.read. Содержит и счётчики,
        и полезные данные (цены, полные КИЗы) для мержа в
        общесервисные структуры.

    Поля:
        seller — продавец, определённый по имени файла.
        added — сколько КИЗов прошло валидацию (result == ADDED).
        prices — dict {storage_kiz: int_price} для добавленных КИЗов.
        full_kizs — set полных КИЗов, добавленных в этом отчёте
                    (нужен вызывающему коду для записи в .txt).
        skipped_dup — сколько вхождений отброшено как дубликаты
                      внутри одного storage_kiz.
        skipped_no_return — КИЗы, проданные без возврата.
        skipped_date_before_return — КИЗы, у которых дата продажи
                                     раньше даты возврата.
        total_unique — всего уникальных storage_kiz в отчёте.
        skipped_by_type — dict {operation_type: count} — строки,
                          не прошедшие фильтр по типу операции.
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

class WBReportReader:
    """Читатель отчётов МП.

    Роль:
        Обрабатывает один файл «ОТЧЁТ МП ПО ...xlsx»: определяет
        продавца по имени файла, читает лист «КИЗ» с фильтром
        по типу операции «ПРОДАЖА», группирует вхождения одного
        КИЗа через KizOccurrences, читает даты из листа «Сборочные
        задания», выбирает самое позднее вхождение и валидирует.
        Возвращает MpReportData с агрегатами и полезными данными.
    """

    @staticmethod
    def read(report_path, sellers, kiz_validator,
             logger: "LoggerV2") -> Optional[MpReportData]:
        """Читает один отчёт МП.

        Вход:
            report_path — путь к файлу «ОТЧЁТ МП ПО ...xlsx».
            sellers — список Seller.
            kiz_validator — KizValidator.
            logger — LoggerV2.

        Выход:
            MpReportData — если продавец определён и лист «КИЗ»
            есть. None — если файл не открылся, продавец не
            определён или листа «КИЗ» нет.

        Роль:
            Один файл — один вызов. Batch-контекст KizStorage —
            снаружи. Статистика KizUtils включается и сбрасывается
            внутри (finally), агрегат логируется через logger.info.
        """
        report_path = Path(report_path)
        logger.report(f"Обработка WB-отчёта: {report_path.name}")

        # Продавца ищем по имени файла (без расширения, в нижнем регистре).
        seller = TextUtils.find_seller_by_file_name(
            report_path.stem.lower(), sellers
        )
        if seller is None:
            logger.report(
                "  Не удалось определить продавца из имени файла – пропущен"
            )
            return None
        logger.report(f"  Продавец определён: {seller.name}")

        wb = WorkbookOpener.open(
            report_path, logger=logger, description="отчёт МП",
            read_only=True,
        )
        if wb is None:
            return None

        KizUtils.start_stats()
        try:
            if "КИЗ" not in wb.sheetnames:
                logger.report("  Лист 'КИЗ' отсутствует – пропущен")
                return None

            sheet_kiz = wb["КИЗ"]
            occurrences = KizOccurrences()
            skipped_by_type: dict[str, int] = {}

            for row in sheet_kiz.iter_rows(min_row=2, values_only=True):
                if len(row) < 9:
                    continue
                task_num = row[0]
                raw_kiz = row[2]
                operation_type = row[8]
                price_raw = row[4] if len(row) > 4 else None

                # Фильтр по типу операции "ПРОДАЖА". Строки с другим
                # типом (или без типа) собираются в skipped_by_type.
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

                full_cleaned_list = KizUtils.clean_kiz_full(
                    raw_kiz, logger=logger
                )
                if not full_cleaned_list:
                    logger.report(
                        f"    Некорректный КИЗ (очистка не дала "
                        f"результатов): {str(raw_kiz)[:50]}..."
                    )
                    continue

                task_num_str = str(task_num).strip()

                # Цена: float; неположительные и нечисловые → None.
                price_value = None
                try:
                    price_value = float(price_raw)
                except (TypeError, ValueError):
                    pass
                if price_value is not None and price_value <= 0:
                    price_value = None

                for full_kiz in full_cleaned_list:
                    storage_list = KizUtils.clean_kiz_for_storage(
                        full_kiz, logger=logger
                    )
                    if not storage_list:
                        continue
                    storage_kiz = storage_list[0]
                    occurrences.add(
                        storage_kiz, full_kiz, task_num_str, price_value
                    )

            # Диагностика по типам операций.
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

            # Даты продаж — из листа «Сборочные задания».
            task_to_date: dict[str, str] = {}
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
            else:
                logger.report(
                    "  Лист 'Сборочные задания' отсутствует – даты "
                    "не загружены, используем сегодняшнюю"
                )

            # Итоги.
            added = 0
            skipped_dup = 0
            skipped_no_return = 0
            skipped_date_before_return = 0
            prices: dict[str, int] = {}
            full_kizs: set[str] = set()

            for storage_kiz, _entries in occurrences.items():
                chosen = occurrences.pick_latest(storage_kiz, task_to_date)
                if chosen is None:
                    continue
                skipped_dup += chosen.skipped_dup_count

                sale_date_str = chosen.sale_date_str
                # Если дата отсутствует или не парсится — фолбэк на сегодня.
                if sale_date_str is None or DateParser.parse_any(
                        sale_date_str, DateParser.KIZ_FORMATS,
                ) is None:
                    sale_date_str = datetime.now().strftime("%d-%m-%Y")

                result = kiz_validator.validate_for_sale(
                    storage_kiz, sale_date_str
                )

                if result == ValidationResult.ADDED:
                    full_kizs.add(chosen.full_kiz)
                    added += 1
                    if chosen.price is not None:
                        prices[storage_kiz] = int(chosen.price)
                elif result == ValidationResult.SKIPPED_NO_RETURN:
                    skipped_no_return += 1
                elif result == ValidationResult.SKIPPED_DATE_BEFORE_RETURN:
                    skipped_date_before_return += 1

            total_unique = (
                added + skipped_no_return
                + skipped_date_before_return + skipped_dup
            )

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

            return MpReportData(
                seller=seller,
                added=added,
                prices=prices,
                full_kizs=full_kizs,
                skipped_dup=skipped_dup,
                skipped_no_return=skipped_no_return,
                skipped_date_before_return=skipped_date_before_return,
                total_unique=total_unique,
                skipped_by_type=skipped_by_type,
            )
        finally:
            try:
                wb.close()
            except Exception:
                pass
            stats = KizUtils.pop_stats()
            logger.info(
                f"МП {report_path.name}: успешно {stats['processed']}, "
                f"отброшено коротких {stats['dropped_short']}, "
                f"без '01' {stats['dropped_no_01']}, "
                f"транслитерировано {stats['transliterated']}."
            )

class OZONReportReader:
    """Читатель Ozon-отчётов «Продажи маркированных товаров».

    Роль:
        Читает лист «Отчет» (fallback — wb.active), фильтрует
        строки по Схема продажи == FBS и Тип чека == Продажа,
        группирует КИЗы по storage_kiz (дедуп через простой
        dict; KizOccurrences не используется — там другая
        логика выбора по task_num). Возвращает MpReportData.
    """

    # Заголовки столбцов Ozon-отчёта.
    HEADER_VARIANTS = {
        "sale_date":  ["Дата фискализации"],
        "check_type": ["Тип чека"],
        "scheme":     ["Схема продажи"],
        "kiz":        ["Код маркировки"],
    }

    # Fallback-индексы, если заголовки не нашлись.
    # По образцу: 0=Дата фискализации, 2=Тип чека, 6=Схема продажи,
    # 8=Код маркировки.
    FALLBACK_COLUMNS = {
        "sale_date": 0, "check_type": 2, "scheme": 6, "kiz": 8,
    }

    @staticmethod
    def read(report_path, sellers, kiz_validator,
             logger: "LoggerV2") -> Optional[MpReportData]:
        """Читает один Ozon-отчёт.

        Вход:
            report_path — путь к файлу Ozon.
            sellers — список Seller.
            kiz_validator — KizValidator.
            logger — LoggerV2.

        Выход:
            MpReportData или None, если файл не открылся, продавец
            не определён или лист «Отчет» отсутствует.
        """
        report_path = Path(report_path)
        logger.report(f"Обработка отчёта Ozon: {report_path.name}")

        seller = TextUtils.find_seller_by_file_name(
            report_path.stem.lower(), sellers
        )
        if seller is None:
            logger.report(
                "  Не удалось определить продавца – пропущен"
            )
            return None

        wb = WorkbookOpener.open(
            report_path, logger=logger, description="отчёт Ozon",
            read_only=True,
        )
        if wb is None:
            return None

        KizUtils.start_stats()
        try:
            if "Отчет" in wb.sheetnames:
                sheet = wb["Отчет"]
            else:
                logger.report(
                    "Лист 'Отчет' не найден – пропущен"
                )
                return None

            header_row, columns = ExcelHelper.find_header_row_and_columns(
                sheet, OZONReportReader.HEADER_VARIANTS,
            )
            if header_row is None or columns is None:
                logger.warning(
                    "Не удалось найти заголовки Ozon-отчёта по именам, "
                    "использую фиксированные индексы (0, 2, 6, 8)"
                )
                header_row = 1
                columns = dict(OZONReportReader.FALLBACK_COLUMNS)

            col_sale_date = columns["sale_date"]
            col_check_type = columns["check_type"]
            col_scheme = columns["scheme"]
            col_kiz = columns["kiz"]

            # Дедуп: dict[storage_kiz] -> list[(full_kiz, datetime)].
            occurrences: dict = {}
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

                # Фильтр по схеме — независимая причина.
                if scheme.upper() != "FBS":
                    key = f"схема: {scheme or '(пусто)'}"
                    skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                    continue
                # Фильтр по типу чека — независимая причина.
                if check_type.upper() != "ПРОДАЖА":
                    key = f"тип чека: {check_type or '(пусто)'}"
                    skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                    continue

                raw_kiz = row[col_kiz] if len(row) > col_kiz else None
                raw_date = (row[col_sale_date]
                            if len(row) > col_sale_date else None)
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

                occurrences.setdefault(storage_kiz, []).append(
                    (full_kiz, dt)
                )

            # Дедуп: выбираем самое позднее вхождение. max берёт
            # первый при равенстве — соответствует «при равенстве
            # — первое».
            picked: list = []
            for storage_kiz, entries in occurrences.items():
                best = max(entries, key=lambda e: e[1])
                picked.append((storage_kiz, best[0], best[1]))
            skipped_dup = sum(
                len(v) - 1 for v in occurrences.values()
            )

            # Диагностика по типам.
            if skipped_by_type:
                logger.report("  Пропущено строк по типу:")
                for key, count in sorted(
                    skipped_by_type.items(), key=lambda x: x[0].lower()
                ):
                    logger.report(f"    '{key}': {count}")

            # Валидация.
            added = 0
            skipped_no_return = 0
            skipped_date_before_return = 0
            full_kizs: set = set()

            for storage_kiz, full_kiz, dt in picked:
                sale_date_str = dt.strftime("%H:%M:%S %d.%m.%Y")
                result = kiz_validator.validate_for_sale(
                    storage_kiz, sale_date_str
                )
                if result == ValidationResult.ADDED:
                    added += 1
                    full_kizs.add(full_kiz)
                elif result == ValidationResult.SKIPPED_NO_RETURN:
                    skipped_no_return += 1
                elif result == ValidationResult.SKIPPED_DATE_BEFORE_RETURN:
                    skipped_date_before_return += 1

            total_unique = (
                added + skipped_no_return
                + skipped_date_before_return + skipped_dup
            )

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
                f"  Добавлено {added} записей для продавца "
                f"'{seller.name}'"
            )

            return MpReportData(
                seller=seller,
                added=added,
                prices={},
                full_kizs=full_kizs,
                skipped_dup=skipped_dup,
                skipped_no_return=skipped_no_return,
                skipped_date_before_return=skipped_date_before_return,
                total_unique=total_unique,
                skipped_by_type=skipped_by_type,
            )
        finally:
            try:
                wb.close()
            except Exception:
                pass
            stats = KizUtils.pop_stats()
            logger.info(
                f"Ozon {report_path.name}: успешно "
                f"{stats['processed']}, отброшено коротких "
                f"{stats['dropped_short']}, без '01' "
                f"{stats['dropped_no_01']}, транслитерировано "
                f"{stats['transliterated']}."
            )

@dataclass
class ReturnsFilterStats:
    """Статистика фильтрации исходного файла возвратов.

    Роль:
        Возвращается ReturnsSourceReportReader.read. Содержит
        счётчики и агрегаты по компаниям. Используется
        ReturnsPreparationService для логирования.

    Поля:
        copied — сколько строк прошло фильтр.
        skipped — сколько строк отброшено (не прошли по компании).
        unknown_companies — dict {компания: количество строк} для
                            компаний, которых нет в списке продавцов.
        status_counts — dict {статус: количество} по строкам, прошедшим
                        фильтр.
        passed_companies — set уникальных компаний, прошедших фильтр.
    """
    copied: int
    skipped: int
    unknown_companies: dict
    status_counts: dict
    passed_companies: set

@dataclass
class ReturnsSourceData:
    """Результат разбора исходного файла возвратов.

    Роль:
        Возвращается ReturnsSourceReportReader.read. Содержит
        заголовки и отфильтрованные строки для записи в новый
        файл, а также статистику фильтрации. Запись нового файла —
        ответственность сервиса.

    Поля:
        headers — заголовки шести оставленных столбцов.
        rows — список кортежей со значениями шести столбцов.
        stats — ReturnsFilterStats.
    """
    headers: list
    rows: list
    stats: ReturnsFilterStats

class ReturnsSourceReportReader:
    """Читатель исходного файла возвратов.

    Роль:
        Открывает исходный файл возвратов, читает заголовки
        шести столбцов (B, D, F, G, H, L) и строки, фильтрует
        по allowed_companies. Возвращает ReturnsSourceData с
        заголовками, отфильтрованными строками и статистикой.
        Запись нового файла и копирование исходника — за
        вызывающим сервисом.

    Атрибуты класса:
        COLUMNS_TO_KEEP — буквы исходных столбцов, которые
                          переносятся в новый файл.
        COL_INDICES — те же столбцы в 1-based индексах (для
                      доступа к row по values_only=True).
        STATUS_COL_IDX — 1-based индекс столбца статуса в исходной
                         строке. Столбец D.
    """

    COLUMNS_TO_KEEP = ('B', 'D', 'F', 'G', 'H', 'L')
    COL_INDICES = (2, 4, 6, 7, 8, 12)
    STATUS_COL_IDX = 4

    @staticmethod
    def read(source_path, allowed_companies,
             logger: "LoggerV2") -> ReturnsSourceData:
        """Читает исходный файл возвратов.

        Вход:
            source_path — путь к исходному файлу (.xlsx).
            allowed_companies — set нормализованных названий компаний.
                                Пустой set — пропускать всех.
            logger — LoggerV2.

        Выход:
            ReturnsSourceData. Если файл не открылся — пустые
            headers, rows и stats с нулями.

        Роль:
            Один файл — один вызов. Заголовки читаются через
            sheet[f"{letter}1"].value (может не сработать на
            некоторых файлах — тогда пустой список). Строки —
            через iter_rows(values_only=True).
        """
        wb = WorkbookOpener.open(
            source_path, logger=logger, description="исходный файл возвратов",
            read_only=True,
        )
        if wb is None:
            return ReturnsSourceData(
                headers=[], rows=[],
                stats=ReturnsFilterStats(
                    copied=0, skipped=0,
                    unknown_companies={}, status_counts={},
                    passed_companies=set(),
                ),
            )

        try:
            sheet = wb.active

            # Заголовки шести столбцов — как в старом коде, через
            # букву столбца. В редких случаях может упасть —
            # тогда работаем с пустым списком.
            headers: list = []
            try:
                for col_letter in ReturnsSourceReportReader.COLUMNS_TO_KEEP:
                    headers.append(sheet[f"{col_letter}1"].value)
            except Exception as e:
                logger.warning(f"Ошибка при чтении заголовков: {e}")
                headers = []

            rows: list = []
            unknown_companies: dict = {}
            status_counts: dict = {}
            passed_companies: set = set()
            copied = 0
            skipped = 0

            for row in sheet.iter_rows(min_row=2, values_only=True):
                cell_L_val = row[11] if len(row) > 11 else None
                cell_L_str = (
                    str(cell_L_val).strip()
                    if cell_L_val is not None else ""
                )

                # Фильтр по компании.
                if allowed_companies:
                    check_val = TextUtils.normalize(cell_L_str)
                    if check_val not in allowed_companies:
                        if cell_L_str:
                            unknown_companies[cell_L_str] = (
                                unknown_companies.get(cell_L_str, 0) + 1
                            )
                        skipped += 1
                        continue

                if cell_L_str:
                    passed_companies.add(cell_L_str)

                # Статус — из исходного столбца D.
                status_val = (
                    row[ReturnsSourceReportReader.STATUS_COL_IDX - 1]
                    if len(row) >= ReturnsSourceReportReader.STATUS_COL_IDX
                    else None
                )
                status_str = (
                    str(status_val).strip()
                    if status_val is not None else ""
                )
                status_key = status_str or "(пусто)"
                status_counts[status_key] = (
                    status_counts.get(status_key, 0) + 1
                )

                # Собираем строку для нового файла.
                new_row = []
                for col_idx in ReturnsSourceReportReader.COL_INDICES:
                    value = row[col_idx - 1] if len(row) >= col_idx else None
                    new_row.append(value)
                rows.append(tuple(new_row))
                copied += 1

            return ReturnsSourceData(
                headers=headers,
                rows=rows,
                stats=ReturnsFilterStats(
                    copied=copied,
                    skipped=skipped,
                    unknown_companies=unknown_companies,
                    status_counts=status_counts,
                    passed_companies=passed_companies,
                ),
            )
        finally:
            try:
                wb.close()
            except Exception:
                pass

@dataclass
class ReturnsKizData:
    """Результат выгрузки КИЗов для возврата.

    Роль:
        Возвращается ReturnsKizReader.read. Содержит данные для
        записи .txt-файлов и агрегаты для логирования.

    Поля:
        full_kizs_by_company — dict {safe_company: [full_kiz, ...]}.
                               Группировка по компаниям после
                               TextUtils.sanitize_filename. Один
                               файл на компанию — пишет сервис.
        returns_updated_in_base — сколько КИЗов обновили дату
                                  возврата (были в базе).
        returns_not_in_base — сколько КИЗов отсутствовали в базе.
        kiz_stats — dict со статистикой KizUtils: processed,
                    dropped_short, dropped_no_01, transliterated.
    """
    full_kizs_by_company: dict
    returns_updated_in_base: int
    returns_not_in_base: int
    kiz_stats: dict

class ReturnsKizReader:
    """Читатель файла «Возвраты_{date}.xlsx» для выгрузки КИЗов.

    Роль:
        Открывает рабочий файл возвратов, фильтрует строки по
        статусу «ВЫБЫЛ», чистит и валидирует КИЗы, группирует
        полные КИЗы по компаниям. Batch-контекст KizStorage
        открывается внутри — цикл валидации идёт одним флашем.
        KizUtils.start_stats / pop_stats управляются здесь:
        это единственный reader, где очистка КИЗов реально
        выполняется.
    """

    @staticmethod
    def read(file_path, kiz_validator,
             logger: "LoggerV2") -> ReturnsKizData:
        """Читает рабочий файл возвратов.

        Вход:
            file_path — путь к «Возвраты_{date}.xlsx».
            kiz_validator — KizValidator с методами batch,
                            validate_for_return и storage.get.
            logger — LoggerV2.

        Выход:
            ReturnsKizData. При ошибке открытия — пустые данные
            и нулевые счётчики.

        Роль:
            Один файл — один вызов. Все изменения used_kiz.json
            накапливаются внутри with kiz_validator.batch() и
            сохраняются на выходе. Ошибки отдельных строк
            логируются через logger.warning и не прерывают
            обход.
        """
        wb = WorkbookOpener.open(
            file_path, logger=logger, description="файл возвратов",
            read_only=True,
        )
        if wb is None:
            return ReturnsKizData(
                full_kizs_by_company={},
                returns_updated_in_base=0,
                returns_not_in_base=0,
                kiz_stats={},
            )

        KizUtils.start_stats()
        full_kizs_by_company: dict = {}
        returns_updated_in_base = 0
        returns_not_in_base = 0

        try:
            sheet = wb.active
            with kiz_validator.batch():
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    try:
                        if len(row) < 6:
                            continue
                        raw_kiz = row[0]
                        status = row[1]
                        company = row[5]

                        # Фильтр по статусу: только «ВЫБЫЛ».
                        if (status is None
                                or str(status).strip().upper() != "ВЫБЫЛ"):
                            continue
                        if raw_kiz is None or company is None:
                            continue

                        full_cleaned_list = KizUtils.clean_kiz_full(
                            raw_kiz, logger=logger
                        )
                        if not full_cleaned_list:
                            logger.report(
                                f"Некорректный КИЗ (очистка не дала "
                                f"результатов): {str(raw_kiz)[:50]}..."
                            )
                            continue

                        company_str = str(company).strip()
                        safe_company = TextUtils.sanitize_filename(
                            company_str
                        )

                        for full_kiz in full_cleaned_list:
                            storage_list = KizUtils.clean_kiz_for_storage(
                                full_kiz, logger=logger
                            )
                            if not storage_list:
                                continue
                            storage_kiz = storage_list[0]
                            # Долг: прямой доступ к storage.get.
                            existing_before = kiz_validator.storage.get(
                                storage_kiz
                            )

                            if kiz_validator.validate_for_return(
                                storage_kiz
                            ):
                                if existing_before is None:
                                    returns_not_in_base += 1
                                else:
                                    returns_updated_in_base += 1
                                full_kizs_by_company.setdefault(
                                    safe_company, []
                                ).append(full_kiz)
                    except Exception as e:
                        logger.warning(f"Ошибка обработки КИЗа: {e}")
                        continue
        finally:
            # Сброс сессии статистики — даже если было исключение.
            kiz_stats = KizUtils.pop_stats()
            try:
                wb.close()
            except Exception:
                pass

        return ReturnsKizData(
            full_kizs_by_company=full_kizs_by_company,
            returns_updated_in_base=returns_updated_in_base,
            returns_not_in_base=returns_not_in_base,
            kiz_stats=kiz_stats,
        )

@dataclass
class ReturnsTransferRow:
    """Одна строка передачи КИЗа между продавцами.

    Роль:
        Готовая к передаче в SalesFileGenerator.add_sale_row
        запись. Заменяет чтение row[0..5] вручную и все проверки
        на стороне сервиса — отбор делает ReturnsTransferReader.

    Поля:
        from_seller_name — имя продавца-отправителя (владелец КИЗа).
        to_seller_name — имя продавца-получателя (куда передаётся
                         бренд).
        to_seller_inn — ИНН получателя.
        product_name — наименование продукта.
        raw_kiz — полный КИЗ для очистки в SalesFileGenerator.
        brand — бренд товара.
        owner_company_str — исходная строка владельца из файла
                            (передаётся в add_sale_row для
                            совместимости контракта).
    """
    from_seller_name: str
    to_seller_name: str
    to_seller_inn: str
    product_name: str
    raw_kiz: str
    brand: str
    owner_company_str: str

@dataclass
class ReturnsTransferData:
    """Результат разбора файла возвратов для передач.

    Роль:
        Возвращается ReturnsTransferReader.read. Содержит готовые
        строки передач и агрегаты для логирования.

    Поля:
        rows — список ReturnsTransferRow, прошедших все проверки.
        total_rows — сколько строк обработано (после фильтра по
                     длине; до остальных проверок).
        unique_brands — set уникальных непустых брендов,
                        встреченных в файле.
    """
    rows: list
    total_rows: int
    unique_brands: set

class ReturnsTransferReader:
    """Читатель файла возвратов для подготовки передач.

    Роль:
        Открывает «Возвраты_{date}.xlsx», строит маппинги
        «компания → продавец» и «ключ бренда → продавец»,
        проходит по строкам через ReturnsRow и собирает
        ReturnsTransferRow для строк, где:
            - бренд известен (есть в key_to_seller);
            - владелец известен (есть в company_to_seller);
            - владелец не совпадает с продавцом бренда;
            - у продавца-владельца ещё нет этого бренда.
        Проверки на стороне сервиса не дублируются.
    """

    @staticmethod
    def read(file_path, sellers,
             logger: "LoggerV2") -> ReturnsTransferData:
        """Читает файл возвратов и собирает строки передач.

        Вход:
            file_path — путь к «Возвраты_{date}.xlsx».
            sellers — список Seller.
            logger — LoggerV2.

        Выход:
            ReturnsTransferData. При ошибке открытия — пустые
            rows, total_rows=0, пустой unique_brands.

        Роль:
            Один файл — один вызов. Маппинги строятся через
            TextUtils.build_key_mapping с logger=logger, чтобы
            дубликаты ключей шли в warnings.txt.
        """
        wb = WorkbookOpener.open(
            file_path, logger=logger, description="файл возвратов",
            read_only=True,
        )
        if wb is None:
            return ReturnsTransferData(
                rows=[], total_rows=0, unique_brands=set(),
            )

        # Маппинги: нормализованная компания → Seller,
        # нормализованный ключ бренда → Seller.
        company_to_seller = TextUtils.build_key_mapping(
            sellers,
            key_extractor=lambda s: s.company,
            logger=logger,
        )
        key_to_seller = TextUtils.build_key_mapping(
            sellers,
            key_extractor=lambda s: s.get_brand_keys(),
            logger=logger,
        )

        rows_out: list = []
        total_rows = 0
        unique_brands: set = set()

        try:
            sheet = wb.active
            for row_idx, raw in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                if len(raw) < 6:
                    continue
                total_rows += 1

                parsed = ReturnsRow.from_row(raw)
                if parsed is None:
                    logger.report(
                        f"Строка {row_idx}: некорректные данные "
                        f"(пустой КИЗ) – пропущена"
                    )
                    continue

                # Собираем уникальные бренды — до проверок, как в
                # исходном сервисе (там бренд учитывался, даже
                # если строка потом отбрасывалась).
                if parsed.brand:
                    unique_brands.add(parsed.brand)

                if not parsed.owner_company or not parsed.brand:
                    continue

                brand_key = TextUtils.normalize(parsed.brand)
                seller_brand = key_to_seller.get(brand_key)
                if seller_brand is None:
                    # По Q3: report, не warning.
                    logger.report(
                        f"Строка {row_idx}: ключ бренда "
                        f"'{parsed.brand}' не найден – пропущена"
                    )
                    continue

                # По Q2: используем company_to_seller.get напрямую.
                norm_owner = TextUtils.normalize(parsed.owner_company)
                owner_seller = company_to_seller.get(norm_owner)
                if owner_seller is None:
                    logger.report(
                        f"Строка {row_idx}: владелец "
                        f"'{parsed.owner_company}' не найден – пропущена"
                    )
                    continue

                if owner_seller == seller_brand:
                    continue

                has_brand = any(
                    TextUtils.normalize(key) == brand_key
                    for brand_obj in owner_seller.brands
                    for key in brand_obj.keys
                )
                if has_brand:
                    logger.report(
                        f"Строка {row_idx}: бренд '{parsed.brand}' "
                        f"уже есть у {owner_seller.name} – пропущена"
                    )
                    continue

                rows_out.append(ReturnsTransferRow(
                    from_seller_name=owner_seller.name,
                    to_seller_name=seller_brand.name,
                    to_seller_inn=seller_brand.inn,
                    product_name=parsed.product_name,
                    raw_kiz=parsed.kiz,
                    brand=parsed.brand,
                    owner_company_str=parsed.owner_company,
                ))
        finally:
            try:
                wb.close()
            except Exception:
                pass

        return ReturnsTransferData(
            rows=rows_out,
            total_rows=total_rows,
            unique_brands=unique_brands,
        )