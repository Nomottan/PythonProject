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
from utils.file_helper import FileHelper, FilenameUtils
from utils.excel_helper import (
    ExcelHelper, WorkbookWriter, WorkbookOpener,
)
from utils.sales_file_generator import (
    SalesFileKizReader, SalesFileRowsReader, KizFilterDetailsWriter,
    SalesFileGenerator,
)
from utils.kiz_utils import KizUtils
from utils.parsers import PreFinalRow
from utils.text_utils import TextUtils
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

    def accumulate(self, target_dir: str, sellers=None) -> None:
        """Аккумулирует файлы продаж из всех источников в одну папку.

        Вход:
            target_dir — корневая папка задачи.
            sellers — список Seller. None → []. Нужен для этапа
                      сверки аккумулированных продаж с ИТОГ-файлами
                      ЧЗ_МП: без него _verify_against_itogs не
                      сможет разобрать имена файлов продаж.

        Выход: нет.

        Роль:
            Создаёт TaskContext (только пути) и два LoggerV2 (основной
            log_аккумуляция.txt и processing log_kiz_processing.txt).
            Определяет источники через _collect_sources, обрабатывает
            каждый через _process_source. Первый источник копируется
            целиком, остальные фильтруются по пулу КИЗов.
            Ошибка на источнике не прерывает прогон — critical и
            continue.
            После аккумуляции — сверка с ИТОГ-файлами ЧЗ_МП
            (_verify_against_itogs), если папка ЧЗ_МП существует.
        """
        if sellers is None:
            sellers = []

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

        # ---- Сверка аккумулированных продаж с ИТОГ-файлами ЧЗ_МП ----
        verify_stats = None
        chz_folder = base_path / f"ЧЗ_МП_{ctx.date_str}"
        if not chz_folder.is_dir():
            logger.info(
                "ЧЗ_МП не найдена — сверка с ИТОГ-файлами "
                "не требуется"
                )
        else:
            verify_stats = self._verify_against_itogs(
                chz_folder, sales_folder, sellers,
                ctx.date_str, logger,
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
        if verify_stats is not None:
            lines = ["\nПроверка против ИТОГ-файлов:"]
            lines.append(
                f"  ИТОГ-файлов найдено: {verify_stats['itogs_found']}"
            )
            lines.append(
                f"  Файлов продаж проверено: "
                f"{verify_stats['sales_checked']}"
            )
            lines.append(
                f"  КИЗов проверено: {verify_stats['kiz_checked']}"
            )
            lines.append(
                f"  Удалено (ИТОГ у отправителя): "
                f"{verify_stats['kiz_removed']}"
            )
            lines.append(
                f"  Переоформлено (ИТОГ у третьего): "
                f"{verify_stats['kiz_reregistered']}"
            )
            lines.append(
                f"  Пустых файлов удалено: "
                f"{verify_stats['empty_files_removed']}"
            )
            if verify_stats["per_seller_removed"]:
                lines.append("  Потери по продавцам:")
                for seller in sellers:
                    if seller.name in verify_stats["per_seller_removed"]:
                        lines.append(
                            f"    {seller.name}: "
                            f"{verify_stats['per_seller_removed'][seller.name]}"
                        )
            if verify_stats["per_seller_added"]:
                lines.append("  Получено по продавцам:")
                for seller in sellers:
                    if seller.name in verify_stats["per_seller_added"]:
                        lines.append(
                            f"    {seller.name}: "
                            f"{verify_stats['per_seller_added'][seller.name]}"
                        )
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

    def _verify_against_itogs(self, chz_folder, sales_folder,
                              sellers, date_str, logger) -> dict:
        """Сверка аккумулированных продаж с ИТОГ-файлами продавцов.

        Вход:
            chz_folder — Path к папке ЧЗ_МП_{date} — источник
                         ИТОГ-файлов.
            sales_folder — Path к папке «Продажи_{date}» — файлы
                           продаж, где сверяем КИЗы.
            sellers — список Seller — нужен для разбора имён
                      файлов продаж и для переоформлений.
            date_str — строка даты для сборки имени ИТОГ-файла
                       через FilenameUtils.
            logger — LoggerV2.

        Выход:
            verify_stats — dict со счётчиками и per-seller
            агрегатами (8 ключей).

        Роль:
            Для КИЗа из файла A → B ищет ИТОГ-файл, в котором КИЗ
            встречается, короткозамкнуто: B → A → остальные
            (алфавит). X == B — оставить; X == A — удалить из
            A → B; X — третий — удалить из A → B, переоформить
            в A → X.
            Порядок применения: переоформления → удаления →
            удаление опустевших файлов.
        """
        verify_stats = {
            "itogs_found": 0,
            "sales_checked": 0,
            "kiz_checked": 0,
            "kiz_removed": 0,
            "kiz_reregistered": 0,
            "empty_files_removed": 0,
            "per_seller_removed": {},
            "per_seller_added": {},
        }
        logger.status("Проверка КИЗов против ИТОГ-файлов")
        logger.debug(
            f"_verify_against_itogs: вход, sellers={len(sellers)}, "
            f"sales_folder={sales_folder}"
        )

        itog_cache: dict = {}
        to_remove: dict = {}  # {file_path: set[storage_kiz]}
        to_reregister: list = []  # [{"from_seller": str,
        #   "to_seller": Seller,
        #   "kiz": str,
        #   "product_name": str}]

        sales_files = FileHelper.find_files_by_pattern(
            sales_folder, "*.xlsx",
        )

        for file_path in sales_files:
            parsed_names = TextUtils.parse_sales_filename(
                file_path.name, sellers,
            )
            if parsed_names is None:
                logger.warning(
                    f"Файл продаж {file_path.name}: имя не распознано "
                    f"— пропущен"
                )
                continue
            from_seller, to_seller = parsed_names
            A = from_seller.name
            B = to_seller.name

            logger.status(f"Сверка: {file_path.name}")

            wb = WorkbookOpener.open(
                file_path, logger=logger, read_only=True,
                description="файл продаж",
            )
            if wb is None:
                logger.warning(
                    f"Файл продаж {file_path.name} не открылся"
                )
                continue

            # Читаем sales_data = {kiz: product_name} из файла продаж.
            sales_data: dict = {}
            try:
                sheet = wb.active
                kiz_col = SalesFileKizReader.KIZ_COLUMN_INDEX
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if len(row) <= kiz_col:
                        continue
                    raw_kiz = row[kiz_col]
                    if not raw_kiz:
                        continue
                    storage_list = KizUtils.clean_kiz_for_storage(
                        raw_kiz, logger=None,
                    )
                    if not storage_list:
                        continue
                    k = storage_list[0]
                    product_name = row[0] if row else ""
                    sales_data[k] = product_name
            finally:
                try:
                    wb.close()
                except Exception:
                    pass

            if not sales_data:
                continue

            verify_stats["sales_checked"] += 1
            verify_stats["kiz_checked"] += len(sales_data)
            file_matched_total = 0
            remaining = set(sales_data.keys())

            # Шаг 1. B — оставить (только вычитаем из remaining).
            itog_b = self._load_itog_set(
                chz_folder, B, date_str, itog_cache, logger,
            )
            if itog_b:
                remaining -= (remaining & itog_b)

            # Шаг 2. A — удалить.
            itog_a = self._load_itog_set(
                chz_folder, A, date_str, itog_cache, logger,
            )
            if itog_a:
                matched_a = remaining & itog_a
                if matched_a:
                    to_remove.setdefault(file_path, set()).update(
                        matched_a
                    )
                    remaining -= matched_a
                    verify_stats["kiz_removed"] += len(matched_a)
                    verify_stats["per_seller_removed"][A] = (
                            verify_stats["per_seller_removed"].get(A, 0)
                            + len(matched_a)
                    )
                    file_matched_total += len(matched_a)
                    for k in sorted(matched_a):
                        logger.report(
                            f"КИЗ {k}: удалён из {A} → {B} "
                            f"(ИТОГ у {A})"
                        )

            # Шаг 3. Остальные — удалить + переоформить.
            other_names = sorted(
                s.name for s in sellers if s.name not in (A, B)
            )
            for X in other_names:
                if not remaining:
                    break
                itog_x = self._load_itog_set(
                    chz_folder, X, date_str, itog_cache, logger,
                )
                if not itog_x:
                    continue
                matched_x = remaining & itog_x
                if not matched_x:
                    continue
                to_remove.setdefault(file_path, set()).update(
                    matched_x
                )
                to_seller_obj = next(
                    (s for s in sellers if s.name == X), None,
                )
                for k in matched_x:
                    to_reregister.append({
                        "from_seller": A,
                        "to_seller": to_seller_obj,
                        "kiz": k,
                        "product_name": sales_data.get(k, ""),
                    })
                remaining -= matched_x
                verify_stats["kiz_reregistered"] += len(matched_x)
                verify_stats["per_seller_removed"][A] = (
                        verify_stats["per_seller_removed"].get(A, 0)
                        + len(matched_x)
                )
                verify_stats["per_seller_added"][X] = (
                        verify_stats["per_seller_added"].get(X, 0)
                        + len(matched_x)
                )
                file_matched_total += len(matched_x)
                for k in sorted(matched_x):
                    logger.report(
                        f"КИЗ {k}: удалён из {A} → {B}, "
                        f"добавлен в {A} → {X} (ИТОГ у {X})"
                    )

            logger.report(
                f"Файл {file_path.name}: КИЗов {len(sales_data)}, "
                f"найдено в ИТОГах {file_matched_total}"
            )

        # ---- Применение: сначала переоформления ----
        sales_gen = SalesFileGenerator(sales_folder, logger=logger)
        for item in to_reregister:
            to_seller = item["to_seller"]
            if to_seller is None:
                continue
            try:
                sales_gen.add_sale_row(
                    from_seller_name=item["from_seller"],
                    to_seller_name=to_seller.name,
                    to_seller_inn=to_seller.inn,
                    product_name=item["product_name"],
                    raw_kiz=item["kiz"],
                )
            except Exception as e:
                logger.critical(
                    f"Ошибка добавления КИЗ {item['kiz']} в "
                    f"{item['from_seller']} → {to_seller.name}: {e}",
                    can_influence=False,
                )

        # ---- Удаления ----
        for file_path, kiz_set in to_remove.items():
            for kiz in kiz_set:
                try:
                    ok = SalesFileRowsReader.remove_kiz(
                        file_path, kiz, logger,
                    )
                except Exception as e:
                    logger.critical(
                        f"Ошибка удаления КИЗ {kiz} из "
                        f"{file_path.name}: {e}",
                        can_influence=False,
                    )
                    continue
                if not ok:
                    logger.warning(
                        f"КИЗ {kiz}: удаление из {file_path.name} "
                        f"не удалось (файл не открылся)"
                    )

        # ---- Опустевшие файлы ----
        for file_path in to_remove:
            if not file_path.exists():
                continue
            if ExcelHelper.is_file_empty(file_path):
                try:
                    file_path.unlink()
                    verify_stats["empty_files_removed"] += 1
                except Exception as e:
                    logger.critical(
                        f"Ошибка удаления пустого файла "
                        f"{file_path.name}: {e}",
                        can_influence=False,
                    )

        sales_gen.remove_empty_files()

        verify_stats["itogs_found"] = sum(
            1 for v in itog_cache.values() if v is not None
        )

        logger.debug(
            f"_verify_against_itogs: to_remove файлов="
            f"{len(to_remove)}, to_reregister="
            f"{len(to_reregister)}, itog_cache={len(itog_cache)}"
        )
        logger.status("Проверка завершена")
        logger.debug(
            f"_verify_against_itogs: выход, itogs_found="
            f"{verify_stats['itogs_found']}, "
            f"sales_checked={verify_stats['sales_checked']}, "
            f"kiz_checked={verify_stats['kiz_checked']}, "
            f"kiz_removed={verify_stats['kiz_removed']}, "
            f"kiz_reregistered={verify_stats['kiz_reregistered']}, "
            f"empty_files_removed={verify_stats['empty_files_removed']}"
        )

        return verify_stats

    def _load_itog_set(self, chz_folder, seller_name, date_str,
                       cache, logger) -> set | None:
        """Ленивая загрузка КИЗов из ИТОГ-файла продавца.

        Вход:
            chz_folder — Path к папке ЧЗ_МП_{date}.
            seller_name — имя продавца.
            date_str — строка даты для FilenameUtils.
            cache — dict, кэш {seller_name: set | None}. Мутируется
                    in-place. None означает «файла нет / не
                    открылся» — при повторных вызовах не будет
                    попыток открыть снова.
            logger — LoggerV2.

        Выход:
            set[str] — storage-КИЗы из ИТОГ-файла. None — файла нет
            или не открылся.

        Роль:
            Единая точка загрузки ИТОГ-файла. Ленивая: при первом
            вызове читает и кэширует (в т.ч. None); при повторных —
            из кэша. КИЗы читаются через PreFinalRow.from_row —
            требует заполненные столбцы kiz и owner_company;
            строки без owner пропускаются.
        """
        if seller_name in cache:
            return cache[seller_name]

        itog_name = FilenameUtils.format_with_extension(
            f"ИТОГ {seller_name} {{date}}", date_str,
        )
        itog_path = chz_folder / itog_name

        if not itog_path.is_file():
            logger.report(f"ИТОГ {seller_name}: файл не найден")
            cache[seller_name] = None
            return None

        wb = WorkbookOpener.open(
            itog_path, logger=logger, read_only=True,
            description=f"ИТОГ {seller_name}",
        )
        if wb is None:
            logger.report(f"ИТОГ {seller_name}: файл не открылся")
            cache[seller_name] = None
            return None

        kiz_set: set = set()
        try:
            sheet = wb.active
            for row in sheet.iter_rows(min_row=2, values_only=True):
                parsed = PreFinalRow.from_row(row)
                if parsed is None:
                    continue
                storage_list = KizUtils.clean_kiz_for_storage(
                    parsed.kiz, logger=None,
                )
                if storage_list:
                    kiz_set.add(storage_list[0])
        finally:
            try:
                wb.close()
            except Exception:
                pass

        logger.report(
            f"ИТОГ {seller_name}: загружено {len(kiz_set)} КИЗов"
        )
        cache[seller_name] = kiz_set
        return kiz_set