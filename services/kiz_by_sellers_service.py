"""
Сервис распределения BestMark-файла по продавцам-владельцам.

Тонкий оркестратор: читает строки BestMark-файла, для каждой
строки определяет владельца через TextUtils.find_seller_by_company,
пишет файл продаж через SalesFileGenerator, копирует исходник
в Отчёты/, ведёт log_распределение_кизов.txt и
log_kiz_processing.txt.

Роль в программе:
    Вызывается из KizBySellersDialog в фоновом потоке.
    Продавцы передаются в конструкторе — диалог берёт их из
    родительского окна.
"""

from pathlib import Path

from utils.context import TaskContext
from utils.file_helper import FileHelper
from utils.excel_helper import WorkbookOpener
from utils.text_utils import TextUtils
from utils.kiz_utils import KizUtils
from utils.parsers import PreFinalRow
from utils.sales_file_generator import SalesFileGenerator

class KizBySellersService:
    """Тонкий оркестратор распределения BestMark-файла по продавцам.

    Роль:
        Читает строки BestMark-файла через PreFinalRow.from_row,
        для каждой строки определяет владельца через
        TextUtils.find_seller_by_company, пишет файл продаж через
        SalesFileGenerator, копирует исходник в Отчёты/, ведёт
        log_распределение_кизов.txt и log_kiz_processing.txt.

    Публичный API:
        distribute(target_dir, source_file, seller) -> dict.
    """

    def __init__(self, log_manager_v2, sellers) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.
            sellers — список Seller, используется для
                      TextUtils.find_seller_by_company.

        Роль: сохраняет ссылки. Логгеры создаются в distribute.
        """
        self._log_manager_v2 = log_manager_v2
        self._sellers = sellers

    def distribute(self, target_dir: str, source_file: str,
                   seller) -> dict:
        """Распределяет BestMark-файл по продавцам-владельцам.

        Вход:
            target_dir — корневая папка задачи.
            source_file — путь к исходному BestMark-файлу.
            seller — продавец-получатель (владелец продаж).
                     Должен иметь заполненный inn.

        Выход:
            dict со статусом:
                {"status": "ok", "rows_read": int, "kiz_written": int,
                 "files_created": int, "skipped": int,
                 "skip_reasons": dict}
                {"status": "error", "error": "no_inn", "seller_name": str}
                {"status": "error", "error": "copy_failed"}
                {"status": "error", "error": "open_failed"}

        Роль:
            Единая точка обработки файла: копирует исходник,
            открывает копию, читает строки через PreFinalRow,
            определяет владельца каждой строки, пишет файлы продаж,
            ведёт детальный лог.
        """
        ctx = TaskContext(
            target_dir,
            "Продажи_{date}",
            "log_распределение_кизов.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )
        logger = self._log_manager_v2.create_logger_v2(
            source="KizBySellersService.kiz_by_sellers_service",
            domain="sales",
            work_folder=ctx.logs_dir,
            log_filename="log_распределение_кизов.txt",
        )
        processing_logger = self._log_manager_v2.create_logger_v2(
            source="KizBySellersService.kiz_processing",
            domain="sales",
            work_folder=ctx.logs_dir,
            log_filename="log_kiz_processing.txt",
        )
        logger.debug(
            f"KizBySellersService.distribute: старт, "
            f"source={Path(source_file).name}, "
            f"seller={seller.name}"
        )
        logger.debug(
            f"KizBySellersService.distribute: ctx.sales_dir="
            f"{ctx.sales_dir}"
        )
        logger.status("Распределение КИЗов начато")
        logger.report("=== РАСПРЕДЕЛЕНИЕ КИЗОВ ===")

        # A5 / W2(a): проверка ИНН получателя.
        if not seller.inn:
            logger.critical(
                f"У продавца '{seller.name}' не задан ИНН — "
                f"распределение остановлено",
                can_influence=False,
            )
            logger.status("Распределение КИЗов прервано")
            return {
                "status": "error",
                "error": "no_inn",
                "seller_name": seller.name,
            }

        # W3=b: копия исходника в Отчёты/.
        copy_name = (
            f"Кизы для {TextUtils.sanitize_filename(seller.name)} "
            f"_{ctx.date_str}.xlsx"
        )
        copy_path = ctx.reports_dir / copy_name
        copy_result = FileHelper.copy_file_with_log(
            source_file, copy_path, logger,
            description="исходный BestMark-файл", overwrite=True,
        )
        if copy_result["status"] != "copied":
            logger.critical(
                f"Не удалось скопировать исходник: "
                f"{copy_result['status']}",
                can_influence=False,
            )
            return {"status": "error", "error": "copy_failed"}

        logger.status(f"Чтение файла {Path(source_file).name}")

        wb = WorkbookOpener.open(
            copy_path, logger=logger,
            description="BestMark-файл", read_only=True,
        )
        if wb is None:
            logger.critical(
                f"Файл не открылся: {copy_path.name}",
                can_influence=False,
            )
            return {"status": "error", "error": "open_failed"}

        logger.report(f"Найден лист: {wb.active.title}")
        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)
        rows_read = 0
        kiz_written = 0
        skipped = 0
        skip_reasons: dict = {}

        try:
            sheet = wb.active
            if sheet.max_row < 2:
                logger.warning(f"\n{source_file}: строк нет")
                logger.status("Распределение КИЗов завершено")
                return {
                    "status": "ok",
                    "rows_read": 0,
                    "kiz_written": 0,
                    "files_created": 0,
                    "skipped": 0,
                }

            logger.status("Запись файлов продаж")

            for row_idx, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True),
                start=2,
            ):
                rows_read += 1
                if row_idx % 100 == 0:
                    logger.report(f" Обработано строк: {row_idx}")

                prefinal = PreFinalRow.from_row(row)
                if prefinal is None:
                    processing_logger.report(
                        f"(нет КИЗа) | строка {row_idx} | "
                        f"пропуск: некорректные данные"
                    )
                    skipped += 1
                    skip_reasons["invalid"] = (
                        skip_reasons.get("invalid", 0) + 1
                    )
                    continue

                storage_list = KizUtils.clean_kiz_for_storage(
                    prefinal.kiz, logger=logger,
                )
                if not storage_list:
                    logger.warning(
                        f"\nСтрока {row_idx}: КИЗ не привёлся к 31 "
                        f"символу ({prefinal.kiz[:30]}...)"
                    )
                    processing_logger.report(
                        f"({prefinal.kiz[:30]}...) | строка {row_idx} | "
                        f"пропуск: КИЗ не 31 символов"
                    )
                    skipped += 1
                    skip_reasons["bad_kiz"] = (
                        skip_reasons.get("bad_kiz", 0) + 1
                    )
                    continue

                owner_seller = TextUtils.find_seller_by_company(
                    prefinal.owner_company, self._sellers,
                )
                if owner_seller is None:
                    logger.warning(
                        f"\nСтрока {row_idx}: владелец "
                        f"'{prefinal.owner_company}' не найден "
                        f"среди продавцов"
                    )
                    processing_logger.report(
                        f"{storage_list[0]} | владелец: "
                        f"{prefinal.owner_company!r} | пропуск: "
                        f"владелец не найден"
                    )
                    skipped += 1
                    skip_reasons["unknown_owner"] = (
                        skip_reasons.get("unknown_owner", 0) + 1
                    )
                    continue

                if owner_seller.name == seller.name:
                    processing_logger.report(
                        f"{storage_list[0]} | владелец: "
                        f"{prefinal.owner_company!r} | пропуск: "
                        f"владелец = получатель"
                    )
                    skipped += 1
                    skip_reasons["own_kiz"] = (
                        skip_reasons.get("own_kiz", 0) + 1
                    )
                    continue

                try:
                    file_path = sales_gen.add_sale_row(
                        from_seller_name=owner_seller.name,
                        to_seller_name=seller.name,
                        to_seller_inn=seller.inn,
                        product_name=prefinal.product_name,
                        raw_kiz=prefinal.kiz,
                    )
                except ValueError as e:
                    logger.warning(
                        f"\nСтрока {row_idx}: add_sale_row: {e}"
                    )
                    skipped += 1
                    skip_reasons["add_failed"] = (
                        skip_reasons.get("add_failed", 0) + 1
                    )
                    continue
                except RuntimeError as e:
                    logger.critical(
                        f"Ошибка записи в файл продаж: {e}",
                        can_influence=False,
                    )
                    skipped += 1
                    skip_reasons["write_error"] = (
                        skip_reasons.get("write_error", 0) + 1
                    )
                    continue

                kiz_written += len(storage_list)
                for kiz in storage_list:
                    processing_logger.report(
                        f"{kiz} | владелец: "
                        f"{prefinal.owner_company!r} | → "
                        f"{file_path.name}"
                    )
        finally:
            try:
                wb.close()
            except Exception:
                pass

        removed = sales_gen.remove_empty_files()
        if removed > 0:
            logger.report(f" Удалено пустых файлов: {removed}")

        created = sales_gen.get_created_files()
        logger.report(f"Файлов продаж создано: {len(created)}")

        lines = ["\nРаспределение КИЗов:"]
        lines.append(f"  Источник: {Path(source_file).name}")
        lines.append(f"  Продавец: {seller.name}")
        lines.append(f"  Прочитано строк: {rows_read}")
        lines.append(f"  Записано КИЗов: {kiz_written}")
        lines.append(f"  Создано файлов: {len(created)}")
        lines.append(f"  Удалено пустых: {removed}")
        lines.append(f"  Пропущено строк: {skipped}")
        lines.append(f"  Папка: {ctx.sales_dir}")
        logger.info("\n".join(lines))

        logger.status("Распределение КИЗов завершено")
        logger.report("\n=== РАСПРЕДЕЛЕНИЕ ЗАВЕРШЕНО ===")
        logger.debug("KizBySellersService.distribute: выход")

        return {
            "status": "ok",
            "rows_read": rows_read,
            "kiz_written": kiz_written,
            "files_created": len(created),
            "skipped": skipped,
            "skip_reasons": skip_reasons,
        }