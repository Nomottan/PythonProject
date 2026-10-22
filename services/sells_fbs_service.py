"""
Сервисы ЧЗ МП: подготовка, обработка файлов, финализация цен.

Содержит три сервиса пайплайна:
    PreparationService     — опознание, копирование, разбор склада,
                             чтение отчётов МП, разрешение конфликтов.
    FinalProcessingService — фильтрация предитоговых файлов и
                             формирование файлов продаж одним проходом,
                             разрешение дублей КИЗов.
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
from utils.sales_file_generator import (
    SalesFileGenerator, SalesDuplicatesResolver,
)
from utils.fbs_buferprices import FbsBufferPrices
from utils.kiz_utils import KizUtils
from services.kiz_validator import KizValidator

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

class DataVerificationService:
    """Необязательный сервис проверки.

    Сверяет КИЗы из отчётов с пулом КИЗов файла продавца (BestMark / ИТОГ).
    Режим (final / processing) определяется автоматически. Не пишет
    в used_kiz.json — работает через KizValidator(dry_run=True,
    ignore_existing=True).
    """

    def __init__(self, kiz_validator, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator: используется только для load().
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2

    def verify(self, target_dir, sellers) -> None:
        """Запускает проверку данных.

        Вход:
            target_dir — корень рабочей папки.
            sellers — список Seller с восстановленными .brands.
        """
        # ============================================================
        # Фаза 1. Контекст, логгер, загрузка базы.
        # ============================================================
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_проверка.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )
        logger = self._log_manager_v2.create_logger_v2(
            source="DataVerificationService.data_verification_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_проверка.txt",
        )
        logger.status("Проверка данных начата")
        logger.report("=== ПРОВЕРКА ДАННЫХ ===")
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

        validator = KizValidator(
            self.kiz_validator.storage,
            dry_run=True,
            ignore_existing=True,
        )

        # ============================================================
        # Фаза 2. Определение режима.
        # ============================================================
        intent_mode = "processing"
        for seller in sellers:
            final_name = f"ИТОГ {seller.name} {ctx.date_str}.xlsx"
            if (ctx.work_folder / final_name).is_file():
                intent_mode = "final"
                break

        logger.debug(
            f"verify: старт, sellers={len(sellers)}, mode={intent_mode}"
        )

        # ============================================================
        # Фаза 3. Этап 1 (только processing).
        # ============================================================
        if intent_mode == "final":
            logger.debug("verify: режим final, пропускаю этап 1")
        else:
            missing_names = set()
            for seller in sellers:
                txt_path = ctx.processing_dir / f"{seller.name}.txt"
                xlsx_path = ctx.processing_dir / f"{seller.name}.xlsx"

                if not txt_path.is_file() and xlsx_path.is_file():
                    logger.debug(
                        f"Этап 1: {seller.name} — txt нет, xlsx есть"
                    )
                elif txt_path.is_file() and xlsx_path.is_file():
                    logger.debug(
                        f"Этап 1: {seller.name} — оба файла есть"
                    )
                elif not txt_path.is_file() and not xlsx_path.is_file():
                    logger.debug(
                        f"Этап 1: {seller.name} — ни txt, ни xlsx"
                    )
                elif txt_path.is_file() and not xlsx_path.is_file():
                    missing_names.add(seller.name)

            if missing_names:
                logger.status("Не все txt файлы проведены через BestMark")
                for seller in sellers:
                    if seller.name in missing_names:
                        logger.report(
                            f" {seller.name}: txt есть, xlsx "
                            f"отсутствует — стоп"
                        )
                logger.report(
                    "Проверка прервана: не все txt проведены "
                    "через BestMark"
                )
                logger.info(
                    f"\nОбработанные файлы отсутствуют: "
                    f"{', '.join(sorted(missing_names))}. "
                    f"Проверка отменена."
                )
                return

        # ============================================================
        # Фаза 4. Основной проход.
        # ============================================================
        missing_reports: dict = {}
        no_expected_matches: dict = {}
        no_matched: dict = {}
        missing_seller_files: set = set()
        unreadable_reports: dict = {}
        checked_sellers = 0
        checked_reports = 0

        for seller in sellers:
            if intent_mode == "final":
                seller_path = (
                    ctx.work_folder
                    / f"ИТОГ {seller.name} {ctx.date_str}.xlsx"
                )
            else:
                seller_path = ctx.processing_dir / f"{seller.name}.xlsx"

            if not seller_path.is_file():
                logger.status(f"Пропуск {seller.name}: файла нет")
                logger.report(
                    f" {seller.name}: файла для проверки нет — пропуск"
                )
                missing_seller_files.add(seller.name)
                continue

            logger.status(f"Проверка {seller.name}")

            pool: set = set()
            wb = None
            try:
                wb = WorkbookOpener.open(
                    seller_path, logger=logger, read_only=True,
                    description="файл проверки",
                )
                if wb is None:
                    logger.critical(
                        f"Ошибка чтения файла продавца {seller.name}: "
                        f"не открылся",
                        can_influence=False,
                    )
                    missing_seller_files.add(seller.name)
                    continue

                sheet = wb.active
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if len(row) >= PriceFiller.KIZ_COL:
                        kiz_val = row[PriceFiller.KIZ_COL - 1]
                        if kiz_val is not None:
                            k_str = str(kiz_val).strip()
                            if k_str and k_str != PriceFiller.HEADER_KIZ:
                                pool.add(k_str)
            except Exception as e:
                logger.critical(
                    f"Ошибка чтения файла продавца {seller.name}: {e}",
                    can_influence=False,
                )
                missing_seller_files.add(seller.name)
                continue
            finally:
                if wb is not None:
                    try:
                        wb.close()
                    except Exception:
                        pass

            # Поиск отчётов.
            found_reports = []
            missing_platforms = []
            found_platforms = set()
            safe_seller = TextUtils.sanitize_filename(
                seller.name
            ).lower()

            for path in ctx.reports_dir.glob("Отчёт_*.xlsx"):
                if safe_seller not in path.stem.lower():
                    continue
                stem_upper = path.stem.upper()
                stem_lower = path.stem.lower()
                if "WB" in stem_upper:
                    found_reports.append(("WB", path))
                    found_platforms.add("WB")
                elif "OZON" in stem_upper:
                    found_reports.append(("OZON", path))
                    found_platforms.add("OZON")
                elif "склада" in stem_lower:
                    found_reports.append(("склада", path))
                    found_platforms.add("склада")

            for platform in ("WB", "OZON", "склада"):
                if platform not in found_platforms:
                    missing_platforms.append(platform)

            if missing_platforms:
                missing_reports[seller.name] = missing_platforms

            logger.debug(
                f"Проверка {seller.name}: пул КИЗов={len(pool)}, "
                f"отчётов={len(found_reports)}, "
                f"отсутствует площадок="
                f"{len(missing_reports.get(seller.name, []))}"
            )

            if found_reports:
                logger.report(f"\nПроверка отчётов {seller.name}:")

            for platform, path in found_reports:
                try:
                    if platform == "WB":
                        reader = WBReportReader
                    elif platform == "OZON":
                        reader = OZONReportReader
                    else:
                        reader = WarehouseReportReader

                    result = reader.read(path, sellers, validator, logger)

                    if result.reason is not None or result.data is None:
                        reason = result.reason or "не прочитан"
                        logger.report(f" Отчёт {path.name}: {reason}")
                        unreadable_reports.setdefault(
                            seller.name, []
                        ).append((path.name, reason))
                        continue

                    data = result.data
                    if data.added == 0:
                        logger.report(
                            f" Отчёт {path.name}: КИЗов к списанию "
                            f"нет — проверка вхождений не требуется"
                        )
                        no_expected_matches.setdefault(
                            seller.name, []
                        ).append(path.name)
                        continue

                    logger.debug(
                        f" Отчёт {path.name}: added={data.added}, "
                        f"проверено до 3 вхождений"
                    )
                    found = 0
                    for full_kiz in data.full_kizs:
                        storage = KizUtils.clean_kiz_for_storage(
                            full_kiz, logger=None,
                        )
                        if not storage:
                            continue
                        k = storage[0]
                        if k in pool:
                            pool.discard(k)
                            found += 1
                        if found >= 3:
                            break

                    if found == 3:
                        logger.report(
                            f" Отчёт {path.name}: 3 вхождения, "
                            f"признан полностью проверенным"
                        )
                    elif found == 2:
                        logger.report(
                            f" Отчёт {path.name}: 2 вхождения, "
                            f"признан относительно проверенным"
                        )
                    elif found == 1:
                        logger.report(
                            f" Отчёт {path.name}: 1 вхождение, "
                            f"признан сомнительно проверенным"
                        )
                    else:
                        logger.report(
                            f" Отчёт {path.name}: внимание, "
                            f"вхождений нет"
                        )
                        no_matched.setdefault(
                            seller.name, []
                        ).append(path.name)

                    checked_reports += 1
                except Exception as e:
                    logger.critical(
                        f"Ошибка чтения отчёта {path.name}: {e}",
                        can_influence=False,
                    )
                    unreadable_reports.setdefault(
                        seller.name, []
                    ).append((path.name, "ошибка чтения"))
                    continue

            checked_sellers += 1

        # ============================================================
        # Фаза 5. Пустой вход.
        # ============================================================
        if checked_sellers == 0:
            logger.status("Файлов для проверки нет")
            logger.report("Проверка завершена без данных")
            logger.info(
                "\nФайлов нет: либо были удалены, либо не требуются "
                "списывать КИЗы."
            )
            return

        # ============================================================
        # Фаза 6. Финальные info-блоки.
        # ============================================================
        logger.info("\n" + "=" * 60)

        if missing_reports:
            lines = ["Отсутствующие отчёты:"]
            for seller in sellers:
                if seller.name in missing_reports:
                    lines.append(f" Продавец {seller.name}:")
                    for platform in ("WB", "OZON", "склада"):
                        if platform in missing_reports[seller.name]:
                            safe_name = TextUtils.sanitize_filename(
                                seller.name
                            )
                            lines.append(
                                f" Отчёт_{platform}_{safe_name}_"
                                f"{ctx.date_str}.xlsx"
                            )
            logger.info("\n".join(lines))
            logger.info("")

        if no_expected_matches:
            lines = [
                "Отчёты в которых не должно было быть совпадений "
                "из-за отсутствия КИЗов к списанию:"
            ]
            for seller in sellers:
                if seller.name in no_expected_matches:
                    lines.append(f" Продавец {seller.name}:")
                    for report_name in no_expected_matches[seller.name]:
                        lines.append(f"    {report_name}")
            logger.info("\n".join(lines))
            logger.info("")

        if no_matched:
            lines = ["Отчёты в которых не было найдено совпадений:"]
            for seller in sellers:
                if seller.name in no_matched:
                    lines.append(f" Продавец {seller.name}:")
                    for report_name in no_matched[seller.name]:
                        lines.append(f"    {report_name}")
            logger.info("\n".join(lines))
            logger.info("")

        if missing_seller_files:
            lines = ["Продавцы без файла для проверки:"]
            for seller in sellers:
                if seller.name in missing_seller_files:
                    lines.append(f" {seller.name}")
            logger.info("\n".join(lines))
            logger.info("")

        if unreadable_reports:
            lines = ["Не прочитавшиеся отчёты:"]
            for seller in sellers:
                if seller.name in unreadable_reports:
                    lines.append(f" Продавец {seller.name}:")
                    for report_name, reason in unreadable_reports[seller.name]:
                        lines.append(f" {report_name} ({reason})")
            logger.info("\n".join(lines))
            logger.info("")

        logger.info("\n" + "=" * 60)

        # ============================================================
        # Фаза 7. Финал.
        # ============================================================
        logger.status("Проверка завершена")
        logger.report("\n=== ПРОВЕРКА ЗАВЕРШЕНА ===")
        logger.debug(
            f"verify: завершён, проверено продавцов={checked_sellers}, "
            f"отчётов={checked_reports}"
        )

class FinalProcessingService:
    """Сервис обработки предитоговых файлов и формирования продаж.

    Роль:
        Один проход по продавцам выполняет три задачи:
            1. Фильтрация строк (статус «В ОБОРОТЕ» + допустимый
               владелец) с перезаписью файла на месте.
            2. Сбор {kiz: (norm_brand, raw_brand)} из всех
               отфильтрованных файлов (первое вхождение).
            3. Формирование файлов продаж: для каждой строки, где
               владелец ≠ текущий продавец, add_sale_row.
        Затем — удаление записей из used_kiz.json по брендам
        requires_saving=False, разрешение дублей КИЗов в папке
        «Продажи», сводка.

    Публичный API:
        completion(target_dir, sellers).
    """

    def __init__(self, kiz_validator, log_manager_v2,
                 brand_unknown_resolver=None,
                 duplicate_keeper_resolver=None,
                 price_requester=None) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator (load, batch, remove_kizs).
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
            brand_unknown_resolver — Callable[[dict], dict] | None.
                Callback UI-разрешения неизвестных брендов.
            duplicate_keeper_resolver — Callable[[str, dict[Path, str]],
                Path | None] | None. Callback UI-выбора файла-получателя.
            price_requester — опциональный callable(seller_name) -> int | None.
                Вызывается, когда нужно спросить цену у пользователя.
                Обязан выполняться в UI-потоке и возвращать либо
                int-цену, либо None при отмене.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2
        self._brand_unknown_resolver = brand_unknown_resolver
        self._duplicate_keeper_resolver = duplicate_keeper_resolver
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

    def completion(self, target_dir, sellers, saved_prices=None) -> dict:
        """Обработка файлов и формирование продаж с установкой цен.

        Вход:
            target_dir — корень рабочей папки.
            sellers — список Seller с восстановленными .brands.
            saved_prices — dict {seller_name: средняя}, может быть пуст.

        Выход:
            Обновлённый saved_prices (та же ссылка, что и входная,
            если она была передана).
        """
        if saved_prices is None:
            saved_prices = {}

        # ============================================================
        # Фаза 1. Контекст, логгер, загрузка базы и цен.
        # ============================================================
        ctx = TaskContext(
            target_dir,
            "ЧЗ_МП_{date}",
            "log_обработка.txt",
            subfolders=["Логи", "Отчёты", "Обработка", "Продажи"],
        )
        logger = self._log_manager_v2.create_logger_v2(
            source="FinalProcessingService.sells_fbs_service",
            domain="chz_mp",
            work_folder=ctx.logs_dir,
            log_filename="log_обработка.txt",
        )
        logger.debug(
            f"completion: старт, sellers={len(sellers)}, "
            f"saved_prices={len(saved_prices)}"
        )
        logger.status("Обработка файлов начата")
        logger.report("=== ОБРАБОТКА ФАЙЛОВ ===")
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

        logger.status("Загрузка цен из отчётов WB")
        all_prices = self._load_prices_from_json(ctx.processing_dir, logger)
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

        allowed_companies = TextUtils.get_allowed_companies(sellers)
        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)

        # ============================================================
        # Фаза 2. Единый цикл по продавцам с предзаполнением цен.
        # ============================================================
        kiz_to_brand_data: dict = {}
        status_counts_agg: dict = {}
        owner_counts_agg: dict = {}
        files_found = 0
        files_not_found = 0
        files_not_opened = 0
        files_empty = 0
        sellers_without_files: list = []
        sellers_without_kiz: list = []
        total_rows_sum = 0
        total_kept_sum = 0
        own_kiz_count = 0
        invalid_rows_count = 0
        unknown_owner_count = 0
        sale_row_errors = 0
        per_receiver_created: dict = {}
        per_receiver_inn: dict = {}
        per_seller_stage1: dict = {}
        total_stage1 = 0

        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                files_not_found += 1
                sellers_without_files.append(seller.name)
                logger.report(
                    f"Файл для продавца '{seller.name}' "
                    f"не найден – пропущен"
                )
                continue

            files_found += 1
            logger.status(f"Обработка файла: {file_path.name}")
            logger.report(
                f"Обработка КИЗов файла продавца: {seller.name}"
            )

            price_map = all_prices.get(seller.name, {})

            wb = WorkbookOpener.open(
                file_path, logger=logger,
                description="предитоговый файл", read_only=False,
            )
            if wb is None:
                files_not_opened += 1
                continue

            filtered_rows = []
            filter_stats = {
                "status": {}, "owner": {},
                "total_kept": 0, "total_removed": 0,
            }
            headers: list = []
            original_sheet_title = ""

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    files_empty += 1
                    logger.report(
                        " Файл пуст (только заголовки) – пропущен"
                    )
                    continue

                original_sheet_title = sheet.title
                headers = [cell.value for cell in sheet[1]]

                filtered_rows, filter_stats = (
                    ExcelHelper.filter_and_clean_rows(
                        sheet,
                        status_col=4,
                        owner_col=12,
                        allowed_owners=allowed_companies,
                        required_status="В ОБОРОТЕ",
                    )
                )
                total_rows_sum += (
                    filter_stats['total_kept']
                    + filter_stats['total_removed']
                )
                total_kept_sum += filter_stats['total_kept']

                for status_name, count in filter_stats['status'].items():
                    status_counts_agg[status_name] = (
                        status_counts_agg.get(status_name, 0) + count
                    )
                for owner_name, count in filter_stats['owner'].items():
                    owner_counts_agg[owner_name] = (
                        owner_counts_agg.get(owner_name, 0) + count
                    )

                if filter_stats['total_kept'] == 0:
                    sellers_without_kiz.append(seller.name)
                logger.report(
                    f" Всего строк: {sheet.max_row - 1}"
                )
                if filter_stats['status']:
                    logger.report(" Удалено по статусу:")
                    for status, count in sorted(
                        filter_stats['status'].items(),
                        key=lambda x: x[0].lower(),
                    ):
                        logger.report(
                            f"   Статус '{status}': {count} строк"
                        )
                if filter_stats['owner']:
                    logger.report(" Удалено по владельцу:")
                    for owner, count in sorted(
                        filter_stats['owner'].items(),
                        key=lambda x: x[0].lower(),
                    ):
                        logger.report(
                            f"   Владелец '{owner}': {count} строк"
                        )
                logger.report(
                    f" Сохранено: {filter_stats['total_kept']} строк"
                )
                if filter_stats['total_kept'] == 0:
                    logger.report(
                        " Нет строк для сохранения – файл будет "
                        "очищен (только заголовки)"
                    )
            finally:
                wb.close()

            rows_for_write = []
            for _, values in filtered_rows:
                new_values = list(values)
                kiz = ""
                if len(new_values) >= PriceFiller.KIZ_COL:
                    raw_kiz = new_values[PriceFiller.KIZ_COL - 1]
                    kiz = str(raw_kiz).strip() if raw_kiz is not None else ""
                if kiz and kiz != PriceFiller.HEADER_KIZ and kiz in price_map:
                    if len(new_values) < PriceFiller.PRICE_COL:
                        new_values.extend(
                            [None] * (PriceFiller.PRICE_COL - len(new_values))
                        )
                    new_values[PriceFiller.PRICE_COL - 1] = price_map[kiz]
                    per_seller_stage1[seller.name] = (
                        per_seller_stage1.get(seller.name, 0) + 1
                    )
                    total_stage1 += 1
                rows_for_write.append(new_values)

            WorkbookWriter.overwrite(
                file_path, headers, rows_for_write,
                sheet_name=original_sheet_title, logger=logger,
            )
            if per_seller_stage1.get(seller.name, 0) > 0:
                logger.report(
                    f" Установлено цен из отчёта: "
                    f"{per_seller_stage1[seller.name]}"
                )
            logger.info(
                f"\nОбработка КИЗов файла: {seller.name}.xlsx — "
                f"сохранено {filter_stats['total_kept']} строк"
            )

            for row_idx, values in filtered_rows:
                parsed = PreFinalRow.from_row(values)
                if parsed is None:
                    invalid_rows_count += 1
                    logger.report(
                        f" Строка {row_idx}: некорректные данные "
                        f"(нет КИЗа или владельца) – пропущена"
                    )
                    continue

                if parsed.kiz not in kiz_to_brand_data:
                    kiz_to_brand_data[parsed.kiz] = (
                        TextUtils.normalize(parsed.brand),
                        parsed.brand,
                    )

                owner_seller = TextUtils.find_seller_by_company(
                    parsed.owner_company, sellers
                )
                if owner_seller is None:
                    unknown_owner_count += 1
                    logger.report(
                        f" Строка {row_idx}: владелец "
                        f"'{parsed.owner_company}' не найден "
                        f"среди продавцов – пропущена"
                    )
                    continue

                if owner_seller.name == seller.name:
                    own_kiz_count += 1
                    continue

                try:
                    sales_gen.add_sale_row(
                        from_seller_name=owner_seller.name,
                        to_seller_name=seller.name,
                        to_seller_inn=seller.inn,
                        product_name=parsed.product_name,
                        raw_kiz=parsed.kiz,
                        owner_company=parsed.owner_company,
                        brand=parsed.brand,
                    )
                except Exception as e:
                    sale_row_errors += 1
                    logger.warning(
                        f" Строка {row_idx}: ошибка записи "
                        f"продажи ({e}) – пропущена"
                    )
                    continue

                per_receiver_created.setdefault(seller.name, {})
                per_receiver_created[seller.name][owner_seller.name] = (
                    per_receiver_created[seller.name]
                    .get(owner_seller.name, 0) + 1
                )
                per_receiver_inn[seller.name] = seller.inn

        # Info-сводка по обработке файлов.
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
        if sale_row_errors > 0:
            logger.warning(
                f"\nОшибок записи продаж: {sale_row_errors}"
            )

        if sellers_without_kiz:
            logger.info(
                f"\nПродавцы без КИЗов после фильтрации: "
                f"{', '.join(sellers_without_kiz)}"
            )

        # ============================================================
        # Фаза 3. Фильтрация по брендам.
        # ============================================================
        used_kiz_keys = set(
            self.kiz_validator.storage.get_all().keys()
        )
        intersection = {
            k: v for k, v in kiz_to_brand_data.items()
            if k in used_kiz_keys
        }

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

        logger.report("\n=== СВОДКА ПО ФИЛЬТРАЦИИ КИЗОВ ===")
        logger.report(
            f"Всего уникальных КИЗов в предитоговых файлах "
            f"после фильтрации: {total_in_files}"
        )
        logger.report(
            f"Из них есть в used_kiz.json: {stats['total']}"
        )
        logger.report(f"С пустым брендом: {stats['empty_brand']}")
        logger.report(
            f"С неизвестным брендом: {stats['unknown_brand']}"
        )
        logger.report(
            f"Распознано уникальных брендов: "
            f"{stats['unique_recognized']}"
        )
        logger.report(
            f"requires_saving=True → сохранено: {stats['saved']}"
        )
        logger.report(
            f"requires_saving=False → удалено: {stats['deleted']}"
        )

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
        lines.append(
            f"  Распознано уникальных брендов: "
            f"{stats['unique_recognized']}"
        )
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
                logger.status("Запрос решений по неизвестным брендам")
                try:
                    result = self._brand_unknown_resolver(
                        brands_unknown,
                    )
                except Exception as e:
                    logger.critical(
                        f"Ошибка обработки неизвестных брендов: {e}",
                        can_influence=False,
                    )
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

        if status_counts_agg:
            lines = ["\nУдалено по статусам:"]
            for status_name in sorted(
                status_counts_agg.keys(), key=lambda x: x.lower()
            ):
                lines.append(
                    f'  "{status_name}": '
                    f"{status_counts_agg[status_name]}"
                )
            logger.info("\n".join(lines))

        empty_owner_count = owner_counts_agg.get("(пусто)", 0)
        other_owners = {
            k: v for k, v in owner_counts_agg.items()
            if k != "(пусто)"
        }
        if other_owners or empty_owner_count > 0:
            lines = ["\nУдалено по владельцам (не из списка продавцов):"]
            for owner_name in sorted(
                other_owners.keys(), key=lambda x: x.lower()
            ):
                lines.append(
                    f'  "{owner_name}": {other_owners[owner_name]}'
                )
            if empty_owner_count > 0:
                lines.append(
                    f"  Без указания владельца: {empty_owner_count}"
                )
            logger.info("\n".join(lines))

        # ============================================================
        # Фаза 4. Дубли.
        # ============================================================
        logger.report("\n--- ПРОВЕРКА ДУБЛЕЙ КИЗОВ ---")
        logger.status("Проверка дублей КИЗов")
        dup_stats = SalesDuplicatesResolver.resolve(
            ctx.sales_dir, sales_gen,
            self._duplicate_keeper_resolver, logger,
        )
        lines = ["\nДубли КИЗов:"]
        lines.append(
            f"  Внутрифайловых: {dup_stats['intra_files']} файлов, "
            f"удалено {dup_stats['intra_deleted_rows']} строк"
        )
        lines.append(
            f"  Межфайловых: {dup_stats['inter_count']} КИЗов"
        )
        lines.append(
            f"  Разрешено в пользу файла: {dup_stats['resolved']}"
        )
        lines.append(
            f"  Удалено вхождений: {dup_stats['removed_occurrences']}"
        )
        logger.info("\n".join(lines))

        # ============================================================
        # Фаза 5. Сводка «Созданы файлы продаж».
        # ============================================================
        lines: list = []
        for seller in sellers:
            to_name = seller.name
            per_from = per_receiver_created.get(to_name)
            if not per_from:
                continue
            inn = per_receiver_inn.get(to_name, "")
            lines.append(f" Для {to_name}:")
            for from_name, count in per_from.items():
                lines.append(
                    f" {from_name} - {to_name} _ {inn}: {count} КИЗов"
                )
        if lines:
            lines.insert(0, "\nСозданы файлы продаж:")
            logger.info("\n".join(lines))

        # ============================================================
        # Фаза 6. Установка цен и финализация.
        # ============================================================
        logger.status("Установка цен и финализация")
        logger.report("=== ВНЕСЕНИЕ ЦЕН И ФИНАЛИЗАЦИЯ ===")
        logger.debug(f"Фаза 6: старт, all_prices={len(all_prices)}")

        sellers_processed = 0
        sellers_skipped_ready = 0
        sellers_skipped_no_file = 0
        sellers_skipped_no_requester = 0
        sellers_skipped_cancelled = 0
        sellers_with_error = 0
        sellers_without_files = []
        average_changes = {}
        per_seller_filled_rows = {}
        per_seller_stage3 = {}
        per_seller_gtins_in_prices = {}
        per_seller_unique_gtins_filled = {}
        total_stage3 = 0
        total_gtins_in_prices = 0
        total_filled_rows = 0
        total_unique_gtins_filled = 0
        total_skipped_already_priced = 0
        total_skipped_no_gtin = 0
        total_skipped_not_in_prices = 0
        total_unique_gtins_not_in_prices = 0

        for seller in sellers:
            price_map = all_prices.get(seller.name, {})
            prices_list = list(price_map.values())

            new_name = FilenameUtils.format_with_extension(
                f"ИТОГ {seller.name} {{date}}", ctx.date_str
            )
            new_path = ctx.work_folder / new_name

            logger.report(f"\nУстановка цен в файле продавца: {seller.name}")
            logger.status(f"Установка цен: {new_path.name}")

            decision = AveragePriceResolver.resolve(
                saved_prices, seller.name, prices_list
            )

            if decision.need_dialog:
                if self._price_requester is None:
                    sellers_skipped_no_requester += 1
                    logger.warning(
                        f"Не могу запросить цену без UI-callback, "
                        f"пропускаю продавца '{seller.name}'"
                    )
                    continue
                logger.status(f"Запрос цены для продавца: {seller.name}")
                user_price = self._price_requester(seller.name)
                if user_price is None:
                    sellers_skipped_cancelled += 1
                    logger.report(
                        f" Пользователь отменил ввод для продавца "
                        f"'{seller.name}' – пропускаем"
                    )
                    continue
                average_price = user_price
                old_price = saved_prices.get(seller.name)
                if old_price != average_price:
                    average_changes[seller.name] = (old_price, average_price)
                saved_prices[seller.name] = average_price
                logger.report(f" Пользователь ввёл цену: {average_price}")
            else:
                average_price = decision.price
                old_price = saved_prices.get(seller.name)
                if old_price != average_price:
                    average_changes[seller.name] = (old_price, average_price)
                if prices_list:
                    logger.report(
                        f" Загружено {len(prices_list)} цен из отчёта, "
                        f"средняя: {average_price}"
                    )
                elif saved_prices.get(seller.name):
                    logger.report(
                        f" Использую сохранённую цену: {average_price}"
                    )
                else:
                    logger.report(
                        f" Использую случайную среднюю с другого "
                        f"продавца: {average_price}"
                    )

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

            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                sellers_skipped_no_file += 1
                sellers_without_files.append(seller.name)
                logger.report(
                    f"Файл для продавца '{seller.name}' не найден – пропущен"
                )
                continue

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
                        " Файл пуст (только заголовки) – пропущен"
                    )
                    continue

                stage1_count = per_seller_stage1.get(seller.name, 0)

                logger.status(f"Подстановка цен по GTIN для {seller.name}")
                stage2_stats = PriceFiller.fill_by_gtin_clusters(
                    sheet, price_map, logger=logger,
                )
                if stage2_stats.total_gtins_in_prices:
                    logger.report(
                        f" GTIN в ценах: "
                        f"{stage2_stats.total_gtins_in_prices}"
                    )
                if stage2_stats.skipped_already_priced:
                    logger.report(
                        f" Пропущено (цена уже стоит): "
                        f"{stage2_stats.skipped_already_priced}"
                    )
                if stage2_stats.skipped_no_gtin:
                    logger.report(
                        f" Пропущено (нет GTIN): "
                        f"{stage2_stats.skipped_no_gtin}"
                    )
                if stage2_stats.skipped_not_in_prices:
                    logger.report(
                        f" Пропущено (GTIN нет в ценах): "
                        f"{stage2_stats.skipped_not_in_prices} строк, "
                        f"{stage2_stats.unique_gtins_not_in_prices} "
                        f"уникальных"
                    )
                if stage2_stats.filled_rows:
                    logger.report(
                        f" Установлено цен по GTIN: "
                        f"{stage2_stats.filled_rows} строк, "
                        f"{stage2_stats.unique_gtins_filled} уникальных "
                        f"GTIN"
                    )
                per_seller_filled_rows[seller.name] = (
                    stage2_stats.filled_rows
                )
                per_seller_gtins_in_prices[seller.name] = (
                    stage2_stats.total_gtins_in_prices
                )
                per_seller_unique_gtins_filled[seller.name] = (
                    stage2_stats.unique_gtins_filled
                )
                total_gtins_in_prices += (
                    stage2_stats.total_gtins_in_prices
                )
                total_filled_rows += stage2_stats.filled_rows
                total_unique_gtins_filled += (
                    stage2_stats.unique_gtins_filled
                )
                total_skipped_already_priced += (
                    stage2_stats.skipped_already_priced
                )
                total_skipped_no_gtin += stage2_stats.skipped_no_gtin
                total_skipped_not_in_prices += (
                    stage2_stats.skipped_not_in_prices
                )
                total_unique_gtins_not_in_prices += (
                    stage2_stats.unique_gtins_not_in_prices
                )

                logger.status(f"Генерация цен по средней для {seller.name}")
                stage3_count = PriceFiller.fill_by_average(
                    sheet, average_price
                )
                per_seller_stage3[seller.name] = stage3_count
                total_stage3 += stage3_count
                logger.report(
                    f" Сгенерировано цен по средней: {stage3_count}"
                )

                wb.save(new_path)
                logger.report(
                    f" Итоговый файл сохранён: {new_path.name}"
                )
                saved_prices[seller.name] = average_price
                sellers_processed += 1

            except Exception as e:
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

        if average_changes:
            lines = ["\nИзменения средних цен:"]
            for seller_name, (old, new) in average_changes.items():
                old_display = str(old) if old is not None else "—"
                lines.append(f"  {seller_name}: {old_display} → {new}")
            logger.info("\n".join(lines))

        lines = ["\nGTIN-заполнение:"]
        per_seller_lines = []
        for seller in sellers:
            filled = per_seller_filled_rows.get(seller.name, 0)
            total_g = per_seller_gtins_in_prices.get(seller.name, 0)
            if filled == 0 and total_g == 0:
                continue
            unique_filled = per_seller_unique_gtins_filled.get(
                seller.name, 0,
            )
            per_seller_lines.append(
                f"    {seller.name}: {total_g} GTIN в ценах, "
                f"{filled} строк / {unique_filled} GTIN установлено"
            )

        has_any = bool(per_seller_lines) or (
                total_gtins_in_prices > 0
                or total_skipped_already_priced > 0
                or total_skipped_no_gtin > 0
                or total_skipped_not_in_prices > 0
                or total_filled_rows > 0
        )

        if has_any:
            if per_seller_lines:
                lines.append("  По продавцам:")
                lines.extend(per_seller_lines)
            if total_gtins_in_prices > 0:
                lines.append(
                    f"  Всего GTIN в ценах: {total_gtins_in_prices}"
                )
            if total_skipped_already_priced > 0:
                lines.append(
                    f"  Пропущено (цена уже стоит): "
                    f"{total_skipped_already_priced}"
                )
            if total_skipped_no_gtin > 0:
                lines.append(
                    f"  Пропущено (нет GTIN): "
                    f"{total_skipped_no_gtin}"
                )
            if total_skipped_not_in_prices > 0:
                lines.append(
                    f"  Пропущено (GTIN нет в ценах): "
                    f"{total_skipped_not_in_prices} строк, "
                    f"{total_unique_gtins_not_in_prices} уникальных"
                )
            if total_filled_rows > 0:
                lines.append(
                    f"  Установлено цен по GTIN: "
                    f"{total_filled_rows} строк, "
                    f"{total_unique_gtins_filled} уникальных GTIN"
                )
            logger.info("\n".join(lines))

        total_stage2_effective = total_filled_rows
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
        per_seller_lines = []
        for seller in sellers:
            s1 = per_seller_stage1.get(seller.name, 0)
            s2 = per_seller_filled_rows.get(seller.name, 0)
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
        logger.status(
            "Внесение цен и финализация завершены. "
            "Работа с отчётами завершена"
        )
        logger.debug(
            f"Фаза 6: завершена, sellers_processed={sellers_processed}"
        )

        # ============================================================
        # Фаза 7. Финал.
        # ============================================================
        logger.report("\n=== ОБРАБОТКА ЗАВЕРШЕНА ===")
        logger.status("Обработка завершена")
        logger.info("\n==================================================\n")
        logger.debug(
            f"completion: завершён, обработано={sellers_processed}, "
            f"возврат saved_prices({len(saved_prices)})"
        )
        return saved_prices
