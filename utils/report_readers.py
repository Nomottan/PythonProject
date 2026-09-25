"""
Читатели Excel-отчётов для пайплайна ЧЗ МП.

Два класса-читателя:
    ChzMpReportReader — разбирает файлы ЧЗ_МП, валидирует КИЗы
                        и возвращает список ChzMpEntry.
    MpReportReader    — разбирает один отчёт МП, группирует
                        вхождения КИЗов, выбирает позднее,
                        валидирует и возвращает агрегат MpReportData.

Роль в программе:
    Используются ExportKizService (Порция 14) вместо встроенных
    блоков чтения Excel. Batch-контекст KizStorage — ответственность
    вызывающего кода, не читателя.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from utils.excel_helper import ExcelHelper
from utils.kiz_utils import KizUtils, KizOccurrences
from utils.text_utils import TextUtils
# KizValidator нужен в рантайме: MpReportReader вызывает
# KizValidator._parse_date для фолбэка на сегодня. ValidationResult —
# в аннотации ChzMpEntry (dataclass не вычисляет аннотации,
# поэтому достаточно строковой ссылки, но импорт делает код яснее).
from services.kiz_validator import KizValidator, ValidationResult

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

        wb = ExcelHelper.open_workbook_with_logger(
            report_path, logger, description="ЧЗ_МП",
            read_only=True, data_only=True,
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


class MpReportReader:
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
        logger.report(f"Обработка отчёта МП: {report_path.name}")

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

        wb = ExcelHelper.open_workbook_with_logger(
            report_path, logger, description="отчёт МП",
            read_only=True, data_only=True,
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
                if sale_date_str is None or KizValidator._parse_date(
                    sale_date_str
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