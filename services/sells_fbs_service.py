"""
Сервисы ЧЗ МП: подготовка файлов, выгрузка КИЗов, фильтрация,
формирование продаж, финализация цен.

Содержит пять сервисов пайплайна:
    PreparationService     — копирование входных файлов в рабочую папку.
    ExportKizService       — выгрузка КИЗов из ЧЗ_МП и отчётов МП.
    FilterPreFinalService  — фильтрация предитоговых файлов.
    GenerateSalesService   — формирование файлов продаж между продавцами.
    FinalizePricesService  — установка цен и финализация ИТОГ-файлов.

Роль в программе:
    Вызываются из ChzMPWindow по кнопкам пайплайна. Каждый сервис
    работает через TaskContext — единую точку рабочей папки и
    логирования. Сервисы независимы: порядок задаёт UI.
"""

from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import (
    ExcelHelper, WorkbookOpener, WorkbookWriter,
)
from utils.txt_helper import TextFileWriter
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper, FilenameUtils
from utils.parsers import PreFinalRow
from utils.price_utils import AveragePriceResolver, PriceFiller
from utils.mp_readers import (
    ChzMpReportReader, WBReportReader, OZONReportReader,
    MpReportTypeDetector,
)
from utils.sales_file_generator import SalesFileGenerator, SalesFileRowsReader
from utils.fbs_buferprices import FbsBufferPrices
from services.kiz_validator import ValidationResult
from utils.kiz_utils import KizUtils, KizDuplicatesFinder

class PreparationService:
    """Сервис подготовки: копирование входных файлов в рабочую папку.

    Роль:
        Создаёт структуру рабочей папки задачи и складывает туда
        исходные файлы — ЧЗ МП и отчёты МП. Оригиналы в источнике
        не трогаются. Заодно чистит устаревшие записи КИЗов
        (старше 1 месяца) через KizValidator.

    Публичный API:
        prepare(target_dir, fbs_files, mp_files, sellers, log_callback).
    """

    def __init__(self, kiz_validator, log_manager_v2) -> None:
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2

    def prepare(self, target_dir, fbs_files=None, mp_files=None,
                sellers=None):
        """Запускает подготовку."""
        if sellers is None:
            sellers = []

        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_подготовка.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )

        # логгер V2 с именем файла, совпадающим с историческим.
        logger = self._log_manager_v2.create_logger_v2(
            source="PreparationService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_подготовка.txt",
        )

        logger.report(
            f"=== Подготовка от {ctx.today.strftime('%d.%m.%Y %H:%M')} ==="
        )
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        self._copy_fbs_files(ctx, logger, fbs_files or [])
        self._copy_mp_files(ctx, logger, mp_files or [], sellers)

        logger.report("Подготовка завершена.")

        # Очистка устаревших записей КИЗов
        self.kiz_validator.set_log_path(ctx.logs_dir)
        self.kiz_validator.load()
        deleted = self.kiz_validator.clean_old_entries(months=1)
        logger.info(f"Очистка старых записей: удалено {deleted}.")

    # ---------- Приватные методы ----------

    def _copy_fbs_files(self, ctx: TaskContext, logger, fbs_files) -> None:
        """Копирует файлы ЧЗ МП в подпапку Отчёты/."""
        if not fbs_files:
            return
        for i, src in enumerate(fbs_files):
            src_path = Path(src)
            if i == 0:
                new_name = FilenameUtils.format_with_extension(
                    "ЧЗ_МП_{date}", ctx.date_str
                )
            else:
                new_name = FilenameUtils.format_with_extension(
                    "ЧЗ_МП_{date}", ctx.date_str, index=i + 1
                )
            dst = ctx.reports_dir / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, logger,
                description="ЧЗ МП",
                overwrite=False,
            )

    def _copy_mp_files(self, ctx: TaskContext, logger, mp_files,
                       sellers) -> None:
        """Копирует отчёты МП в подпапку Отчёты/.

        REPLACE: определяем тип отчёта (WB / Ozon) по первому
        листу и формируем имя по шаблону Отчёт_WB_... или
        Отчёт_OZON_.... Старый шаблон ОТЧЁТ МП ПО ... не
        поддерживается. Неопознанные и неоткрывающиеся файлы
        копируются как «Неопознанный отчёт {stem} {date}.xlsx».
        """
        if not mp_files:
            return
        seller_counters: dict = {}
        for src in mp_files:
            src_path = Path(src)

            wb = WorkbookOpener.open(src_path, logger=None, read_only=True)
            if wb is None:
                logger.warning(f"Не удалось открыть {src_path.name}")
                dst = ctx.reports_dir / FilenameUtils.format_with_extension(
                    f"Неопознанный отчёт {src_path.stem} {{date}}",
                    ctx.date_str,
                )
                FileHelper.copy_file_with_log(
                    src_path, dst, logger,
                    description="неопознанный отчёт", overwrite=False,
                )
                continue

            # Битый dimension — не копируем вообще.
            if ExcelHelper._is_dimension_broken(wb):
                wb.close()
                logger.critical(
                    f"Файл {src_path.name} имеет битый dimension – "
                    f"пропущен",
                    can_influence=False,
                )
                continue

            report_type = MpReportTypeDetector.detect(wb)
            try:
                wb.close()
            except Exception:
                pass

            # Тип не распознан — копируем как неопознанный.
            if report_type is None:
                logger.warning(
                    f"Не удалось определить тип отчёта: {src_path.name}"
                )
                dst = ctx.reports_dir / FilenameUtils.format_with_extension(
                    f"Неопознанный отчёт {src_path.stem} {{date}}",
                    ctx.date_str,
                )
                FileHelper.copy_file_with_log(
                    src_path, dst, logger,
                    description="неопознанный отчёт", overwrite=False,
                )
                continue

            # Логируем тип.
            type_label = "WB" if report_type == "wb" else "Ozon"
            logger.report(
                f"Определён тип отчёта: {type_label} ({src_path.name})"
            )

            # Продавца ищем по имени файла.
            fname_lower = src_path.stem.lower()
            found_seller = TextUtils.find_seller_by_file_name(
                fname_lower, sellers
            )

            # Ключ счётчика — (seller или stem, тип).
            if found_seller:
                seller_key = found_seller.name
            else:
                seller_key = src_path.stem
            counter_key = (seller_key, report_type)

            idx = seller_counters.get(counter_key, 0) + 1
            seller_counters[counter_key] = idx

            if report_type == "wb":
                template = f"Отчёт_WB_{seller_key} {{date}}"
            else:
                template = f"Отчёт_OZON_{seller_key} {{date}}"

            if idx == 1:
                new_name = FilenameUtils.format_with_extension(
                    template, ctx.date_str,
                )
            else:
                new_name = FilenameUtils.format_with_extension(
                    template, ctx.date_str, index=idx,
                )

            dst = ctx.reports_dir / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, logger,
                description="отчёт", overwrite=False,
            )

class ExportKizService:
    """Сервис выгрузки КИЗов из ЧЗ_МП и отчётов МП в текстовые файлы.

    Роль:
        Оркестратор чтения. Логика разбора Excel живёт в
        ChzMpReportReader/WBReportReader/OZONReportReader
        (utils/report_readers.py). Сервис отвечает только за:
            - выбор файлов в подпапке Отчёты/;
            - вызов ридеров и мерж результатов в kiz_by_seller
              и prices_by_seller;
            - сохранение .txt со списками КИЗов;
            - сохранение prices_from_mp.json через FbsBufferPrices;
            - обрамление обоих чтений одним batch-контекстом
              KizStorage.

    Публичный API:
        export(target_dir, sellers).
    """

    def __init__(self, kiz_validator, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator для валидации КИЗов.
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.

        Роль: сохраняет ссылки. Логгер создаётся в начале export.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2

    def export(self, target_dir, sellers) -> None:
        """Запускает выгрузку КИЗов.

        Вход:
            target_dir — корневая папка задачи.
            sellers — список Seller.

        Выход: нет.

        Роль:
            Создаёт TaskContext и LoggerV2. Внутри одного batch-
            контекста KizStorage проходится по файлам ЧЗ_МП и
            отчётам МП. По завершении (вне батча) сохраняются
            prices_from_mp.json и .txt-файлы со списками КИЗов
            по продавцам.
        """
        # TaskContext — только пути.
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_выгрузка_кизов.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )

        # Логгер V2 с историческим именем файла.
        logger = self._log_manager_v2.create_logger_v2(
            source="ExportKizService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_выгрузка_кизов.txt",
        )

        logger.report(
            "=== ВЫГРУЗКА КИЗОВ В ТЕКСТОВЫЕ ФАЙЛЫ "
            "(с валидацией и очисткой) ==="
        )
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        self.kiz_validator.set_log_path(ctx.logs_dir)
        self.kiz_validator.load()

        kiz_by_seller: dict[str, set] = {seller.name: set() for seller in sellers}
        prices_by_seller: dict[str, dict] = {seller.name: {} for seller in sellers}

        # Единый батч на оба цикла чтения.
        with self.kiz_validator.batch():
            # ------------------------------------------------------------
            # 1. Обработка ЧЗ_МП — через ChzMpReportReader.
            # ------------------------------------------------------------
            chz_files = FileHelper.find_files_by_pattern(
                ctx.reports_dir, "ЧЗ_МП*.xlsx"
            )
            for chz_path in chz_files:
                try:
                    entries = ChzMpReportReader.read(
                        report_path=chz_path,
                        sellers=sellers,
                        kiz_validator=self.kiz_validator,
                        logger=logger,
                    )
                    # Ридер возвращает и ADDED, и SKIPPED. Фильтруем
                    # по result — только добавленные КИЗы идут в .txt.
                    for entry in entries:
                        if entry.result == ValidationResult.ADDED:
                            kiz_by_seller[entry.seller_name].add(entry.full_kiz)
                except Exception as e:
                    # NEW: ошибка одного файла — в critical, обработка
                    # остальных продолжается. Накопленные в батче
                    # изменения сохранятся на выходе из with.
                    logger.critical(
                        f"Ошибка обработки файла {Path(chz_path).name}: {e}",
                        can_influence=False,
                    )
                    continue

            # ------------------------------------------------------------
            # 2. Обработка отчётов МП — через WBReportReader.
            # ------------------------------------------------------------
            mp_files = FileHelper.find_files_by_pattern(
                ctx.reports_dir, "Отчёт_WB_*.xlsx"
            )
            for mp_path in mp_files:
                try:
                    data = WBReportReader.read(
                        report_path=mp_path,
                        sellers=sellers,
                        kiz_validator=self.kiz_validator,
                        logger=logger,
                    )
                    if data is None:
                        continue
                    # Мерж результатов отчёта в общесервисные структуры.
                    kiz_by_seller[data.seller.name].update(data.full_kizs)
                    prices_by_seller[data.seller.name].update(data.prices)
                except Exception as e:
                    logger.critical(
                        f"Ошибка обработки файла {Path(mp_path).name}: {e}",
                        can_influence=False,
                    )
                    continue
            # --- 3. Обработка Ozon-отчётов ---
            ozon_files = FileHelper.find_files_by_pattern(
                ctx.reports_dir, "Отчёт_OZON_*.xlsx"
            )
            for ozon_path in ozon_files:
                try:
                    data = OZONReportReader.read(
                        report_path=ozon_path,
                        sellers=sellers,
                        kiz_validator=self.kiz_validator,
                        logger=logger,
                    )
                    if data is None:
                        continue
                    kiz_by_seller[data.seller.name].update(data.full_kizs)
                    prices_by_seller[data.seller.name].update(data.prices)
                except Exception as e:
                    logger.critical(
                        f"Ошибка обработки файла {Path(ozon_path).name}: "
                        f"{e}",
                        can_influence=False,
                    )
                    continue
        # ------------------------------------------------------------
        # 3. Сохранение цен из отчётов МП — вне батча.
        # ------------------------------------------------------------
        try:
            FbsBufferPrices(ctx.processing_dir).save(prices_by_seller)
            logger.report(
                f"  Цены сохранены в {FbsBufferPrices.FILENAME}"
            )
        except (IOError, OSError) as e:
            logger.critical(
                f"Не удалось сохранить {FbsBufferPrices.FILENAME}: {e}",
                can_influence=False,
            )

        # ------------------------------------------------------------
        # 4. Сохранение текстовых файлов — вне батча.
        # .txt-файлы не связаны с used_kiz.json и не должны зависеть
        # от финального save() KizStorage.
        # ------------------------------------------------------------
        logger.report("\n--- СОХРАНЕНИЕ ТЕКСТОВЫХ ФАЙЛОВ ---")
        for seller_name, kiz_set in kiz_by_seller.items():
            if not kiz_set:
                logger.report(
                    f"  {seller_name}: нет КИЗов – файл не создан"
                )
                continue
            txt_path = ctx.processing_dir / f"{seller_name}.txt"
            TextFileWriter.write(
                txt_path, header=None, items=sorted(kiz_set), logger=logger,
            )
            logger.report(
                f"  {seller_name}: сохранено {len(kiz_set)} КИЗов "
                f"в {txt_path.name}"
            )

        logger.report("\n=== ВЫГРУЗКА ЗАВЕРШЕНА ===")

class FilterPreFinalService:
    """Сервис фильтрации предитоговых файлов.

    Роль:
        Для каждого продавца берёт файл из «Обработки» и оставляет
        только строки со статусом «В ОБОРОТЕ» и допустимым
        владельцем (см. TextUtils.get_allowed_companies).
        Файл перезаписывается на месте — дальнейшие шаги пайплайна
        работают с уже очищенными данными.

    Публичный API:
        filter_files(target_dir, sellers, log_callback).
    """

    def __init__(self, kiz_validator, log_manager_v2,
                 brand_unknown_resolver=None) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator: на шаге фильтрации
                            удаляются записи из used_kiz.json по
                            брендам с requires_saving=False.
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
            brand_unknown_resolver — Callable[[dict[str, list[str]]],
                            dict[str, int]] | None. Callback для
                            UI-разрешения неизвестных брендов:
                            принимает brands_unknown, возвращает
                            {"total", "resolved", "skipped"}. Вызов —
                            только в UI-потоке. None — UI-разрешение
                            недоступно, неизвестные бренды остаются
                            как есть.

        Роль: сохраняет ссылки. Логгер создаётся в начале
              filter_files, когда уже известна рабочая папка.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2
        self._brand_unknown_resolver = brand_unknown_resolver

    def filter_files(self, target_dir, sellers) -> None:
        """Фильтрует предитоговые файлы и чистит used_kiz.json.

        Вход:
            target_dir — корневая папка задачи.
            sellers — список Seller с восстановленными .brands
                      (см. ChzMPWindow._current_sellers).

        Выход: нет.

        Роль:
            Основной цикл — существующая фильтрация строк по
            статусу и владельцу + перезапись файлов. Второй цикл —
            сбор пар {kiz: brand_key} из уже отфильтрованных файлов.
            Пересечение с used_kiz.json + маппинг key → Brand +
            KizUtils.filter_for_removal определяют, какие записи
            удалить. Удаление — batch-контекстом, чтобы был один
            физический save на выходе.
        """
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_фильтрация.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )

        logger = self._log_manager_v2.create_logger_v2(
            source="FilterPreFinalService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_фильтрация.txt",
        )

        logger.report("=== ФИЛЬТРАЦИЯ ПРЕДИТОГОВЫХ ФАЙЛОВ ===")
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        # NEW: загружаем used_kiz.json — по нему будем считать пересечение.
        self.kiz_validator.load()

        allowed_companies = TextUtils.get_allowed_companies(sellers)

        # ------------------------------------------------------------------
        # 1. Основной цикл: фильтрация строк в предитоговых файлах.
        # ------------------------------------------------------------------
        kiz_to_brand_data: dict = {}
        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

            logger.report(f"\nОбработка файла: {file_path.name}")

            wb = WorkbookOpener.open(
                file_path, logger=logger,
                description="предитоговый файл", read_only=False,
            )
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    logger.report(
                        "  Файл пуст (только заголовки) – пропущен"
                    )
                    continue

                original_sheet_title = sheet.title
                headers = [cell.value for cell in sheet[1]]

                filtered_rows, stats = ExcelHelper.filter_and_clean_rows(
                    sheet,
                    status_col=4,          # столбец D
                    owner_col=12,          # столбец L
                    allowed_owners=allowed_companies,
                    required_status="В ОБОРОТЕ",
                )

                logger.report(f"  Всего строк: {sheet.max_row - 1}")
                if stats['status']:
                    logger.report("  Удалено по статусу:")
                    for status, count in sorted(
                        stats['status'].items(),
                        key=lambda x: x[0].lower(),
                    ):
                        logger.report(
                            f"    Статус '{status}': {count} строк"
                        )
                if stats['owner']:
                    logger.report("  Удалено по владельцу:")
                    for owner, count in sorted(
                        stats['owner'].items(),
                        key=lambda x: x[0].lower(),
                    ):
                        logger.report(
                            f"    Владелец '{owner}': {count} строк"
                        )
                logger.report(f"  Сохранено: {stats['total_kept']} строк")

                if stats['total_kept'] == 0:
                    logger.report(
                        "  Нет строк для сохранения – файл будет "
                        "очищен (только заголовки)"
                    )
            finally:
                wb.close()

            rows_for_write = [values for _, values in filtered_rows]
            WorkbookWriter.overwrite(
                file_path, headers, rows_for_write,
                sheet_name=original_sheet_title, logger=logger,
            )

            # ------------------------------------------------------------------
            # 2. Второй цикл — сбор пар {kiz: (норм_ключ, сырая_строка)} из
            #    отфильтрованных файлов. Первое вхождение КИЗа приоритетно
            #    (порядок sellers задаёт обход).
            # ------------------------------------------------------------------

            for seller in sellers:
                file_path = ctx.processing_dir / f"{seller.name}.xlsx"
                if not file_path.is_file():
                    continue

                wb = WorkbookOpener.open(
                    file_path, logger=logger,
                    description="предитоговый файл", read_only=True,
                )
                if wb is None:
                    continue

                try:
                    sheet = wb.active
                    for row_idx, row in enumerate(
                            sheet.iter_rows(min_row=2, values_only=True),
                            start=2,
                    ):
                        parsed = PreFinalRow.from_row(row)
                        if parsed is None:
                            continue
                        if parsed.kiz in kiz_to_brand_data:
                            continue
                        kiz_to_brand_data[parsed.kiz] = (
                            TextUtils.normalize(parsed.brand),
                            parsed.brand,
                        )
                finally:
                    wb.close()

        # ------------------------------------------------------------------
        # 3. Пересечение с used_kiz.json + маппинг key → Brand + отбор.
        # ------------------------------------------------------------------
        used_kiz_keys = set(self.kiz_validator.storage.get_all().keys())
        intersection = {
            k: v for k, v in kiz_to_brand_data.items()
            if k in used_kiz_keys
        }

        # Уникальные Brand из sellers[].brands, дедуп по имени.
        seen_names: set = set()
        unique_brands: list = []
        for seller in sellers:
            for brand in seller.brands:
                if brand.name not in seen_names:
                    seen_names.add(brand.name)
                    unique_brands.append(brand)

        brand_key_to_brand = TextUtils.build_key_mapping(
            unique_brands,
            key_extractor=lambda b: b.get_all_keys(),
            logger=logger,
        )

        total_in_files = len(kiz_to_brand_data)

        to_delete, stats, brands_unknown = KizUtils.filter_for_removal(
            intersection, brand_key_to_brand, logger=logger,
        )

        # ------------------------------------------------------------------
        # 4. Сводка.
        # ------------------------------------------------------------------
        logger.report("\n=== СВОДКА ПО ФИЛЬТРАЦИИ КИЗОВ ===")
        logger.report(
            f"Всего уникальных КИЗов в предитоговых файлах "
            f"после фильтрации: {total_in_files}"
        )
        logger.report(
            f"Из них есть в used_kiz.json: {stats['total']}"
        )
        logger.report(f"С пустым брендом: {stats['empty_brand']}")
        logger.report(f"С неизвестным брендом: {stats['unknown_brand']}")
        logger.report(f"Распознано брендов: {stats['recognized']}")
        logger.report(
            f"requires_saving=True → сохранено: {stats['saved']}"
        )
        logger.report(
            f"requires_saving=False → удалено: {stats['deleted']}"
        )
        if stats["top_deleted"]:
            logger.report(
                "Топ-10 брендов по количеству удалённых КИЗов:"
            )
            for i, (brand_name, count) in enumerate(
                stats["top_deleted"], start=1,
            ):
                logger.report(f"  {i}. {brand_name}: {count}")

        if brands_unknown:
            if self._brand_unknown_resolver is None:
                logger.report(
                    f"UI-обработка неизвестных брендов недоступна: "
                    f"{len(brands_unknown)} ключей остаются "
                    f"неизвестными"
                )
            else:
                try:
                    result = self._brand_unknown_resolver(brands_unknown)
                except Exception as e:
                    logger.critical(
                        f"Ошибка обработки неизвестных брендов: {e}",
                        can_influence=False,
                    )
                else:
                    if isinstance(result, dict) and all(
                            key in result
                            for key in ("total", "resolved", "skipped")
                    ):
                        logger.report(
                            f"Разрешение неизвестных брендов: всего "
                            f"{result['total']}, разрешено "
                            f"{result['resolved']}, пропущено "
                            f"{result['skipped']}"
                        )
                    else:
                        logger.warning(
                            "Callback неизвестных брендов вернул "
                            "некорректный результат"
                        )

        # ------------------------------------------------------------------
        # 5. Удаление из used_kiz.json — одним batch-контекстом.
        # ------------------------------------------------------------------
        if to_delete:
            X = len(used_kiz_keys)
            with self.kiz_validator.batch():
                deleted = self.kiz_validator.remove_kizs(to_delete)
            Y = X - deleted
            if deleted != len(to_delete):
                logger.warning(
                    f"remove_kizs: запрошено удалить {len(to_delete)}, "
                    f"реально удалено {deleted} – расхождение"
                )
            logger.info(
                f"used_kiz.json: было {X}, стало {Y}, удалено {deleted}"
            )

        logger.report("\n=== ФИЛЬТРАЦИЯ ЗАВЕРШЕНА ===")

class GenerateSalesService:
    """Сервис формирования файлов продаж.

    Роль:
        По предитоговым файлам продавцов строит файлы передачи
        КИЗов между продавцами. Владелец КИЗа (столбец L, читается
        через PreFinalRow) определяет отправителя, текущий продавец —
        получателя. Если владелец = текущий продавец, строка
        пропускается. Файлы продаж пишет SalesFileGenerator в
        подпапку Продажи/, пустые файлы в конце удаляются.

    Публичный API:
        generate(target_dir, sellers, log_callback).
    """

    def __init__(self, log_manager_v2, duplicate_keeper_resolver=None) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
            duplicate_keeper_resolver — Callable[[str, dict[Path, str]],
                Path | None] | None. Callback для UI-разрешения
                дублей: принимает (kiz, file_to_receiver), возвращает
                Path выбранного файла или None при отмене. Вызов —
                только в UI-потоке. None — UI-разрешение недоступно,
                межфайловые дубли остаются как есть.

        Роль: сохраняет ссылки. Логгер создаётся в начале generate.
        """
        self._log_manager_v2 = log_manager_v2
        self._duplicate_keeper_resolver = duplicate_keeper_resolver

    def generate(self, target_dir, sellers) -> None:
        """Запускает формирование файлов продаж."""
        # TaskContext — только пути, без логгера.
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_продажи.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )

        # Логгер V2 с историческим именем файла.
        logger = self._log_manager_v2.create_logger_v2(
            source="GenerateSalesService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_продажи.txt",
        )

        logger.report("=== ФОРМИРОВАНИЕ ФАЙЛОВ ПРОДАЖ ===")
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)

        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

            logger.report(f"\nОбработка файла: {file_path.name}")
            wb = WorkbookOpener.open(
                file_path, logger=logger,
                description="предитоговый файл", read_only=True,
            )
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    logger.report(
                        "  Файл пуст (только заголовки) – пропущен"
                    )
                    continue

                for row_idx, row in enumerate(
                    sheet.iter_rows(min_row=2, values_only=True),
                    start=2,
                ):
                    prefinal = PreFinalRow.from_row(row)
                    if prefinal is None:
                        logger.report(
                            f"  Строка {row_idx}: некорректные данные "
                            f"(нет КИЗа или владельца) – пропущена"
                        )
                        continue

                    # Находим продавца-владельца по company.
                    owner_seller = TextUtils.find_seller_by_company(
                        prefinal.owner_company, sellers
                    )
                    if owner_seller is None:
                        logger.report(
                            f"  Строка {row_idx}: владелец "
                            f"'{prefinal.owner_company}' не найден "
                            f"среди продавцов – пропущена"
                        )
                        continue

                    if owner_seller.name == seller.name:
                        continue

                    sales_gen.add_sale_row(
                        from_seller_name=owner_seller.name,
                        to_seller_name=seller.name,
                        to_seller_inn=seller.inn,
                        product_name=prefinal.product_name,
                        raw_kiz=prefinal.kiz,
                        owner_company=prefinal.owner_company,
                        brand=prefinal.brand,
                    )
            finally:
                wb.close()

                # ---- УДАЛЕНИЕ ПУСТЫХ ФАЙЛОВ ПРОДАЖ ----
            logger.report("\n--- ПРОВЕРКА ФАЙЛОВ ПРОДАЖ ---")
            removed = sales_gen.remove_empty_files()
            for file_path in sales_gen.get_created_files():
                logger.report(f"  Файл сохранён: {file_path.name}")

            if removed:
                logger.report(f"  Удалено пустых файлов: {removed}")

            # ---- СТАТИСТИКА ПРОДАЖ ----
            logger.report("\n--- СТАТИСТИКА ПРОДАЖ ---")
            stats = sales_gen.get_stats()
            if stats:
                for (from_seller, to_seller), count in sorted(stats.items()):
                    logger.report(
                        f"  {from_seller} → {to_seller}: {count} КИЗов"
                    )
            else:
                logger.report("  Нет строк для передачи между продавцами")

            # ---- ПОИСК И РАЗРЕШЕНИЕ ДУБЛЕЙ КИЗОВ ----
            logger.report("\n--- ПРОВЕРКА ДУБЛЕЙ КИЗОВ ---")

            intra_file, inter_file = KizDuplicatesFinder.find(
                ctx.sales_dir, logger,
            )

            # 6.4 — intra-file дедупликация.
            intra_files_count = len(intra_file)
            intra_deleted_rows = 0
            for file_path in intra_file:
                deleted = SalesFileRowsReader.remove_duplicates_in_file(
                    file_path, logger,
                )
                intra_deleted_rows += deleted
                logger.debug(
                    f"КИЗ в файле {file_path.name}: удалено дублей {deleted}"
                )

            # 6.5–6.6 — inter-file обработка через callback.
            inter_count = len(inter_file)
            resolved_count = 0
            removed_occurrences = 0

            if inter_file:
                if self._duplicate_keeper_resolver is None:
                    logger.warning(
                        f"UI-обработка дублей недоступна: {inter_count} "
                        f"КИЗов остаются в нескольких файлах"
                    )
                else:
                    for kiz, file_paths in inter_file.items():
                        file_to_receiver = {
                            p: (sales_gen.get_receiver_name(p) or p.name)
                            for p in file_paths
                        }
                        chosen = None
                        try:
                            chosen = self._duplicate_keeper_resolver(
                                kiz, file_to_receiver,
                            )
                        except Exception as e:
                            logger.critical(
                                f"Ошибка в резолвере дублей: {e}",
                                can_influence=False,
                            )
                            chosen = None
                        if chosen is None or chosen not in file_paths:
                            chosen = file_paths[0]
                        resolved_count += 1

                        removed_names = []
                        for p in file_paths:
                            if p == chosen:
                                continue
                            ok = SalesFileRowsReader.remove_kiz(
                                p, kiz, logger,
                            )
                            if ok:
                                removed_occurrences += 1
                                removed_names.append(p.name)
                            else:
                                logger.warning(
                                    f"Не удалось удалить КИЗ {kiz} "
                                    f"из {p.name}"
                                )

                        logger.debug(
                            f"КИЗ {kiz}: найден в "
                            f"{[p.name for p in file_paths]}; "
                            f"оставлен в {chosen.name}; "
                            f"удалён из {removed_names}"
                        )

            # 6.7 — второй remove_empty_files: только если что-то менялось.
            empty_removed_after = 0
            if intra_files_count > 0 or inter_count > 0:
                empty_removed_after = sales_gen.remove_empty_files()

            # 6.8 — report-сводка.
            logger.report(
                f"Найдено внутрифайловых дублей: {intra_files_count} файлов, "
                f"удалено {intra_deleted_rows} строк"
            )
            logger.report(
                f"Найдено межфайловых дублей: {inter_count} КИЗов"
            )
            logger.report(
                f"Разрешено в пользу файла: {resolved_count}; "
                f"удалено вхождений: {removed_occurrences}"
            )
            logger.report(
                f"После чистки удалено пустых файлов: {empty_removed_after}"
            )

            logger.report("\n=== ФОРМИРОВАНИЕ ПРОДАЖ ЗАВЕРШЕНО ===")

class FinalizePricesService:
    """Сервис внесения цен и финализации итоговых файлов.

    Роль:
        Для каждого продавца создаёт ИТОГ в корне рабочей папки
        (копия предитогового файла из «Обработки») и заполняет
        цены в три этапа через PriceFiller:
            1. Цены из отчёта МП — точное совпадение по КИЗу.
            2. Распределение числовых цен внутри кластеров GTIN.
            3. Генерация по средней для оставшихся нечисловых.

        Исходник в «Обработке» не изменяется — вся работа идёт
        с копией. Средняя определяется AveragePriceResolver;
        если ни один источник не подошёл — вызывается
        price_requester, переданный из UI.

    Публичный API:
        finalize(target_dir, sellers, saved_prices).
    """

    def __init__(self, kiz_validator, log_manager_v2,
                 price_requester=None) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator для set_log_path/load.
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
            price_requester — опциональный callable(seller_name) -> int | None.
                              Вызывается, когда нужно спросить цену у
                              пользователя. Обязан выполняться в
                              UI-потоке и возвращать либо int-цену,
                              либо None при отмене.

        Роль:
            Сохраняет ссылки. Логгер создаётся в начале finalize —
            когда уже известна рабочая папка. Диалог ввода цены
            сервис сам не открывает: этим занимается окно.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2
        self._price_requester = price_requester

    def _load_prices_from_json(self, processing_dir, logger) -> dict:
        """Читает цены из буфера FbsBufferPrices.

        Вход:
            processing_dir — папка «Обработка» рабочей папки.
            logger — LoggerV2 для сообщения об отсутствии файла.

        Выход:
            dict {seller_name: {storage_kiz: price}} или {}.

        Роль:
            Тонкая обёртка над FbsBufferPrices.load(): добавляет
            только report-сообщение при пустом результате. Ошибки
            чтения FbsBufferPrices глотает сам и возвращает {}.
        """
        data = FbsBufferPrices(processing_dir).load()
        if not data:
            logger.report(
                f"  {FbsBufferPrices.FILENAME} не найден или пуст – "
                f"цены не будут применены"
            )
        return data

    def finalize(self, target_dir, sellers, saved_prices=None) -> dict:
        """Финализация цен по продавцам.

        Вход:
            target_dir — корень рабочей папки.
            sellers — список Seller.
            saved_prices — dict {seller_name: средняя}, может быть пуст.

        Выход:
            Обновлённый saved_prices (та же ссылка, что и входная,
            если она была передана).

        Роль:
            Создаёт TaskContext (пути) и LoggerV2. Для каждого
            продавца: определяет среднюю через AveragePriceResolver,
            при необходимости запрашивает её через price_requester,
            проверяет, не обработан ли ИТОГ, копирует исходник,
            применяет три этапа через PriceFiller и сохраняет.
        """
        if saved_prices is None:
            saved_prices = {}

        # TaskContext — только пути.
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_цены.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )

        # Логгер V2 с историческим именем файла.
        logger = self._log_manager_v2.create_logger_v2(
            source="FinalizePricesService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_цены.txt",
        )

        logger.report("=== ВНЕСЕНИЕ ЦЕН И ФИНАЛИЗАЦИЯ ===")
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        self.kiz_validator.set_log_path(ctx.logs_dir)
        self.kiz_validator.load()

        # Цены из отчётов читаем один раз — до цикла по продавцам.
        all_prices = self._load_prices_from_json(
            ctx.processing_dir, logger
        )

        for seller in sellers:
            price_map = all_prices.get(seller.name, {})
            prices_list = list(price_map.values())

            logger.report(f"\nПродавец '{seller.name}'")

            # ---- 1. Определяем среднюю через резолвер. ----
            decision = AveragePriceResolver.resolve(
                saved_prices, seller.name, prices_list
            )

            if decision.need_dialog:
                # Ни цен из отчёта, ни сохранённых цен вообще нет.
                if self._price_requester is None:
                    # Сервис не может открыть диалог сам: UI-поток
                    # ему недоступен. Логируем и пропускаем продавца.
                    logger.warning(
                        f"Не могу запросить цену без UI-callback, "
                        f"пропускаю продавца '{seller.name}'"
                    )
                    continue

                user_price = self._price_requester(seller.name)
                if user_price is None:
                    logger.report(
                        f"  Пользователь отменил ввод для продавца "
                        f"'{seller.name}' – пропускаем"
                    )
                    continue
                average_price = user_price
                saved_prices[seller.name] = average_price
                logger.report(
                    f"  Пользователь ввёл цену: {average_price}"
                )
            else:
                average_price = decision.price
                # Различаем источник в логе для диагностики.
                if prices_list:
                    logger.report(
                        f"  Загружено {len(prices_list)} цен из отчёта, "
                        f"средняя: {average_price}"
                    )
                elif saved_prices.get(seller.name):
                    logger.report(
                        f"  Использую сохранённую цену: {average_price}"
                    )
                else:
                    logger.report(
                        f"  Использую случайную среднюю с другого "
                        f"продавца: {average_price}"
                    )

            # ---- 2. Проверка существующего ИТОГа ----
            new_name = FilenameUtils.format_with_extension(
                f"ИТОГ {seller.name} {{date}}", ctx.date_str
            )
            new_path = ctx.work_folder / new_name

            # REPLACE: было self._is_processed(new_path, ctx) — стало
            # ExcelHelper.is_column_numeric. Номера столбцов берутся
            # из PriceFiller, чтобы не плодить магические числа.
            if new_path.is_file() and ExcelHelper.is_column_numeric(
                new_path,
                price_col=PriceFiller.PRICE_COL,
                kiz_col=PriceFiller.KIZ_COL,
                logger=logger,
                header=PriceFiller.HEADER_KIZ,
            ):
                logger.report(
                    f"ИТОГ {seller.name} уже создан и обработан "
                    f"ранее – пропускаем."
                )
                saved_prices[seller.name] = average_price
                continue

            # ---- 3. Предатоговый файл в «Обработке». ----
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

            # ---- 4. Копирование в корень как ИТОГ. ----
            FileHelper.copy_file_with_log(
                file_path, new_path, logger,
                description="итоговый файл", overwrite=True,
            )
            logger.report(f"Файл скопирован в корень: {new_path.name}")

            # ---- 5. Открытие ИТОГа и три этапа через PriceFiller. ----
            wb = WorkbookOpener.open(
                new_path, logger=logger,
                description="итоговый файл", read_only=False,
            )
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    logger.report(
                        "  Файл пуст (только заголовки) – пропущен"
                    )
                    continue

                # Этап 1 — цены из отчёта.
                stage1_count = PriceFiller.fill_from_report(
                    sheet, price_map
                )
                logger.report(
                    f"  Установлено цен из отчёта: {stage1_count}"
                )

                # Этап 2 — кластеры GTIN.
                stage2_stats = PriceFiller.fill_by_gtin_clusters(sheet)
                logger.report(
                    f"  Кластеров GTIN: {stage2_stats.total_clusters}"
                )
                logger.report(
                    f"  Обработано кластеров: {stage2_stats.processed}"
                )
                logger.report(
                    f"  Пропущено (нет числовых): "
                    f"{stage2_stats.skipped_no_numeric}"
                )
                logger.report(
                    f"  Пропущено (все числовые): "
                    f"{stage2_stats.skipped_all_numeric}"
                )
                logger.report(
                    f"  Установлено цен по кластерам GTIN: "
                    f"{stage2_stats.filled_rows}"
                )

                # Этап 3 — генерация по средней.
                stage3_count = PriceFiller.fill_by_average(
                    sheet, average_price
                )
                logger.report(
                    f"  Сгенерировано цен по средней: {stage3_count}"
                )

                # ---- 6. Сохранение ИТОГа. ----
                wb.save(new_path)
                logger.report(
                    f"  Итоговый файл сохранён: {new_path.name}"
                )
                saved_prices[seller.name] = average_price

            except Exception as e:
                # Ошибка обработки одного файла не должна валить
                # весь прогон — остальные продавцы продолжают.
                logger.critical(
                    f"Ошибка обработки файла {new_path.name}: {e}",
                    can_influence=False,
                )
            finally:
                try:
                    wb.close()
                except Exception:
                    pass

        logger.report("\n=== ФИНАЛИЗАЦИЯ ЗАВЕРШЕНА ===")
        return saved_prices
