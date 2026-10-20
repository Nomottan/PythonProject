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
    Вызываются из SellsFBSWindow по кнопкам пайплайна. Каждый сервис
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
from utils.parsers import DateParser, PreFinalRow
from datetime import datetime
from utils.price_utils import AveragePriceResolver, PriceFiller
from utils.sells_fbs_report_utils import (
    WBReportReader, OZONReportReader,
    WarehouseReportReader, WarehouseReportWriter,
    FileTypeDetector, ReturnsTxtWriter,
)
from utils.path_manager import PathManager
from utils.sales_file_generator import SalesFileGenerator, SalesFileRowsReader
from utils.fbs_buferprices import FbsBufferPrices
from utils.kiz_utils import KizUtils, KizDuplicatesFinder

class PreparationService:
    """Сервис шага «Подготовка»: опознание, копирование, разбор,
    чтение отчётов, разрешение конфликтов, финализация.

    Роль:
        Семь фаз: опознание входных файлов,
        копирование с новыми именами, разбивка склада, чтение
        всех отчётов в одном batch-контексте KizStorage,
        разрешение конфликтов КИЗов между продавцами, финализация
        (цены, .txt, сводки), очистка устаревших записей.

    Публичный API:
        prepare(target_dir, files=None, sellers=None).
    """

    # Ярлыки источников для разрешения конфликтов.
    # Коды: 0 — склад, 1 — WB, 2 — Ozon.
    _SOURCE_LABELS = {0: "ЧЗ МП", 1: "WB", 2: "Ozon"}

    def __init__(self, kiz_validator, log_manager_v2,
                 seller_unknown_resolver=None) -> None:
        """Конструктор.

                Вход:
                    kiz_validator — KizValidator.
                    log_manager_v2 — LogManagerV2.
                    seller_unknown_resolver — Callable[[dict, dict], dict] |
                        None. Вызывается из фонового потока, возвращает
                        {total, resolved, skipped, decisions}.
                """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2
        self._seller_unknown_resolver = seller_unknown_resolver
    # ============================================================
    # Публичный метод
    def _detect_all(self, files, logger) -> dict:
        """Определяет типы файлов и логирует сводку.

        Вход:
            files — список путей.
            logger — LoggerV2.

        Выход:
            dict {path: "wb"|"ozon"|"wh"|None}.

        Роль:
            Тонкая обёртка над FileTypeDetector.detect_all.
            Обход по файлам и логирование сводки (в report
            и в info) живут в детекторе — здесь только вызов.
        """
        return FileTypeDetector.detect_all(files, logger)

    # ============================================================
    # Приватные методы: опознание
    # ============================================================

    # ============================================================

    def _copy_wb_file(self, src_path, ctx, logger, sellers,
                      seller_counters, returns_txt_path,
                      decision=None) -> dict:
        """Копирует WB-отчёт (учитывая decision)."""
        seller = TextUtils.find_seller_by_file_name(
            src_path.stem.lower(), sellers,
        )
        if seller is not None:
            seller_key = seller.name
            seller_name = seller.name
            safe_name = TextUtils.sanitize_filename(seller.name)
            logger.report(f"  Продавец: {seller.name}")
        else:
            seller_name = None
            if decision is None:
                seller_key = src_path.stem
                safe_name = TextUtils.sanitize_filename(src_path.stem)
                logger.warning(f"\n{src_path.name}: продавец не определён")
                logger.report(" Продавец не определён")
            elif decision[0] == "seller":
                target = decision[1]
                seller_key = target
                seller_name = target
                safe_name = TextUtils.sanitize_filename(target)
                logger.report(f"  Продавец (по решению): {target}")
            elif decision[0] == "garbage":
                logger.report("  Мусор (по решению)")
                return {"status": "garbage", "type": "wb"}
            elif decision[0] == "unknown":
                safe_stem = TextUtils.sanitize_filename(src_path.stem)
                new_name = FilenameUtils.format_with_extension(
                    f"Неопознанный отчёт {safe_stem} {{date}}",
                    ctx.date_str,
                )
                dst = ctx.reports_dir / new_name
                result = FileHelper.copy_file_with_log(
                    src_path, dst, logger,
                    description="неопознанный отчёт", overwrite=False,
                )
                return {
                    "status": result["status"],
                    "type": "unknown",
                    "seller_name": None,
                    "dst_name": new_name,
                }
            elif decision[0] == "returns":
                logger.report("  Возвраты (по решению)")
                cells = []
                wb = WorkbookOpener.open(
                    src_path, logger=None, read_only=True,
                )
                if wb is not None:
                    try:
                        if "КИЗ" in wb.sheetnames:
                            sheet = wb["КИЗ"]
                            for row in sheet.iter_rows(values_only=True):
                                # Индекс 2 — столбец C. Совпадает с
                                # WBReportReader._load_occurrences.
                                if len(row) > 2:
                                    cells.append(row[2])
                    finally:
                        try:
                            wb.close()
                        except Exception:
                            pass
                ReturnsTxtWriter.append_cells(
                    cells, returns_txt_path, logger,
                )
                return {"status": "returns", "type": "wb"}
            else:
                return {"status": "error", "type": "wb"}

        counter_key = (seller_key, "wb")
        idx = seller_counters.get(counter_key, 0) + 1
        seller_counters[counter_key] = idx

        template = f"Отчёт_WB_{safe_name} {{date}}"
        if idx == 1:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str,
            )
        else:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str, index=idx,
            )
        dst = ctx.reports_dir / new_name
        result = FileHelper.copy_file_with_log(
            src_path, dst, logger,
            description="отчёт WB", overwrite=False,
        )
        return {
            "status": result["status"],
            "type": "wb",
            "seller_name": seller_name,
            "dst_name": new_name,
        }

    # ============================================================
    # Приватные методы: копирование
    # ============================================================

    def prepare(self, target_dir, files=None, sellers=None):
        """Запускает подготовку.

        Вход:
            target_dir — корневая папка задачи.
            files — список входных файлов (склад / WB / Ozon).
            sellers — список Seller. None → [].

        Выход: нет.
        """
        if sellers is None:
            sellers = []
        if files is None:
            files = []

        # ---------- Фаза 1. TaskContext + логгер. ----------
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_подготовка.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )
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

        # ---------- Фаза 2. Опознание. ----------
        logger.report(
            "\n==================== Этап: Опознание файлов ====================\n"
        )
        logger.info(
            "\n==================== Этап: Опознание файлов ====================\n"
        )
        logger.status("Опознание входных файлов")

        try:
            detected = self._detect_all(files, logger)
        except Exception as e:
            logger.critical(
                f"Ошибка опознания файлов: {e}",
                can_influence=False,
            )
            detected = {}

        if not files:
            logger.warning("\nНет входных файлов для копирования")

        # ---------- Фаза 3. Копирование WH-файлов. ----------
        logger.report(
            "\n==================== Этап: Копирование склада ====================\n"
        )
        logger.info(
            "\n==================== Этап: Копирование склада ====================\n"
        )

        seller_counters: dict = {}
        stats = {
            "copied_wb": 0, "copied_ozon": 0, "copied_wh": 0,
            "copied_unknown": 0, "copied_garbage": 0, "processed_returns": 0,
            "exists": 0, "error": 0,
            "sellers_wb": set(), "sellers_ozon": set(),
        }

        for src, file_type in detected.items():
            if file_type != "wh":
                continue
            logger.status(f"Обрабатывается: {Path(src).name}")
            logger.report(f"\nОбработка файла: {Path(src).name}")
            r = self._copy_wh_file(
                Path(src), ctx, logger, seller_counters,
            )
            status = r.get("status")
            if status == "copied":
                stats["copied_wh"] += 1
            elif status == "exists":
                stats["exists"] += 1
            else:
                stats["error"] += 1

        # ---------- Фаза 4. Сбор unresolved + context_map. ----------
        logger.report(
            "\n==================== Этап: Сбор неизвестных ====================\n"
        )
        logger.info(
            "\n==================== Этап: Сбор неизвестных ====================\n"
        )

        # R1: путь returns.txt готовим заранее — он нужен уже в фазе 5.
        returns_txt_dir = PathManager.ensure_dir(
            Path(ctx.target_dir) / ctx.date_str
            / f"Возвратов_{ctx.date_str}" / "Отчёты"
        )
        returns_txt_path = returns_txt_dir / "возвраты.txt"

        unresolved: dict = {}
        context_map: dict = {}

        # MP: WB/Ozon без продавца.
        for src, file_type in detected.items():
            if file_type not in ("wb", "ozon"):
                continue
            src_path = Path(src)
            seller = TextUtils.find_seller_by_file_name(
                src_path.stem.lower(), sellers,
            )
            if seller is None:
                nk = TextUtils.normalize(src_path.stem)
                unresolved.setdefault(nk, []).append(src_path.stem)
                context_map.setdefault(nk, set()).add("mp")

        # WH: листы без продавца.
        wh_files = FileHelper.find_files_by_pattern(
            ctx.reports_dir, "Склад_*.xlsx",
        )
        for wh_path in wh_files:
            sheets = WarehouseReportWriter.scan(
                wh_path, sellers, logger,
            )
            for info in sheets:
                if info.seller is not None or info.is_empty:
                    continue
                nk = TextUtils.normalize(info.sheet_name)
                unresolved.setdefault(nk, []).append(info.sheet_name)
                context_map.setdefault(nk, set()).add("wh")

        # Резолвер.
        result = {
            "total": 0, "resolved": 0,
            "skipped": len(unresolved), "decisions": {},
        }
        if unresolved:
            logger.status("Запрос решений по неизвестным именам")
            if self._seller_unknown_resolver is None:
                logger.report(
                    f"\nUI-резолвер не передан, {len(unresolved)} "
                    f"неизвестных имён остаются без решения"
                )
            else:
                try:
                    result = self._seller_unknown_resolver(
                        unresolved, context_map,
                    )
                except Exception as e:
                    logger.critical(
                        f"Ошибка резолвера неизвестных имён: {e}",
                        can_influence=False,
                    )
                    result = {
                        "total": 0, "resolved": 0,
                        "skipped": len(unresolved), "decisions": {},
                    }
            logger.info(
                f"\nРазрешение неизвестных имён: всего "
                f"{result['total']}, разрешено {result['resolved']}, "
                f"пропущено {result['skipped']}"
            )

        decisions = result.get("decisions", {})

        # ---------- Фаза 5. Копирование WB/Ozon с decisions. ----------
        logger.report(
            "\n==================== Этап: Копирование отчётов МП ====================\n"
        )
        logger.info(
            "\n==================== Этап: Копирование отчётов МП ====================\n"
        )

        for src, file_type in detected.items():
            if file_type not in ("wb", "ozon"):
                continue
            src_path = Path(src)
            norm_stem = TextUtils.normalize(src_path.stem)
            decision = decisions.get(norm_stem)

            logger.status(f"Обрабатывается: {src_path.name}")
            logger.report(f"\nОбработка файла: {src_path.name}")

            if file_type == "wb":
                r = self._copy_wb_file(
                    src_path, ctx, logger, sellers,
                    seller_counters, returns_txt_path, decision,
                )
            else:
                r = self._copy_ozon_file(
                    src_path, ctx, logger, sellers,
                    seller_counters, returns_txt_path, decision,
                )

            status = r.get("status")
            rtype = r.get("type")
            seller_name = r.get("seller_name")

            if status == "copied":
                if rtype == "wb":
                    stats["copied_wb"] += 1
                    if seller_name:
                        stats["sellers_wb"].add(seller_name)
                elif rtype == "ozon":
                    stats["copied_ozon"] += 1
                    if seller_name:
                        stats["sellers_ozon"].add(seller_name)
                else:
                    stats["copied_unknown"] += 1
            elif status == "exists":
                stats["exists"] += 1
            elif status == "garbage":
                stats["copied_garbage"] += 1
            elif status == "returns":
                stats["processed_returns"] += 1
            else:
                stats["error"] += 1

        # Сводка копирования.
        copied_total = (
            stats["copied_wb"] + stats["copied_ozon"]
            + stats["copied_wh"] + stats["copied_unknown"]
            + stats["copied_garbage"] + stats["processed_returns"]
        )
        lines = [f"Скопировано всего: {copied_total}"]
        if stats["copied_wh"] > 0:
            lines.append(f"  Склад (ЧЗ МП): {stats['copied_wh']}")
        if stats["copied_wb"] > 0:
            lines.append(f"  WB: {stats['copied_wb']}")
        if stats["copied_ozon"] > 0:
            lines.append(f"  Ozon: {stats['copied_ozon']}")
        if stats["copied_unknown"] > 0:
            lines.append(f"  Неопознанные: {stats['copied_unknown']}")
        if stats["copied_garbage"] > 0:
            lines.append(f"  Мусор: {stats['copied_garbage']}")
        if stats["processed_returns"] > 0:
            lines.append(f"  Возвраты: {stats['processed_returns']}")
        lines.append(f"Не скопировано: {stats['exists'] + stats['error']}")
        if stats["exists"] > 0:
            lines.append(f"  Уже существует: {stats['exists']}")
        if stats["error"] > 0:
            lines.append(f"  Ошибка копирования: {stats['error']}")
        if stats["sellers_wb"] or stats["sellers_ozon"]:
            lines.append("Продавцы:")
            if stats["sellers_wb"]:
                lines.append(
                    f"  WB: {', '.join(sorted(stats['sellers_wb']))}"
                )
            if stats["sellers_ozon"]:
                lines.append(
                    f"  Ozon: {', '.join(sorted(stats['sellers_ozon']))}"
                )
        logger.info("\n".join(lines))

        # ---------- Фаза 6. Разбивка склада. ----------
        logger.report(
            "\n==================== Этап: Разбивка склада ====================\n"
        )
        logger.info(
            "\n==================== Этап: Разбивка склада ====================\n"
        )
        logger.status("Разбивка складских отчётов по продавцам")
        wh_stats = self._write_wh_reports(
            ctx, logger, sellers, decisions, returns_txt_path,
        )

        # ---------- Фаза 7. Чтение отчётов (единый batch). ----------
        logger.report(
            "\n==================== Этап: Чтение отчётов ====================\n"
        )
        logger.info(
            "\n==================== Этап: Чтение отчётов ====================\n"
        )

        kiz_by_seller: dict = {s.name: set() for s in sellers}
        prices_by_seller: dict = {s.name: {} for s in sellers}
        kiz_owners: dict = {}
        missed_files: list = []
        wb_sellers_with_kiz: set = set()
        size_before = len(self.kiz_validator.storage.get_all())

        with self.kiz_validator.batch():
            wh_result = self._read_wh_reports(ctx, sellers, logger)
            wb_result = self._read_wb_reports(ctx, sellers, logger)
            ozon_result = self._read_ozon_reports(ctx, sellers, logger)

            self._merge_read_result(
                wh_result, kiz_by_seller, prices_by_seller, kiz_owners,
            )
            self._merge_read_result(
                wb_result, kiz_by_seller, prices_by_seller, kiz_owners,
            )
            self._merge_read_result(
                ozon_result, kiz_by_seller, prices_by_seller, kiz_owners,
            )

            wb_sellers_with_kiz.update(
                wb_result.get("sellers_with_kiz", set())
            )
            missed_files.extend(wh_result["missed"])
            missed_files.extend(wb_result["missed"])
            missed_files.extend(ozon_result["missed"])

        # ---------- Фаза 8. Разрешение конфликтов. ----------
        logger.report(
            "\n==================== Этап: Разрешение конфликтов ====================\n"
        )
        logger.info(
            "\n==================== Этап: Разрешение конфликтов ====================\n"
        )
        conflict_stats = self._resolve_kiz_conflicts(
            kiz_owners, kiz_by_seller, sellers, logger,
        )

        # ---------- Фаза 9. Финализация. ----------
        logger.report(
            "\n==================== Этап: Финализация ====================\n"
        )
        logger.info(
            "\n==================== Этап: Финализация ====================\n"
        )
        self._finalize_reports(
            ctx, logger, sellers, kiz_by_seller, prices_by_seller,
            wb_sellers_with_kiz, missed_files,
            wh_result, wb_result, ozon_result, size_before,
            conflict_stats, detected, stats,
        )

        # ---------- Финал. ----------
        logger.report("Подготовка завершена.")
        logger.status("Подготовка завершена")
        self.kiz_validator.load()
        deleted = self.kiz_validator.clean_old_entries(months=1)
        logger.info(f"Очистка старых записей: удалено {deleted}.")
        logger.info("\n==================================================\n")
    def _copy_ozon_file(self, src_path, ctx, logger, sellers,
                        seller_counters, returns_txt_path,
                        decision=None) -> dict:
        """Копирует Ozon-отчёт (учитывая decision)."""
        seller = TextUtils.find_seller_by_file_name(
            src_path.stem.lower(), sellers,
        )
        if seller is not None:
            seller_key = seller.name
            seller_name = seller.name
            safe_name = TextUtils.sanitize_filename(seller.name)
            logger.report(f"  Продавец: {seller.name}")
        else:
            seller_name = None
            if decision is None:
                seller_key = src_path.stem
                safe_name = TextUtils.sanitize_filename(src_path.stem)
                logger.warning(f"\n{src_path.name}: продавец не определён")
                logger.report(" Продавец не определён")
            elif decision[0] == "seller":
                target = decision[1]
                seller_key = target
                seller_name = target
                safe_name = TextUtils.sanitize_filename(target)
                logger.report(f"  Продавец (по решению): {target}")
            elif decision[0] == "garbage":
                logger.report("  Мусор (по решению)")
                return {"status": "garbage", "type": "ozon"}
            elif decision[0] == "unknown":
                safe_stem = TextUtils.sanitize_filename(src_path.stem)
                new_name = FilenameUtils.format_with_extension(
                    f"Неопознанный отчёт {safe_stem} {{date}}",
                    ctx.date_str,
                )
                dst = ctx.reports_dir / new_name
                result = FileHelper.copy_file_with_log(
                    src_path, dst, logger,
                    description="неопознанный отчёт", overwrite=False,
                )
                return {
                    "status": result["status"],
                    "type": "unknown",
                    "seller_name": None,
                    "dst_name": new_name,
                }
            elif decision[0] == "returns":
                logger.report("  Возвраты (по решению)")
                cells = []
                wb = WorkbookOpener.open(
                    src_path, logger=None, read_only=True,
                )
                if wb is not None:
                    try:
                        if "Отчет" in wb.sheetnames:
                            sheet = wb["Отчет"]
                            for row in sheet.iter_rows(values_only=True):
                                # Индекс 8 — из FALLBACK_COLUMNS["kiz"].
                                if len(row) > 8:
                                    cells.append(row[8])
                    finally:
                        try:
                            wb.close()
                        except Exception:
                            pass
                ReturnsTxtWriter.append_cells(
                    cells, returns_txt_path, logger,
                )
                return {"status": "returns", "type": "ozon"}
            else:
                return {"status": "error", "type": "ozon"}

        counter_key = (seller_key, "ozon")
        idx = seller_counters.get(counter_key, 0) + 1
        seller_counters[counter_key] = idx

        template = f"Отчёт_OZON_{safe_name} {{date}}"
        if idx == 1:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str,
            )
        else:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str, index=idx,
            )
        dst = ctx.reports_dir / new_name
        result = FileHelper.copy_file_with_log(
            src_path, dst, logger,
            description="отчёт Ozon", overwrite=False,
        )
        return {
            "status": result["status"],
            "type": "ozon",
            "seller_name": seller_name,
            "dst_name": new_name,
        }

    def _copy_wh_file(self, src_path, ctx, logger,
                      seller_counters) -> dict:
        """Копирует складской отчёт под именем «Склад_{date}»."""
        counter_key = ("_wh_", "wh")
        idx = seller_counters.get(counter_key, 0) + 1
        seller_counters[counter_key] = idx

        template = "Склад_{date}"
        if idx == 1:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str,
            )
        else:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str, index=idx,
            )
        dst = ctx.reports_dir / new_name
        result = FileHelper.copy_file_with_log(
            src_path, dst, logger,
            description="склад", overwrite=False,
        )
        return {
            "status": result["status"],
            "type": "wh",
            "dst_name": new_name,
        }

    def _copy_unknown_file(self, src_path, ctx, logger,
                           seller_counters) -> dict:
        """Копирует неопознанный файл как «Неопознанный отчёт {stem} {date}»."""
        counter_key = (src_path.stem, "unknown")
        idx = seller_counters.get(counter_key, 0) + 1
        seller_counters[counter_key] = idx

        template = f"Неопознанный отчёт {src_path.stem} {{date}}"
        if idx == 1:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str,
            )
        else:
            new_name = FilenameUtils.format_with_extension(
                template, ctx.date_str, index=idx,
            )
        dst = ctx.reports_dir / new_name
        result = FileHelper.copy_file_with_log(
            src_path, dst, logger,
            description="неопознанный отчёт", overwrite=False,
        )
        return {
            "status": result["status"],
            "type": "unknown",
            "dst_name": new_name,
        }

    # ============================================================
    # Приватные методы: разбивка склада
    # ============================================================

    def _write_wh_reports(self, ctx, logger, sellers, decisions,
                          returns_txt_path) -> dict:
        """Второй проход по складским отчётам с учётом decisions."""
        wh_files = FileHelper.find_files_by_pattern(
            ctx.reports_dir, "Склад_*.xlsx",
        )
        totals = {
            "created": 0, "appended": 0,
            "skipped_garbage": 0, "written_unknown": 0,
            "written_returns": 0,
        }
        for file_path in wh_files:
            result = WarehouseReportWriter.write(
                file_path, decisions, returns_txt_path,
                ctx.reports_dir, sellers, ctx.date_str, logger,
            )
            totals["created"] += result.get("created", 0)
            totals["appended"] += result.get("appended", 0)
            totals["skipped_garbage"] += result.get("skipped_garbage", 0)
            totals["written_unknown"] += result.get("written_unknown", 0)
            totals["written_returns"] += result.get("written_returns", 0)

        logger.info("\n".join([
            "Разбивка склада:",
            f"  Создано: {totals['created']}",
            f"  Дополнено: {totals['appended']}",
            f"  Мусор: {totals['skipped_garbage']}",
            f"  Неопознанных: {totals['written_unknown']}",
            f"  Возвратов: {totals['written_returns']}",
        ]))
        return totals

    # ============================================================
    # Приватные методы: чтение отчётов
    # ============================================================

    def _read_wh_reports(self, ctx, sellers, logger) -> dict:
        """Читает все «Отчёт_склада_*.xlsx».

        Выход:
            dict со стандартными ключами (см. _read_wb_reports).
            Источник 0 в kiz_owners.
        """
        files = FileHelper.find_files_by_pattern(
            ctx.reports_dir, "Отчёт_склада_*.xlsx",
        )
        result = {
            "added": 0,
            "blocks": [],
            "missed": [],
            "sellers_with_kiz": set(),
            "kiz_by_seller": {},
            "prices_by_seller": {},
            "kiz_owners": {},
        }
        today_str = ctx.today.strftime("%d.%m.%Y")

        for file_path in files:
            try:
                read_result = WarehouseReportReader.read(
                    report_path=file_path,
                    sellers=sellers,
                    kiz_validator=self.kiz_validator,
                    logger=logger,
                )
                if read_result.reason is not None:
                    result["missed"].append(
                        (file_path.name, read_result.reason)
                    )
                    continue
                data = read_result.data
                if data is None:
                    continue

                result["added"] += data.added
                seller_name = data.seller.name
                result["kiz_by_seller"].setdefault(seller_name, set())
                result["kiz_by_seller"][seller_name].update(data.full_kizs)

                for full_kiz in data.full_kizs:
                    result["kiz_owners"].setdefault(full_kiz, []).append(
                        (seller_name, today_str, 0)
                    )

                result["blocks"].append("\n".join([
                    f"Файл: {file_path.name}",
                    f"  Продавец: {seller_name}",
                    f"  Всего уникальных: {data.total_unique}",
                    f"  Добавлено: {data.added}",
                    f"  Отсеяно (товар не возвращён): "
                    f"{data.skipped_no_return + data.skipped_date_before_return}",
                    f"  Дубликаты в отчёте: {data.skipped_dup}",
                ]))
            except Exception as e:
                logger.critical(
                    f"Ошибка обработки файла {file_path.name}: {e}",
                    can_influence=False,
                )
                result["missed"].append(
                    (file_path.name, "ошибка чтения")
                )
                continue

        if result["blocks"]:
            logger.info("\n" + "\n\n".join(result["blocks"]))
        return result

    def _read_wb_reports(self, ctx, sellers, logger) -> dict:
        """Читает все «Отчёт_WB_*.xlsx».

        Выход:
            dict {
                added: int,
                blocks: list[str],
                missed: list[(file_name, reason)],
                sellers_with_kiz: set,
                kiz_by_seller: {seller_name: set(full_kiz)},
                prices_by_seller: {seller_name: {storage_kiz: price}},
                kiz_owners: {full_kiz: [(seller, date, src)]},
            }
            Источник 1 в kiz_owners.
        """
        files = FileHelper.find_files_by_pattern(
            ctx.reports_dir, "Отчёт_WB_*.xlsx",
        )
        result = {
            "added": 0,
            "blocks": [],
            "missed": [],
            "sellers_with_kiz": set(),
            "kiz_by_seller": {},
            "prices_by_seller": {},
            "kiz_owners": {},
        }

        for file_path in files:
            try:
                logger.status(f"Обработка отчёта WB: {file_path.name}")
                read_result = WBReportReader.read(
                    report_path=file_path,
                    sellers=sellers,
                    kiz_validator=self.kiz_validator,
                    logger=logger,
                )
                if read_result.reason is not None:
                    result["missed"].append(
                        (file_path.name, read_result.reason)
                    )
                    continue
                data = read_result.data
                if data is None:
                    continue

                result["added"] += data.added
                seller_name = data.seller.name
                result["kiz_by_seller"].setdefault(seller_name, set())
                result["kiz_by_seller"][seller_name].update(data.full_kizs)
                result["prices_by_seller"].setdefault(seller_name, {})
                result["prices_by_seller"][seller_name].update(data.prices)
                result["sellers_with_kiz"].add(seller_name)

                for full_kiz in data.full_kizs:
                    result["kiz_owners"].setdefault(full_kiz, []).append(
                        (seller_name, data.kiz_dates.get(full_kiz), 1)
                    )

                result["blocks"].append("\n".join([
                    f"Файл: {file_path.name}",
                    f"  Продавец: {seller_name}",
                    f"  Всего уникальных: {data.total_unique}",
                    f"  Добавлено: {data.added}",
                    f"  Отсеяно (товар не возвращён): "
                    f"{data.skipped_no_return + data.skipped_date_before_return}",
                    f"  Дубликаты в отчёте: {data.skipped_dup}",
                    f"  Цен собрано: {len(data.prices)}",
                ]))
            except Exception as e:
                logger.critical(
                    f"Ошибка обработки файла {file_path.name}: {e}",
                    can_influence=False,
                )
                result["missed"].append(
                    (file_path.name, "ошибка чтения")
                )
                continue

        if result["blocks"]:
            logger.info("\n" + "\n\n".join(result["blocks"]))
        return result

    def _read_ozon_reports(self, ctx, sellers, logger) -> dict:
        """Читает все «Отчёт_OZON_*.xlsx».

        Выход:
            Тот же формат, что _read_wb_reports, но prices_by_seller
            пуст — Ozon цены не собирает. Источник 2 в kiz_owners.
        """
        files = FileHelper.find_files_by_pattern(
            ctx.reports_dir, "Отчёт_OZON_*.xlsx",
        )
        result = {
            "added": 0,
            "blocks": [],
            "missed": [],
            "sellers_with_kiz": set(),
            "kiz_by_seller": {},
            "prices_by_seller": {},
            "kiz_owners": {},
        }

        for file_path in files:
            try:
                logger.status(f"Обработка отчёта Ozon: {file_path.name}")
                read_result = OZONReportReader.read(
                    report_path=file_path,
                    sellers=sellers,
                    kiz_validator=self.kiz_validator,
                    logger=logger,
                )
                if read_result.reason is not None:
                    result["missed"].append(
                        (file_path.name, read_result.reason)
                    )
                    continue
                data = read_result.data
                if data is None:
                    continue

                result["added"] += data.added
                seller_name = data.seller.name
                result["kiz_by_seller"].setdefault(seller_name, set())
                result["kiz_by_seller"][seller_name].update(data.full_kizs)

                for full_kiz in data.full_kizs:
                    result["kiz_owners"].setdefault(full_kiz, []).append(
                        (seller_name, data.kiz_dates.get(full_kiz), 2)
                    )

                result["blocks"].append("\n".join([
                    f"Файл: {file_path.name}",
                    f"  Продавец: {seller_name}",
                    f"  Всего уникальных: {data.total_unique}",
                    f"  Добавлено: {data.added}",
                    f"  Отсеяно (товар не возвращён): "
                    f"{data.skipped_no_return + data.skipped_date_before_return}",
                    f"  Дубликаты в отчёте: {data.skipped_dup}",
                ]))
            except Exception as e:
                logger.critical(
                    f"Ошибка обработки файла {file_path.name}: {e}",
                    can_influence=False,
                )
                result["missed"].append(
                    (file_path.name, "ошибка чтения")
                )
                continue

        if result["blocks"]:
            logger.info("\n" + "\n\n".join(result["blocks"]))
        return result

    @staticmethod
    def _merge_read_result(result, kiz_by_seller, prices_by_seller,
                           kiz_owners) -> None:
        """Мержит результат _read_*_reports в общие структуры.

        Вход:
            result — dict от _read_*_reports.
            kiz_by_seller, prices_by_seller, kiz_owners — общие
                структуры, мутируются на месте.
        """
        for seller_name, kiz_set in result["kiz_by_seller"].items():
            kiz_by_seller.setdefault(seller_name, set()).update(kiz_set)
        for seller_name, prices in result.get("prices_by_seller", {}).items():
            prices_by_seller.setdefault(seller_name, {}).update(prices)
        for kiz, owners in result["kiz_owners"].items():
            kiz_owners.setdefault(kiz, []).extend(owners)

    # ============================================================
    # Приватные методы: разрешение конфликтов
    # ============================================================

    def _resolve_kiz_conflicts(self, kiz_owners, kiz_by_seller, sellers,
                               logger) -> dict:
        """Разрешает конфликты КИЗов между продавцами.

        Вход:
            kiz_owners — {full_kiz: [(seller_name, date, src)]}.
            kiz_by_seller — {seller_name: set(full_kiz)}. Мутируется:
                у проигравшего КИЗ удаляется.
            sellers — список Seller.
            logger — LoggerV2.

        Выход:
            dict {"conflict_count", "per_seller_lost"}.

        Роль:
            Тело — точная копия прежнего блока конфликтов из
            ExportKizService.export. Никаких новых правил.
        """
        logger.status("Проверка дублей КИЗов между продавцами")
        conflict_count = 0
        per_seller_lost: dict = {}

        for kiz, owners in kiz_owners.items():
            if len(owners) <= 1:
                continue
            unique_sellers = {o[0] for o in owners}
            if len(unique_sellers) <= 1:
                continue
            winner = self._pick_winner(owners, sellers)
            if winner is None:
                continue
            conflict_count += 1
            winner_owner = next(o for o in owners if o[0] == winner)
            winner_date = (
                winner_owner[1] if winner_owner[1] else "дата неизвестна"
            )
            winner_label = self._SOURCE_LABELS.get(
                winner_owner[2], str(winner_owner[2])
            )
            for loser in unique_sellers:
                if loser == winner:
                    continue
                kiz_by_seller[loser].discard(kiz)
                per_seller_lost[loser] = per_seller_lost.get(loser, 0) + 1
                if winner_owner[2] == 0:
                    logger.report(
                        f"\nКИЗ {kiz}: у '{loser}' (не определяли) и "
                        f"'{winner}' ({winner_date}, src={winner_label}) "
                        f"→ оставлен у '{winner}'"
                    )
                else:
                    loser_owner = next(o for o in owners if o[0] == loser)
                    loser_date = (
                        loser_owner[1] if loser_owner[1]
                        else "дата неизвестна"
                    )
                    loser_label = self._SOURCE_LABELS.get(
                        loser_owner[2], str(loser_owner[2])
                    )
                    logger.report(
                        f"\nКИЗ {kiz}: у '{loser}' ({loser_date}, "
                        f"src={loser_label}) и '{winner}' "
                        f"({winner_date}, src={winner_label}) "
                        f"→ оставлен у '{winner}'"
                    )

        if conflict_count > 0:
            logger.warning(
                f"\nНайдено конфликтов КИЗов между продавцами: "
                f"{conflict_count}"
            )
            lines = ["\nКонфликты КИЗов между продавцами:"]
            lines.append(f"  Всего конфликтов: {conflict_count}")
            lines.append(f"  Продавцов затронуто: {len(per_seller_lost)}")
            if per_seller_lost:
                lines.append("")
                lines.append("  По продавцам (потеряно КИЗов):")
                for seller in sellers:
                    if seller.name in per_seller_lost:
                        lines.append(
                            f"    {seller.name}: "
                            f"{per_seller_lost[seller.name]}"
                        )
            logger.info("\n".join(lines))

        return {
            "conflict_count": conflict_count,
            "per_seller_lost": per_seller_lost,
        }

    @classmethod
    def _pick_winner(cls, owners, sellers):
        """Определяет продавца-победителя для конфликтного КИЗа.

        Вход:
            owners — list[tuple[seller_name: str, date_str: str | None,
                     source_priority: int]].
            sellers — list[Seller].

        Выход:
            str — имя продавца-победителя; None при пустом owners.

        Роль:
            Т6: ЧЗ МП (src=0) побеждает жёстко, без сравнения дат.
            Иначе — ключ (дата, -src, -index): позже > раньше,
            меньше src лучше, меньше индекс в sellers лучше.
        """
        if not owners:
            return None

        seller_names = [s.name for s in sellers]

        def seller_index(name):
            if name in seller_names:
                return seller_names.index(name)
            return len(seller_names)

        chz_owners = [o for o in owners if o[2] == 0]
        if chz_owners:
            winner_chz = min(
                chz_owners, key=lambda o: seller_index(o[0])
            )
            return winner_chz[0]

        def sort_key(owner):
            dt = DateParser.parse_any(
                owner[1], DateParser.KIZ_FORMATS
            )
            if dt is None:
                dt = datetime.min
            return (dt, -owner[2], -seller_index(owner[0]))

        return max(owners, key=sort_key)[0]

    # ============================================================
    # Приватные методы: финализация
    # ============================================================

    def _finalize_reports(self, ctx, logger, sellers, kiz_by_seller,
                          prices_by_seller, wb_sellers_with_kiz,
                          missed_files, wh_result, wb_result, ozon_result,
                          size_before, conflict_stats, detected,
                          stats) -> dict:
        """Сохранение цен, .txt, сводки, отчёт по базе.

        Вход:
            ctx — TaskContext.
            logger — LoggerV2.
            sellers — список Seller.
            kiz_by_seller — {seller_name: set(full_kiz)} после
                разрешения конфликтов.
            prices_by_seller — {seller_name: {storage_kiz: price}}.
            wb_sellers_with_kiz — set имён продавцов с WB-КИЗами.
            missed_files — list[(file_name, reason)].
            wh_result, wb_result, ozon_result — результаты чтения.
            size_before — размер базы до batch.
            conflict_stats — из _resolve_kiz_conflicts.
            detected — dict от _detect_all (для has_any_files).

        Выход:
            dict {"successful_txt": list, "total_prices": int}.
        """
        # 1. Сохранение цен.
        try:
            FbsBufferPrices(ctx.processing_dir).save(prices_by_seller)
            logger.report(
                f"  Цены сохранены в {FbsBufferPrices.FILENAME}"
            )
            total_prices = sum(
                len(p) for p in prices_by_seller.values()
            )
            if total_prices > 0:
                logger.status("Цены с отчётов WB сохранены")
                lines = ["\nСохранение цен из отчётов WB:"]
                for seller in sellers:
                    prices = prices_by_seller.get(seller.name) or {}
                    if prices:
                        lines.append(f"  {seller.name}: {len(prices)}")
                no_price_names = [
                    seller.name for seller in sellers
                    if seller.name in wb_sellers_with_kiz
                       and not prices_by_seller.get(seller.name)
                ]
                if no_price_names:
                    lines.append(
                        f"Без цен: {', '.join(no_price_names)}"
                    )
                logger.info("\n".join(lines))
            else:
                logger.status("Цены с отчётов WB не обнаружены")
        except (IOError, OSError) as e:
            logger.critical(
                f"Не удалось сохранить {FbsBufferPrices.FILENAME}: {e}",
                can_influence=False,
            )

        # 2. Запись .txt по продавцам.
        logger.report("\n--- СОХРАНЕНИЕ ТЕКСТОВЫХ ФАЙЛОВ ---")
        successful_txt: list = []
        for seller_name, kiz_set in kiz_by_seller.items():
            if not kiz_set:
                logger.status(
                    f"Нет КИЗов для продавца {seller_name}"
                )
                logger.report(
                    f"  {seller_name}: нет КИЗов – файл не создан"
                )
                continue
            txt_path = ctx.processing_dir / f"{seller_name}.txt"
            ok = TextFileWriter.write(
                txt_path, header=None, items=sorted(kiz_set),
                logger=logger,
            )
            if ok:
                logger.status(
                    f"Файл для обработки по продавцу {seller_name} готов"
                )
                successful_txt.append(txt_path.name)
            logger.report(
                f"  {seller_name}: сохранено {len(kiz_set)} КИЗов "
                f"в {txt_path.name}"
            )

        if successful_txt:
            lines = ["\nСозданы файлы для обработки:"]
            for name in successful_txt:
                lines.append(f"  {name}")
            logger.info("\n".join(lines))

        # 3. Пропущенные файлы.
        if missed_files:
            lines = ["\nПропущено файлов:"]
            for file_name, reason in missed_files:
                lines.append(f"  {file_name} ({reason})")
            logger.info("\n".join(lines))

        # 4. Продавцы без отчётов / сохранено КИЗов — только на непустом прогоне.
        has_any_files = bool(detected)
        if has_any_files:
            sellers_without_reports = [
                seller.name for seller in sellers
                if not kiz_by_seller.get(seller.name)
                   and not prices_by_seller.get(seller.name)
            ]
            if sellers_without_reports:
                logger.info(
                    "\nПродавцы без отчётов: "
                    + ", ".join(sellers_without_reports)
                )

            lines = ["\nСохранено КИЗов по продавцам:"]
            for seller in sellers:
                kiz_set = kiz_by_seller.get(seller.name) or set()
                if kiz_set:
                    lines.append(f"  {seller.name}: {len(kiz_set)}")
            logger.info("\n".join(lines))

        # 5. Сводка записи в базу КИЗов.
        size_after = len(self.kiz_validator.storage.get_all())
        info_lines = ["\nЗапись в базу КИЗов:"]
        info_lines.append(
            f"  Из отчётов со склада: {wh_result['added']}"
        )
        info_lines.append(f"  Из отчётов WB: {wb_result['added']}")
        info_lines.append(
            f"  Из отчётов Ozon: {ozon_result['added']}"
        )
        total_ops = (
            wh_result["added"] + wb_result["added"] + ozon_result["added"]
        )
        info_lines.append(f"  Всего операций записи: {total_ops}")
        if stats.get("copied_garbage", 0) > 0:
            info_lines.append(
                f"  Мусор (не скопировано): {stats['copied_garbage']}"
            )
        if stats.get("processed_returns", 0) > 0:
            info_lines.append(
                f"  Возвратов (в returns.txt): "
                f"{stats['processed_returns']}"
            )
        delta = size_after - size_before
        delta_str = f"{'+' if delta >= 0 else ''}{delta}"
        info_lines.append(
            f"База КИЗов: {size_before} → {size_after} ({delta_str})"
        )
        logger.info("\n".join(info_lines))

        logger.status(
            "Обработайте файлы в BestMark и переходите к следующему этапу"
        )
        logger.report("\n=== ВЫГРУЗКА ЗАВЕРШЕНА ===\n")

        return {
            "successful_txt": successful_txt,
            "total_prices": sum(
                len(p) for p in prices_by_seller.values()
            ),
        }

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
                      (см. SellsFBSWindow._current_sellers).

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
        logger.status("Сбор данных начат")
        logger.info(
            "\n==================== Этап: Сбор данных ====================\n"
        )
        logger.report("\n==================== Этап: Сбор данных ====================\n")
        logger.report(f"Рабочая папка: {ctx.work_folder}")
        logger.status("Загрузка базы КИЗов для валидации")
        try:
            self.kiz_validator.load()
            if self.kiz_validator.storage.get_all():
                logger.info(
                    "Загружены сохранённые данные по ранее "
                    "списанным КИЗам"
                )
            else:
                logger.info(
                    "Не получилось загрузить данные — валидация "
                    "без сохранённой базы"
                )
        except Exception:
            logger.info(
                "Не получилось загрузить данные — валидация "
                "без сохранённой базы"
            )

        allowed_companies = TextUtils.get_allowed_companies(sellers)
        files_found: int = 0
        files_not_found: int = 0
        files_not_opened: list = []
        sellers_without_files: list = []
        sellers_without_kiz: list = []
        total_rows_sum: int = 0
        total_kept_sum: int = 0
        total_removed_sum: int = 0
        status_counts_agg: dict = {}
        owner_counts_agg: dict = {}
        # ------------------------------------------------------------------
        # 1. Основной цикл: фильтрация строк в предитоговых файлах.
        # ------------------------------------------------------------------
        kiz_to_brand_data: dict = {}
        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                sellers_without_files.append(seller.name)
                files_not_found += 1
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue
            files_found += 1
            logger.status(f"Обработка файла: {file_path.name}")
            logger.report(f"Обработка файла: {file_path.name}")

            wb = WorkbookOpener.open(
                file_path, logger=logger,
                description="предитоговый файл", read_only=False,
            )
            if wb is None:
                files_not_opened.append(f"{seller.name}.xlsx")
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
                total_rows_sum += (
                        stats['total_kept'] + stats['total_removed']
                )
                total_kept_sum += stats['total_kept']
                total_removed_sum += stats['total_removed']


                for status_name, count in stats['status'].items():
                    status_counts_agg[status_name] = (
                            status_counts_agg.get(status_name, 0) + count
                    )
                for owner_name, count in stats['owner'].items():
                    owner_counts_agg[owner_name] = (
                            owner_counts_agg.get(owner_name, 0) + count
                    )

                if stats['total_kept'] == 0:
                    sellers_without_kiz.append(seller.name)
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
            logger.info(
                f"\nОбработка файла: {seller.name}.xlsx — "
                f"сохранено {stats['total_kept']} строк"
            )
        lines = ["\nФильтрация строк:"]
        lines.append(f"  Продавцов обработано: {len(sellers)}")
        lines.append(f"  Файлов найдено: {files_found}")
        lines.append(f"  Файлов не найдено: {files_not_found}")
        lines.append(f"  Всего строк: {total_rows_sum}")
        lines.append(f"  Оставлено: {total_kept_sum}")
        lines.append(
            f"  Удалено по статусу: {sum(status_counts_agg.values())}"
        )
        lines.append(
            f"  Удалено по владельцу: {sum(owner_counts_agg.values())}"
        )
        logger.info("\n".join(lines))

        #разбивка по статусам. Только при непустом agg.
        if status_counts_agg:
            lines = ["\nУдалено по статусам:"]
            for status_name in sorted(
                    status_counts_agg.keys(), key=lambda x: x.lower()
            ):
                lines.append(
                    f'  "{status_name}": {status_counts_agg[status_name]}'
                )
            logger.info("\n".join(lines))

        #разбивка по владельцам.
        empty_owner_count = owner_counts_agg.get("(пусто)", 0)
        other_owners = {
            k: v for k, v in owner_counts_agg.items() if k != "(пусто)"
        }
        if other_owners or empty_owner_count > 0:
            lines = ["\nУдалено по владельцам (не из списка продавцов):"]
            for owner_name in sorted(
                    other_owners.keys(), key=lambda x: x.lower()
            ):
                lines.append(f'  "{owner_name}": {other_owners[owner_name]}')
            if empty_owner_count > 0:
                lines.append(
                    f"  Без указания владельца: {empty_owner_count}"
                )
            logger.info("\n".join(lines))

        # два отдельных info для продавцов без файлов/КИЗов.
        if sellers_without_files:
            logger.info(
                f"\nПродавцы без файлов: "
                f"{', '.join(sellers_without_files)}"
            )
        if sellers_without_kiz:
            logger.info(
                f"\nПродавцы без КИЗов после фильтрации: "
                f"{', '.join(sellers_without_kiz)}"
            )

        # файлы, которые не открылись.
        if files_not_opened:
            logger.info(
                f"\nНе открылись файлы: {', '.join(files_not_opened)}"
            )

        # статус перед вторым циклом — только если sellers непуст.
        if sellers:
            logger.status("Сбор КИЗов из отфильтрованных файлов")

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

        # info-сводка — дополнительно, после report-блока.
        lines = ["\nСводка по фильтрации КИЗов:"]
        lines.append(
            f"  Всего уникальных КИЗов в предитоговых файлах: "
            f"{total_in_files}"
        )
        lines.append(
            f"  Из них есть в used_kiz.json: {stats['total']}"
        )
        lines.append(f"  С пустым брендом: {stats['empty_brand']}")
        lines.append(
            f"  С неизвестным брендом: {stats['unknown_brand']}"
        )
        lines.append(f"  Распознано брендов: {stats['recognized']}")
        lines.append(f"  сохранено: {stats['saved']}")
        lines.append(f"  удалено: {stats['deleted']}")
        logger.info("\n".join(lines))

        if brands_unknown:
            if self._brand_unknown_resolver is None:
                logger.warning(
                    f"\nUI-обработка неизвестных брендов недоступна: "
                    f"{len(brands_unknown)} ключей остаются "
                    f"неизвестными"
                )
            else:
                # NEW A.5: статус перед разрешением.
                logger.status("Запрос решений по неизвестным брендам")
                try:
                    result = self._brand_unknown_resolver(brands_unknown)
                except Exception as e:
                    logger.critical(
                        f"Ошибка обработки неизвестных брендов: {e}",
                        can_influence=False,
                    )
                    # NEW B.10: info о завершении с ошибкой.
                    logger.info(
                        "\nОбработка неизвестных брендов завершилась "
                        "ошибкой"
                    )
                else:
                    if isinstance(result, dict) and all(
                            key in result
                            for key in ("total", "resolved", "skipped")
                    ):
                        logger.info(
                            f"\nРазрешение неизвестных брендов: всего "
                            f"{result['total']}, разрешено "
                            f"{result['resolved']}, пропущено "
                            f"{result['skipped']}"
                        )
                    else:
                        logger.warning(
                            "Callback неизвестных брендов вернул "
                            "некорректный результат"
                        )
                        logger.info(
                            "\nОбработка неизвестных брендов вернула "
                            "некорректный результат"
                        )

        # ------------------------------------------------------------------
        # 5. Удаление из used_kiz.json — одним batch-контекстом.
        # ------------------------------------------------------------------
        if to_delete:
            X = len(used_kiz_keys)
            logger.status("Удаление записей из базы КИЗов")
            with self.kiz_validator.batch():
                deleted = self.kiz_validator.remove_kizs(to_delete)
            Y = X - deleted
            if deleted != len(to_delete):
                logger.warning(
                    f"remove_kizs: запрошено удалить {len(to_delete)}, "
                    f"реально удалено {deleted} – расхождение"
                )
            lines = [
                "\nБаза КИЗов:",
                f"  Было: {X}",
                f"  Стало: {Y}",
                f"  Удалено: {deleted}",
            ]
            logger.info("\n".join(lines))

        logger.report("\n=== ФИЛЬТРАЦИЯ ЗАВЕРШЕНА ===")

        #info-отбивка конца, 50 знаков =.
        logger.info("\n==================================================\n")

        # финальный статус этапа.
        logger.status(
            "Сбор данных завершён. Можете переходить к этапу "
            "формирования файлов продаж."
        )

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

        logger = self._log_manager_v2.create_logger_v2(
            source="GenerateSalesService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_продажи.txt",
        )
        logger.status("Формирование файлов продаж начато")

        logger.info(
            "\n==================== Этап: Продажи ====================\n"
        )
        logger.report("=== ФОРМИРОВАНИЕ ФАЙЛОВ ПРОДАЖ ===")
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)
        files_found = 0
        files_not_found = 0
        files_not_opened = 0
        files_empty = 0
        sellers_without_files = []
        own_kiz_count = 0
        invalid_rows_count = 0
        unknown_owner_count = 0

        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                # NEW A.2: файла нет — учёт.
                files_not_found += 1
                sellers_without_files.append(seller.name)
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

            files_found += 1
            logger.status(f"Обработка файла: {seller.name}.xlsx")
            logger.report(f"\nОбработка файла: {file_path.name}")
            wb = WorkbookOpener.open(
                file_path, logger=logger,
                description="предитоговый файл", read_only=True,
            )
            if wb is None:
                files_not_opened += 1
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    files_empty += 1
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
                        invalid_rows_count += 1
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
                        unknown_owner_count += 1
                        logger.report(
                            f"  Строка {row_idx}: владелец "
                            f"'{prefinal.owner_company}' не найден "
                            f"среди продавцов – пропущена"
                        )
                        continue

                    if owner_seller.name == seller.name:
                        own_kiz_count += 1
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

        lines = ["\nОбработка файлов продавцов:"]
        lines.append(f"  Продавцов обработано: {len(sellers)}")
        lines.append(f"  Файлов найдено: {files_found}")
        lines.append(f"  Файлов не найдено: {files_not_found}")
        lines.append(f"  Файлов не открылось: {files_not_opened}")
        lines.append(f"  Файлов пустых: {files_empty}")
        if sellers_without_files:
            lines.append(
                f"  Продавцов без файлов: "
                f"{', '.join(sellers_without_files)}"
            )
        logger.info("\n".join(lines))

        logger.info(
            f"\nСвои КИЗы (владелец = текущий продавец): {own_kiz_count}"
        )

        if invalid_rows_count > 0:
            logger.warning(
                f"\nНекорректных строк (нет КИЗа или владельца): "
                f"{invalid_rows_count}"
            )
        if unknown_owner_count > 0:
            logger.warning(
                f"\nСтрок с неизвестным владельцем: {unknown_owner_count}"
            )


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
        logger.status("Проверка дублей КИЗов")
        intra_file, inter_file = KizDuplicatesFinder.find(
            ctx.sales_dir, logger,
        )

        # 6.4 — intra-file дедупликация.
        intra_files_count = len(intra_file)
        intra_deleted_rows = 0
        logger.status("Удаление дублей внутри файлов")
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
                logger.status("UI-обработка дублей недоступна")
            else:
                logger.status("Обработка межфайловых дублей")
                for kiz, file_paths in inter_file.items():
                    file_to_receiver = {
                        p: (sales_gen.get_receiver_name(p) or p.name)
                        for p in file_paths
                    }
                    logger.status(f"Разрешение дубля: {kiz}")
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

        empty_removed_after = 0
        if intra_files_count > 0 or inter_count > 0:
            empty_removed_after = sales_gen.remove_empty_files()

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
        lines = ["\nДубли КИЗов:"]
        lines.append(
            f"  Внутрифайловых: {intra_files_count} файлов, "
            f"удалено {intra_deleted_rows} строк"
        )
        lines.append(f"  Межфайловых: {inter_count} КИЗов")
        lines.append(f"  Разрешено в пользу файла: {resolved_count}")
        lines.append(f"  Удалено вхождений: {removed_occurrences}")
        logger.info("\n".join(lines))

        logger.report("\n=== ФОРМИРОВАНИЕ ПРОДАЖ ЗАВЕРШЕНО ===")
        logger.info("\n==================================================\n")
        logger.status("Формирование файлов продаж завершено")

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
            kiz_validator — KizValidator: доступ к used_kiz.json
                            (load, clean_old_entries, batch).
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
        logger.status("Внесение цен и финализация начато")
        logger.info(
            "\n==================== Этап: Цены ====================\n"
        )
        logger.report("=== ВНЕСЕНИЕ ЦЕН И ФИНАЛИЗАЦИЯ ===")
        logger.report(f"Рабочая папка: {ctx.work_folder}")
        logger.status("Загрузка базы КИЗов для валидации")
        try:
            self.kiz_validator.load()
            if self.kiz_validator.storage.get_all():
                logger.info(
                    "Загружены сохранённые данные по ранее "
                    "списанным КИЗам"
                )
            else:
                logger.warning(
                    "\nНе получилось загрузить данные — валидация "
                    "без сохранённой базы"
                )
        except Exception:
            logger.warning(
                "\nНе получилось загрузить данные — валидация "
                "без сохранённой базы"
            )
        logger.status("Загрузка цен из отчётов WB")
        # Цены из отчётов читаем один раз — до цикла по продавцам.
        all_prices = self._load_prices_from_json(
            ctx.processing_dir, logger
        )
        if all_prices:
            logger.info(
                f"\nЦены из отчётов WB загружены: "
                f"{len(all_prices)} продавцов"
            )
        else:
            logger.info(
                "\nЦены из отчётов WB не обнаружены — средние "
                "будут взяты из сохранённых или запрошены"
            )

        sellers_processed = 0
        sellers_skipped_ready = 0
        sellers_skipped_no_file = 0
        sellers_skipped_no_requester = 0
        sellers_skipped_cancelled = 0
        sellers_with_error = 0
        sellers_without_files = []
        average_changes = {}  # {seller_name: (old, new)}
        cluster_totals = {}  # {seller_name: total_clusters}
        cluster_filled = {}  # {seller_name: filled_rows}
        total_clusters = 0
        total_processed = 0
        total_skipped_no_numeric = 0
        total_skipped_all_numeric = 0
        total_cluster_filled = 0
        per_seller_stage1 = {}  # {seller_name: stage1_count}
        per_seller_stage2 = {}  # {seller_name: stage2_stats.filled_rows}
        per_seller_stage3 = {}  # {seller_name: stage3_count}
        total_stage1 = 0
        total_stage2 = 0
        total_stage3 = 0

        for seller in sellers:
            price_map = all_prices.get(seller.name, {})
            prices_list = list(price_map.values())

            logger.report(f"\nОбработка продавца: {seller.name}")
            logger.status(f"Обработка продавца: {seller.name}")
            # ---- 1. Определяем среднюю через резолвер. ----
            decision = AveragePriceResolver.resolve(
                saved_prices, seller.name, prices_list
            )

            if decision.need_dialog:
                # Ни цен из отчёта, ни сохранённых цен вообще нет.
                if self._price_requester is None:
                    sellers_skipped_no_requester += 1
                    logger.warning(
                        f"Не могу запросить цену без UI-callback, "
                        f"пропускаю продавца '{seller.name}'"
                    )
                    continue
                logger.status(
                    f"Запрос цены для продавца: {seller.name}"
                )
                user_price = self._price_requester(seller.name)
                if user_price is None:
                    sellers_skipped_cancelled += 1
                    logger.report(
                        f"  Пользователь отменил ввод для продавца "
                        f"'{seller.name}' – пропускаем"
                    )
                    continue
                average_price = user_price
                old_price = saved_prices.get(seller.name)
                if old_price != average_price:
                    average_changes[seller.name] = (
                        old_price, average_price,
                    )
                saved_prices[seller.name] = average_price
                logger.report(
                    f"  Пользователь ввёл цену: {average_price}"
                )
            else:
                average_price = decision.price
                old_price = saved_prices.get(seller.name)
                if old_price != average_price:
                    average_changes[seller.name] = (
                        old_price, average_price,
                    )
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
                sellers_skipped_ready += 1
                logger.report(
                    f"ИТОГ {seller.name} уже создан и обработан "
                    f"ранее – пропускаем."
                )
                saved_prices[seller.name] = average_price
                continue

            # ---- 3. Предитоговый файл в «Обработке». ----
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                # NEW D: счётчик skip-no-file + сбор имён.
                sellers_skipped_no_file += 1
                sellers_without_files.append(seller.name)
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

            # ---- 4. Копирование в корень как ИТОГ. ----
            result = FileHelper.copy_file_with_log(
                file_path, new_path, logger,
                description="итоговый файл", overwrite=True,
            )
            if result["status"] != "copied":
                logger.warning(
                    f"\n{new_path.name}: не удалось скопировать "
                    f"({result['status']})"
                )
                continue
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
                per_seller_stage1[seller.name] = stage1_count
                total_stage1 += stage1_count
                logger.report(
                    f"  Установлено цен из отчёта: {stage1_count}"
                )
                logger.status(
                    f"Подстановка цен по GTIN для {seller.name}"
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
                cluster_totals[seller.name] = stage2_stats.total_clusters
                cluster_filled[seller.name] = stage2_stats.filled_rows
                total_clusters += stage2_stats.total_clusters
                total_processed += stage2_stats.processed
                total_skipped_no_numeric += stage2_stats.skipped_no_numeric
                total_skipped_all_numeric += stage2_stats.skipped_all_numeric
                total_cluster_filled += stage2_stats.filled_rows
                per_seller_stage2[seller.name] = stage2_stats.filled_rows
                # Этап 3 — генерация по средней.
                logger.status(
                    f"Генерация цен по средней для {seller.name}"
                )
                stage3_count = PriceFiller.fill_by_average(
                    sheet, average_price
                )
                per_seller_stage3[seller.name] = stage3_count
                total_stage3 += stage3_count
                logger.report(
                    f"  Сгенерировано цен по средней: {stage3_count}"
                )

                # ---- 6. Сохранение ИТОГа. ----
                wb.save(new_path)
                logger.report(
                    f"  Итоговый файл сохранён: {new_path.name}"
                )
                saved_prices[seller.name] = average_price
                sellers_processed += 1

            except Exception as e:
                # Ошибка обработки одного файла не должна валить
                # весь прогон — остальные продавцы продолжают.
                sellers_with_error += 1
                logger.critical(
                    f"Ошибка обработки файла {new_path.name}: {e}",
                    can_influence=False,
                )
            finally:
                try:
                    wb.close()
                except Exception:
                    pass

        lines = ["\nОбработка продавцов:"]
        lines.append(f"  Продавцов обработано: {sellers_processed}")
        lines.append(
            f"  Пропущено (ИТОГ уже готов): {sellers_skipped_ready}"
        )
        lines.append(
            f"  Пропущено (нет файла): {sellers_skipped_no_file}"
        )
        lines.append(
            f"  Пропущено (нет UI-callback): "
            f"{sellers_skipped_no_requester}"
        )
        lines.append(
            f"  Пропущено (отменено пользователем): "
            f"{sellers_skipped_cancelled}"
        )
        lines.append(f"  Обработано с ошибкой: {sellers_with_error}")
        if sellers_without_files:
            lines.append(
                f"  Продавцов без файлов: "
                f"{', '.join(sellers_without_files)}"
            )
        logger.info("\n".join(lines))

        # NEW B.5: изменения средних цен — только если были изменения.
        # old_display — str(old) если old is not None, иначе "—".
        if average_changes:
            lines = ["\nИзменения средних цен:"]
            for seller_name, (old, new) in average_changes.items():
                old_display = str(old) if old is not None else "—"
                lines.append(f"  {seller_name}: {old_display} → {new}")
            logger.info("\n".join(lines))

        # NEW B.6: расширенный отчёт по кластерам GTIN.
        lines = ["\nКластеры GTIN:"]
        # Блок «По продавцам» — только для продавцов, дошедших
        # до fill_by_gtin_clusters, с total_clusters > 0.
        per_seller_lines = []
        for seller in sellers:
            if seller.name not in cluster_totals:
                continue
            total_c = cluster_totals[seller.name]
            if total_c == 0:
                continue
            filled = cluster_filled.get(seller.name, 0)
            per_seller_lines.append(
                f"    {seller.name}: {total_c} кластеров, "
                f"{filled} цен"
            )
        if per_seller_lines:
            lines.append("  По продавцам:")
            lines.extend(per_seller_lines)
            lines.append("")
        lines.append(f"  Всего кластеров: {total_clusters}")
        lines.append(f"  Обработано (распределено): {total_processed}")
        lines.append(
            f"  Пропущено (нет числовых): {total_skipped_no_numeric}"
        )
        lines.append(
            f"  Пропущено (все числовые): {total_skipped_all_numeric}"
        )
        lines.append(f"  Установлено цен: {total_cluster_filled}")
        logger.info("\n".join(lines))

        # NEW B.7: расширенный отчёт о внесённых ценах.
        # total_stage2 не заполнялся отдельно — используем
        # total_cluster_filled как источник «По кластерам GTIN».
        total_stage2_effective = total_cluster_filled
        total_all = total_stage1 + total_stage2_effective + total_stage3
        pct1 = (
            round(total_stage1 * 100 / total_all) if total_all > 0 else 0
        )
        pct2 = (
            round(total_stage2_effective * 100 / total_all)
            if total_all > 0 else 0
        )
        pct3 = (
            round(total_stage3 * 100 / total_all) if total_all > 0 else 0
        )
        lines = ["\nУстановлено цен:"]
        lines.append(f"  Из отчёта: {total_stage1} ({pct1}%)")
        lines.append(
            f"  По кластерам GTIN: {total_stage2_effective} ({pct2}%)"
        )
        lines.append(f"  По средней: {total_stage3} ({pct3}%)")
        lines.append(f"  Всего: {total_all}")
        # Блок «По продавцам» — только для продавцов, дошедших
        # до wb.save (успешно завершённых), с total > 0.
        per_seller_lines = []
        for seller in sellers:
            s1 = per_seller_stage1.get(seller.name, 0)
            s2 = per_seller_stage2.get(seller.name, 0)
            s3 = per_seller_stage3.get(seller.name, 0)
            total_s = s1 + s2 + s3
            if total_s == 0:
                continue
            per_seller_lines.append(
                f"    {seller.name}: {total_s} "
                f"(отчёт {s1} / GTIN {s2} / средняя {s3})"
            )
        if per_seller_lines:
            lines.append("")
            lines.append("  По продавцам:")
            lines.extend(per_seller_lines)
        logger.info("\n".join(lines))

        logger.report("\n=== ФИНАЛИЗАЦИЯ ЗАВЕРШЕНА ===")

        # NEW B.8: info-отбивка конца, 50 знаков =.
        logger.info("\n==================================================\n")

        # NEW A.8: финальный статус этапа.
        logger.status(
            "Внесение цен и финализация завершены. "
            "Работа с отчётами завершена"
        )

        return saved_prices