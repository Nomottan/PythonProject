"""
Читатели Excel-отчётов пайплайна возвратов.

Четыре класса-читателя:
    ReturnsSourceReportReader — фильтрует исходный файл возвратов.
    ReturnsKizReader          — выгружает КИЗы для возврата.
    ReturnsTransferReader     — готовит строки передач между продавцами.

Роль в программе:
    Читатели отвечают только за разбор Excel и возврат типизированных
    данных. Batch-контекст KizStorage, запись .txt, сборка итоговых
    файлов — ответственность вызывающих сервисов.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from utils.excel_helper import ExcelHelper, WorkbookOpener
from utils.kiz_utils import KizUtils
from utils.parsers import ReturnsRow
from utils.text_utils import TextUtils

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2


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
            source_path, logger=logger,
            description="исходный файл возвратов",
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
                    logger.report(
                        f"Строка {row_idx}: ключ бренда "
                        f"'{parsed.brand}' не найден – пропущена"
                    )
                    continue

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
