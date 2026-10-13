"""
Сервис аккумуляции файлов продаж из двух папок в одну общую.

Работает с новым форматом файлов продаж:
  - Имя: "{от_кого} - {кому} : {ИНН}.xlsx" (содержит " - " и " _ ").
  - Столбцы: Наименование продукта, КИЗ (31 символ), GTIN, Цена.

Приоритет отдаётся файлам из ЧЗ_МП (Sells_FBS):
  - если КИЗ присутствует в ЧЗ_МП, то строки из Возвратов с этим
    КИЗом игнорируются.

Роль в программе:
    Тонкий оркестратор. Находит файлы через FileHelper, читает
    КИЗы через SalesFileKizReader, копирует и фильтрует строки
    через ExcelHelper, пишет детальный лог через
    KizFilterDetailsWriter. Логгер V2 создаётся в начале
    accumulate.

    Вызывается из ChzMPWindow/ReturnsWindow по кнопке «Собрать
    продажи» через ThreadFactory.run_in_thread.
"""

import traceback
from pathlib import Path

from utils.context import TaskContext
from utils.file_helper import FileHelper
from utils.excel_helper import ExcelHelper, WorkbookWriter
from utils.sales_file_generator import (
    SalesFileKizReader, SalesFileRowsReader, KizFilterDetailsWriter,
)

class SalesAccumulatorService:
    """Сервис аккумуляции продаж.

    Роль:
        Копирует файлы продаж из ЧЗ_МП и Возвратов в общую папку
        «Продажи_{date}». Файлы из ЧЗ_МП имеют приоритет: если КИЗ
        уже есть в ЧЗ_МП, строки из Возвратов с этим КИЗом
        отбрасываются.

    Публичный API:
        accumulate(target_dir).
    """

    def __init__(self, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.

        Роль: сохраняет ссылку. Логгеры создаются в начале
              accumulate, когда известна рабочая папка.
        """
        self._log_manager_v2 = log_manager_v2

    def accumulate(self, target_dir: str) -> None:
        """Аккумулирует файлы продаж из всех источников в одну папку.

        Вход: target_dir — корневая папка задачи.
        Выход: нет.

        Роль:
            Создаёт TaskContext (только пути) и два LoggerV2 (основной
            log_аккумуляция.txt и processing log_kiz_processing.txt).
            Определяет источники через _collect_sources, обрабатывает
            каждый через _process_source. Первый источник копируется
            целиком, остальные фильтруются по пулу КИЗов.
            Ошибка на источнике не прерывает прогон — critical и
            continue.
        """
        ctx = TaskContext(
            target_dir,
            "Продажи_{date}",
            "log_аккумуляция.txt",
            subfolders=["Логи", "Продажи"],
        )
        logger = self._log_manager_v2.create_logger_v2(
            source="SalesAccumulatorService.sales_accumulator",
            domain="sales",
            work_folder=ctx.logs_dir,
            log_filename="log_аккумуляция.txt",
        )
        processing_logger = self._log_manager_v2.create_logger_v2(
            source="SalesAccumulatorService.kiz_processing",
            domain="sales",
            work_folder=ctx.logs_dir,
            log_filename="log_kiz_processing.txt",
        )
        logger.status("Обнаружение источников продаж")

        base_path = Path(target_dir) / ctx.date_str
        sources = self._collect_sources(base_path, ctx.date_str, logger)

        if not sources:
            logger.warning("\nИсточники продаж не найдены")
            logger.status("Аккумуляция завершена")
            return

        lines = ["\nНайденные источники продаж:"]
        for source_folder, source_name, priority in sources:
            lines.append(
                f"  {source_folder.name} ({source_name}, "
                f"приоритет {priority})"
            )
        logger.info("\n".join(lines))

        sales_folder = ctx.work_folder
        logger.report("=== АККУМУЛЯЦИЯ ПРОДАЖ (приоритет ЧЗ_МП) ===")
        logger.report(f"Рабочая папка: {sales_folder}")

        kiz_pool: set = set()
        details = {"kiz_from_fbs": kiz_pool, "files": []}

        total_copied = 0
        total_appended = 0
        total_skipped = 0
        total_duplicates = 0
        per_source_stats: list = []

        for idx, (source_folder, source_name, _priority) in enumerate(sources):
            is_first = (idx == 0)
            logger.status(f"Обработка источника: {source_folder.name}")
            try:
                stats = self._process_source(
                    source_folder, sales_folder, kiz_pool, is_first,
                    source_name, logger, processing_logger, details,
                )
            except Exception as e:
                logger.critical(
                    f"Ошибка обработки источника "
                    f"{source_folder.name}: {e}",
                    can_influence=False,
                )
                logger.debug(f"Traceback: {traceback.format_exc()}")
                continue
            logger.debug(
                f"_process_source {source_name}: "
                f"kiz_pool = {len(kiz_pool)}"
            )
            total_copied += stats["files_copied"]
            total_appended += stats["files_appended"]
            total_skipped += stats["files_skipped"]
            total_duplicates += stats.get("kiz_duplicates", 0)
            per_source_stats.append((source_folder.name, stats))

        if details["files"]:
            KizFilterDetailsWriter.write(
                details, ctx.logs_dir, self._log_manager_v2,
            )
            logger.report(
                "  Детальный лог фильтрации КИЗов сохранён в "
                "log_фильтрация_КИЗов.txt"
            )

        lines = ["\nАккумуляция продаж:"]
        lines.append(
            f"  Источников обработано: {len(per_source_stats)}"
        )
        for folder_name, stats in per_source_stats:
            lines.append(
                f"  {folder_name}: найдено {stats['files_found']}, "
                f"скопировано {stats['files_copied']}, "
                f"дополнено {stats['files_appended']}, "
                f"пропущено {stats['files_skipped']}, "
                f"КИЗов добавлено {stats['kiz_added_to_pool']}"
            )
        lines.append(
            f"  Итого: скопировано {total_copied}, "
            f"дополнено {total_appended}, пропущено {total_skipped}"
        )
        lines.append(f"  Всего КИЗов в пуле: {len(kiz_pool)}")
        lines.append(f"  Всего дублей отброшено: {total_duplicates}")
        logger.info("\n".join(lines))

        logger.status("Аккумуляция завершена")
        logger.report("\n=== АККУМУЛЯЦИЯ ЗАВЕРШЕНА ===")

    def _collect_sources(self, base_path, date_str, logger) -> list:
        """Находит источники продаж в рабочей папке.

        Вход:
            base_path — Path к папке с подпапками источников.
            date_str — строка даты "D_M_YYYY" для распознавания
                       ЧЗ_МП_{date} и Возвраты_{date}.
            logger — LoggerV2.

        Выход:
            list[tuple[Path, str, int]] — [(папка_источника,
            короткое_имя, priority), ...]. Порядок: по priority (asc),
            внутри priority 2 — по имени папки (asc). Пустой список,
            если base_path не папка или ни одна подпапка не содержит
            «Продажи».

        Роль:
            Определяет, из каких подпапок собирать файлы продаж.
            ЧЗ_МП_{date} — priority 0, Возвраты_{date} — 1,
            остальные — 2. Единая точка отбора источников.
        """
        if not base_path.is_dir():
            logger.warning("\nРабочая папка не найдена")
            return []

        subdirs = [p for p in base_path.iterdir() if p.is_dir()]

        chz_name = f"ЧЗ_МП_{date_str}"
        returns_name = f"Возвраты_{date_str}"
        if not (base_path / chz_name).is_dir():
            logger.warning("\nПапка ЧЗ_МП не найдена")
        if not (base_path / returns_name).is_dir():
            logger.warning("\nПапка Возвраты не найдена")

        sources = []
        for p in subdirs:
            if not (p / "Продажи").is_dir():
                logger.warning(
                    f"\n{p.name}: подпапка 'Продажи' отсутствует "
                    f"— пропущено"
                )
                continue
            if p.name == chz_name:
                sources.append((p, "ЧЗ_МП", 0))
            elif p.name == returns_name:
                sources.append((p, "Возвраты", 1))
            else:
                sources.append((p, p.name, 2))

        sources.sort(key=lambda t: (t[2], t[0].name))
        return sources

    # ---------- Приватные методы-оркестраторы ----------

    def _process_source(self, source_folder, sales_folder, kiz_pool,
                        is_first, source_name, logger,
                        processing_logger, details) -> dict:
        """Обрабатывает один источник продаж.

        Вход:
            source_folder — Path к папке источника (внутри — «Продажи»).
            sales_folder — Path к целевой папке аккумуляции.
            kiz_pool — set[str], общий пул КИЗов (мутируется in-place).
            is_first — True для первого источника: файлы копируются
                       целиком; False: фильтруются по kiz_pool.
            source_name — короткое имя источника.
            logger — LoggerV2 основного журнала.
            processing_logger — LoggerV2 журнала обработки КИЗов.
            details — dict {"kiz_from_fbs": set, "files": []} для
                      KizFilterDetailsWriter — мутируется in-place.

        Выход:
            dict {"files_found", "files_copied", "files_appended",
                  "files_skipped", "kiz_added_to_pool",
                  "kiz_duplicates"}.

        Роль:
            Единая обработка источника. Устойчив к отсутствию
            папки-источника, подпапки «Продажи» и пустой «Продажи» —
            warning и нулевой результат. Ошибка на отдельном файле
            не прерывает источник: critical + continue.
        """
        source_label = source_folder.name
        zeros = {
            "files_found": 0,
            "files_copied": 0,
            "files_appended": 0,
            "files_skipped": 0,
            "kiz_added_to_pool": 0,
            "kiz_duplicates": 0,
        }

        if not source_folder.is_dir():
            logger.warning(
                f"\n{source_name}: папка источника не найдена: "
                f"{source_folder}"
            )
            return zeros

        sales_subfolder = source_folder / "Продажи"
        if not sales_subfolder.is_dir():
            logger.warning(
                f"\n{source_name}: подпапка 'Продажи' отсутствует "
                f"— пропущено"
            )
            return zeros

        files = FileHelper.find_sales_files(sales_subfolder)
        logger.report(
            f"Источник {source_label}: найдено файлов {len(files)}"
        )
        if not files:
            logger.warning(f"{source_name}: файлов продаж не найдено")
            return zeros

        files_copied = 0
        files_appended = 0
        files_skipped = 0
        kiz_added = 0
        kiz_duplicates = 0

        for src_path in files:
            logger.status(f"Обработка файла: {src_path.name}")
            try:
                dst_path = sales_folder / src_path.name
                src_kiz_set = SalesFileKizReader.read(src_path)
                logger.report(
                    f"  Файл: {src_path.name}, "
                    f"КИЗов в файле: {len(src_kiz_set)}"
                )

                if not src_kiz_set:
                    logger.report(
                        f"  {src_path.name}: пусто — пропущен"
                    )
                    details["files"].append({
                        "name": src_path.name,
                        "source_name": source_name,
                        "total": 0,
                        "duplicates": set(),
                        "filtered": set(),
                    })
                    files_skipped += 1
                    continue

                if is_first:
                    result = FileHelper.copy_file_with_log(
                        src_path, dst_path, logger,
                        description="файл продаж", overwrite=True,
                    )
                    if result["status"] == "copied":
                        kiz_pool.update(src_kiz_set)
                        files_copied += 1
                        kiz_added += len(src_kiz_set)
                        logger.report(
                            f"  Скопирован: {src_path.name} "
                            f"(КИЗов: {len(src_kiz_set)})"
                        )
                        details["files"].append({
                            "name": src_path.name,
                            "source_name": source_name,
                            "total": len(src_kiz_set),
                            "duplicates": set(),
                            "filtered": src_kiz_set,
                        })
                        for kiz in sorted(src_kiz_set):
                            processing_logger.report(
                                f"{kiz} | источник: {source_name} | "
                                f"→ скопирован в {dst_path.name}"
                            )
                    else:
                        files_skipped += 1
                        logger.report(
                            f"  Не скопирован {src_path.name}: "
                            f"{result['status']}"
                        )
                    continue

                duplicates = src_kiz_set & kiz_pool
                filtered = src_kiz_set - kiz_pool
                kiz_duplicates += len(duplicates)
                details["files"].append({
                    "name": src_path.name,
                    "source_name": source_name,
                    "total": len(src_kiz_set),
                    "duplicates": duplicates,
                    "filtered": filtered,
                })

                if not filtered:
                    files_skipped += 1
                    logger.report(
                        f"  Пропущен {src_path.name}: все КИЗы уже "
                        f"в пуле (всего {len(src_kiz_set)}, "
                        f"дублей {len(duplicates)})"
                    )
                    for kiz in sorted(duplicates):
                        processing_logger.report(
                            f"{kiz} | источник: {source_name} | "
                            f"пропуск: уже есть в пуле"
                        )
                    continue

                header, filtered_rows = SalesFileRowsReader.read_filtered(
                    src_path,
                    SalesFileKizReader.KIZ_COLUMN_INDEX,
                    filtered,
                    logger=None,
                )

                if dst_path.exists():
                    WorkbookWriter.append_rows(
                        dst_path, filtered_rows, logger=logger,
                    )
                    files_appended += 1
                    action = "Дополнен"
                else:
                    WorkbookWriter.create(
                        dst_path, header, filtered_rows,
                        sheet_name="Продажи", logger=logger,
                    )
                    files_copied += 1
                    action = "Создан"

                kiz_pool.update(filtered)
                kiz_added += len(filtered)
                logger.report(
                    f"  {action} {dst_path.name}: добавлено "
                    f"{len(filtered_rows)} строк"
                )
                for kiz in sorted(filtered):
                    processing_logger.report(
                        f"{kiz} | источник: {source_name} | → "
                        f"{dst_path.name}"
                    )
                for kiz in sorted(duplicates):
                    processing_logger.report(
                        f"{kiz} | источник: {source_name} | "
                        f"пропуск: уже есть в пуле"
                    )
            except Exception as e:
                logger.critical(
                    f"Ошибка обработки {src_path.name}: {e}",
                    can_influence=False,
                )
                logger.debug(f"Traceback: {traceback.format_exc()}")
                files_skipped += 1
                continue

        logger.report(
            f"Источник {source_label}: файлов {len(files)} "
            f"(скопировано {files_copied}, дополнено {files_appended}, "
            f"пропущено {files_skipped}), "
            f"КИЗов добавлено {kiz_added}, дублей {kiz_duplicates}"
        )
        logger.debug(
            f"_process_source {source_name}: выход, "
            f"kiz_pool = {len(kiz_pool)}"
        )

        return {
            "files_found": len(files),
            "files_copied": files_copied,
            "files_appended": files_appended,
            "files_skipped": files_skipped,
            "kiz_added_to_pool": kiz_added,
            "kiz_duplicates": kiz_duplicates,
        }
