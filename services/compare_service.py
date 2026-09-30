"""
Сервис сравнения поставок.

Содержит два класса:
    CompareService — тонкий оркестратор: держит state, строит
                     LoggerV2, дёргает ридеры, стадии и генератор
                     отчёта. Вся тяжёлая логика — в утилитах.
    ReportGenerator — формирование Excel-отчёта и txt-списков.

Роль в программе:
    Вызывается из CompareWindow. Диалоги с пользователем переданы
    через callbacks (stage1_reviewer / stage2_confirmer /
    stage3_selector), сервис сам их не открывает — так UI и логика
    развязаны, а стадии можно тестировать без Qt.

    Порядок работы:
        copy_supply_sheet(...)       → копия листа поставки.
        build_consolidated_supply(...) → сборный файл.
        load_data()                  → SupplyItem + Candidate.
        run_stage1() / run_stage2() / run_stage3() → сопоставление.
        generate_report(...)         → xlsx + txt.
        save_mappings()              → сохранение сопоставлений.
"""

from pathlib import Path
from datetime import date
from typing import Optional

from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.txt_helper import TextFileWriter
from utils.compare_readers import (
    SupplyItemsReader, CandidatesReader, ConsolidatedSupplyBuilder,
)
from models.models import SupplyItem, Candidate
from services.compare_stages import Stage1, Stage2, Stage3
from storage.compare_mappings_storage import CompareMappingsStorage


class CompareService:
    """Оркестратор сравнения поставок.

    Роль:
        Держит состояние прогона (пути к подготовленным файлам,
        загруженные SupplyItem/Candidate, найденные на каждом
        этапе), строит LoggerV2 в начале каждого публичного метода
        и делегирует работу утилитам:
            - чтение Excel → utils/compare_readers.py;
            - разбор наименований → utils/parsers.py;
            - арифметика схожести → utils/similarity_utils.py;
            - индексы кандидатов → utils/index_utils.py;
            - стадии → services/compare_stages.py;
            - отчёты → ReportGenerator (этот файл) + txt_utils.py.

    Поля:
        _log_manager_v2 — фабрика логгеров V2 или None.
        _brands_set — set[str] ключей брендов (в нижнем регистре)
                      или None.
        _mappings_storage — CompareMappingsStorage (или создан
                            через PathManager fallback).
        _stage1_reviewer / _stage2_confirmer / _stage3_selector —
            callbacks, передаваемые в стадии.
        _current_output_dir: Path | None — обновляется в начале
            каждого публичного метода, знающего output_dir.
            Нужен _create_logger для TaskContext и work_folder.
        Ключевые state-поля (сохранены из старой версии):
            copied_supply_path, consolidated_supply_path,
            supply_items, candidates, found_stage1, found_stage2,
            final_items.
    """

    def __init__(self, log_manager_v2=None, brands_set=None,
                 mappings_storage=None,
                 stage1_reviewer=None, stage2_confirmer=None,
                 stage3_selector=None) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2 или None. При None логгер
                             не создаётся, все логи молча пропускаются.
            brands_set — set[str] ключей брендов в нижнем регистре
                         либо None.
            mappings_storage — CompareMappingsStorage. Если None —
                               создаётся свой через PathManager
                               (fallback для тестов без main.py).
            stage1_reviewer — callable(pairs) -> list[bool] или None.
            stage2_confirmer — callable(item, cand, score, remaining)
                               -> bool или None.
            stage3_selector — callable(item, candidates, remaining)
                              -> (dict | None, bool) или None.

        Роль: сохраняет ссылки, создаёт стадии с callback'ами.
              Хранилище маппингов — единое, не пересоздаётся.
        """
        self._log_manager_v2 = log_manager_v2
        self._brands_set = brands_set or set()
        self._stage1_reviewer = stage1_reviewer
        self._stage2_confirmer = stage2_confirmer
        self._stage3_selector = stage3_selector

        if mappings_storage is None:
            from utils.path_manager import PathManager
            mappings_storage = CompareMappingsStorage(PathManager())
        self._mappings_storage = mappings_storage

        # NEW: текущая рабочая папка. Обновляется в начале публичных
        # методов, знающих output_dir. Нужна _create_logger.
        self._current_output_dir: Optional[Path] = None

        # State прогона — сохранён как был.
        self.copied_supply_path: Optional[Path] = None
        self.consolidated_supply_path: Optional[Path] = None
        self.supply_items: list[SupplyItem] = []
        self.candidates: list[Candidate] = []
        self.found_stage1: list[SupplyItem] = []
        self.found_stage2: list[SupplyItem] = []
        self.final_items: list[SupplyItem] = []

    # ============================================================
    # Логирование
    # ============================================================

    def _create_logger(self):
        """Создаёт LoggerV2 для текущего output_dir.

        Выход:
            LoggerV2 или None, если log_manager_v2 не передан либо
            _current_output_dir ещё не установлен.

        Роль:
            Единая точка создания логгера. TaskContext — только
            пути (Логи/Отчёты), логирование — через LoggerV2 с
            историческим именем файла log_сравнение.txt.
        """
        if self._log_manager_v2 is None or self._current_output_dir is None:
            return None
        ctx = TaskContext(
            self._current_output_dir,
            "Сравнение_{date}",
            "log_сравнение.txt",
            subfolders=["Логи", "Отчёты"],
        )
        return self._log_manager_v2.create_logger_v2(
            source="CompareService.compare_service",
            domain="compare",
            work_folder=ctx.logs_dir,
            log_filename="log_сравнение.txt",
        )

    # ============================================================
    # Маппинги
    # ============================================================

    def load_mappings(self) -> dict:
        """Загружает сохранённые сопоставления.

        Выход: dict {brand: {article: {"shk": ..., "supply_name": ...,
                                       "candidate_name": ...}}}.

        Роль: делегирует в CompareMappingsStorage. Нормализация
              имён брендов удалена вместе с brands_from_config.
        """
        return self._mappings_storage.get_all() or {}

    def save_mappings(self, mappings=None) -> None:
        """Сохраняет сопоставления.

        Вход: mappings — dict. Если None — собирается из текущего
              состояния сервиса (_collect_mappings).

        Роль: файл перезаписывается целиком через replace_all.
        """
        logger = self._create_logger()
        if mappings is None:
            mappings = self._collect_mappings(logger)
            if not mappings:
                if logger is not None:
                    logger.report("Нет сопоставлений для сохранения")
                return
        self._mappings_storage.replace_all(mappings)
        if logger is not None:
            logger.report(f"Сохранено брендов: {len(mappings)}")

    def _collect_mappings(self, logger) -> dict:
        """Собирает сопоставления из найденных товаров.

        Вход: logger — LoggerV2 или None (не используется, но
              параметр зарезервирован для симметрии с _apply_mappings).

        Выход: dict {brand: {article: {...}}}.

        Роль: обходит found_stage1 + found_stage2 + final_items,
              берёт те, где есть found + matched_candidate + article.
        """
        mappings: dict = {}
        all_items: list = []
        all_items.extend(self.found_stage1)
        all_items.extend(self.found_stage2)
        all_items.extend(self.final_items)

        for item in all_items:
            if item.found and item.matched_candidate and item.article:
                brand = item.brand or "Без бренда"
                article = item.article
                shk = item.matched_candidate.shk or ""
                supply_name = item.matched_candidate.name or ""
                candidate_name = item.name or ""
                mappings.setdefault(brand, {})[article] = {
                    "shk": shk,
                    "supply_name": supply_name,
                    "candidate_name": candidate_name,
                }
        return mappings

    def _apply_mappings(self, items: list, candidates: list,
                        logger) -> tuple:
        """Применяет сохранённые сопоставления до этапа 1.

        Вход:
            items — список SupplyItem.
            candidates — список Candidate.
            logger — LoggerV2 или None.

        Выход:
            (remaining_items, remaining_candidates) — те, что не
            удалось сопоставить по маппингам.

        Роль: по каждой item ищет её article в mappings, берёт
              кандидата по shk среди свободных и помечает пару
              stage=1. Совпадает с прежней логикой.
        """
        mappings = self.load_mappings()
        if not mappings:
            return items, candidates

        remaining_items: list = []
        remaining_candidates = candidates.copy()

        for item in items:
            if not item.article:
                remaining_items.append(item)
                continue

            handled = False
            for brand, articles in mappings.items():
                if item.article in articles:
                    shk = articles[item.article]["shk"]
                    matched_cand = None
                    for cand in remaining_candidates:
                        if cand.shk == shk and not cand.used:
                            matched_cand = cand
                            break
                    if matched_cand is not None:
                        matched_cand.used = True
                        item.found = True
                        item.matched_candidate = matched_cand
                        item.stage = 1
                        if logger is not None:
                            logger.report(
                                f"  Применено сохранённое сопоставление: "
                                f"{item.article} -> {shk}"
                            )
                    else:
                        if logger is not None:
                            logger.report(
                                f"  Не найден кандидат для сохранённого "
                                f"сопоставления: {item.article} -> {shk}"
                            )
                    handled = True
                    break
            if not handled:
                remaining_items.append(item)

        remaining_candidates = [c for c in remaining_candidates if not c.used]
        return remaining_items, remaining_candidates

    # ============================================================
    # Подготовка файлов
    # ============================================================

    def copy_supply_sheet(self, supply_file_path, output_dir) -> Path:
        """Копирует лист поставки в рабочую папку.

        Вход:
            supply_file_path — путь к исходному Excel.
            output_dir — корневая папка задачи.

        Выход:
            Path к копии Лист_поставки_копия_{date}.xlsx.

        Роль:
            Копирует файл и добавляет два столбца в шапку:
            «Итоговое количество» и «КИЗ». Обновляет
            _current_output_dir. Логи — через logger.report.
        """
        self._current_output_dir = Path(output_dir)
        logger = self._create_logger()

        supply_path = Path(supply_file_path)
        if not supply_path.exists():
            raise FileNotFoundError(
                f"Файл листа поставки не найден: {supply_file_path}"
            )

        if logger is not None:
            logger.report("=== КОПИРОВАНИЕ ЛИСТА ПОСТАВКИ ===")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        copy_path = output_dir_path / f"Лист_поставки_копия_{date_str}.xlsx"

        if logger is not None:
            logger.report(f"Исходный файл: {supply_path.name}")
            logger.report(f"Копия: {copy_path.name}")

        wb = ExcelHelper.open_data_file(
            supply_path, read_only=False, data_only=True,
        )
        try:
            ws = wb.active
            if (ws.max_row is not None and ws.max_row > 0
                    and ws.max_column is not None and ws.max_column > 0):
                max_col = ws.max_column
                ws.cell(row=1, column=max_col + 1,
                        value="Итоговое количество")
                ws.cell(row=1, column=max_col + 2, value="КИЗ")
                if logger is not None:
                    logger.report(
                        "  Добавлены столбцы 'Итоговое количество' и 'КИЗ'"
                    )
            else:
                if logger is not None:
                    logger.report(
                        f"  max_row={ws.max_row}, max_column={ws.max_column}"
                    )
                    logger.report(
                        "  Лист пуст или не содержит данных — "
                        "столбцы не добавлены"
                    )
            wb.save(copy_path)
        finally:
            wb.close()

        self.copied_supply_path = copy_path
        return copy_path

    def build_consolidated_supply(self, supply_files, output_dir) -> Path:
        """Собирает общий файл поставок из списка.

        Вход:
            supply_files — список путей к файлам поставок.
            output_dir — корневая папка задачи.

        Выход:
            Path к Сборный_поставок_{date}.xlsx.

        Роль: делегирует в ConsolidatedSupplyBuilder. Обновляет
              _current_output_dir, сохраняет результат в
              self.consolidated_supply_path.
        """
        self._current_output_dir = Path(output_dir)
        logger = self._create_logger()
        if logger is not None:
            logger.report("=== ФОРМИРОВАНИЕ СБОРНОГО ФАЙЛА ПОСТАВОК ===")

        path = ConsolidatedSupplyBuilder.build(
            supply_files, output_dir, logger,
        )
        self.consolidated_supply_path = path
        return path

    def load_data(self) -> None:
        """Загружает SupplyItem и Candidate из подготовленных файлов.

        Вход: нет.
        Выход: нет.

        Роль: делегирует в SupplyItemsReader/CandidatesReader.
              Требует, чтобы copy_supply_sheet и
              build_consolidated_supply уже отработали.
        """
        if not self.copied_supply_path or not self.consolidated_supply_path:
            raise RuntimeError("Сначала выполните подготовку файлов.")

        logger = self._create_logger()
        self.supply_items = SupplyItemsReader.read(
            self.copied_supply_path, self._brands_set, logger,
        )
        self.candidates = CandidatesReader.read(
            self.consolidated_supply_path, self._brands_set, logger,
        )

    # ============================================================
    # Стадии
    # ============================================================

    def run_stage1(self) -> None:
        """Запускает этап 1 — жёсткую сверку.

        Вход: нет.
        Выход: нет.

        Роль: применяет сохранённые маппинги, затем прогоняет
              оставшееся через Stage1 (utils уже дали индексы и
              пересечения). Результат — found_stage1, обновлённые
              supply_items и candidates.
        """
        if not self.supply_items or not self.candidates:
            raise RuntimeError(
                "Данные не загружены. Выполните подготовку и загрузку."
            )
        logger = self._create_logger()
        remaining_items, remaining_candidates = self._apply_mappings(
            self.supply_items, self.candidates, logger,
        )
        found, remaining, updated_candidates = Stage1(
            logger=logger, reviewer=self._stage1_reviewer,
        ).run(remaining_items, remaining_candidates)

        # Все найденные на этапе 1 — и через маппинги, и через Stage1.
        mapped_items = [
            item for item in self.supply_items if item not in remaining_items
        ]
        self.found_stage1 = found + mapped_items
        self.supply_items = remaining
        self.candidates = updated_candidates

    def run_stage2(self) -> None:
        """Запускает этап 2 — мягкую сверку (Жаккар >= 0.7)."""
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        logger = self._create_logger()
        self.found_stage2, self.supply_items, self.candidates = Stage2(
            logger=logger, confirmer=self._stage2_confirmer,
        ).run(self.supply_items, self.candidates)

    def run_stage3(self) -> None:
        """Запускает этап 3 — ручной выбор кандидатов."""
        if not self.supply_items or not self.candidates:
            raise RuntimeError("Данные не загружены.")
        logger = self._create_logger()
        self.final_items = Stage3(
            logger=logger, selector=self._stage3_selector,
        ).run(self.supply_items, self.candidates)

    # ============================================================
    # Отчёт
    # ============================================================

    def generate_report(self, output_dir) -> None:
        """Формирует Excel-отчёт и txt-списки.

        Вход: output_dir — куда писать.
        Выход: нет.

        Роль: собирает все найденные товары (stage1 + stage2 +
              final_items), передаёт в ReportGenerator. Обновляет
              _current_output_dir.
        """
        if not self.final_items:
            raise RuntimeError("Нет финальных данных. Выполните этап 3.")

        self._current_output_dir = Path(output_dir)
        logger = self._create_logger()

        all_items: list = []
        all_items.extend(self.found_stage1)
        all_items.extend(self.found_stage2)
        all_items.extend(self.final_items)

        ReportGenerator(logger).generate(
            all_items, Path(output_dir), self.candidates,
        )

    # ============================================================
    # НЕ ИСПОЛЬЗУЕТСЯ, ОСТАВЛЕНО НА СЛУЧАЙ ВОССТАНОВЛЕНИЯ
    # (удалить после подтверждения, что восстановление не потребуется)
    # ============================================================
    #
    # def set_brands_from_config(self, brands):
    #     self.brands_from_config = brands
    #
    # def _normalize_brand_names(self, mappings, brands_from_config):
    #     if not self.brands_from_config:
    #         return mappings
    #     brand_map = {b.name: b for b in self.brands_from_config}
    #     normalized = {}
    #     for brand_name, articles in mappings.items():
    #         canonical = None
    #         lower_name = brand_name.lower()
    #         for b in brand_map.values():
    #             if b.name.lower() == lower_name:
    #                 canonical = b.name
    #                 break
    #         if canonical is None:
    #             for b in brand_map.values():
    #                 if any(brand_name.lower() in key.lower() for key in b.keys):
    #                     canonical = b.name
    #                     break
    #         if canonical is None:
    #             canonical = brand_name
    #         if canonical in normalized:
    #             normalized[canonical].update(articles)
    #         else:
    #             normalized[canonical] = articles.copy()
    #     return normalized


class ReportGenerator:
    """Формирование Excel-отчёта и txt-списков.

    Роль:
        Тонкий генератор. Сохранение структуры столбцов и порядка
        строк повторяет старый ReportGenerator.generate, но Excel
        пишется через ExcelHelper.create_report_workbook, а txt —
        через CompareReportTxtWriter.

    Контракт:
        logger может быть None — все логи тогда молча пропускаются.
    """

    def __init__(self, logger=None) -> None:
        """Конструктор.

        Вход: logger — LoggerV2 или None.
        Роль: сохраняет ссылку.
        """
        self._logger = logger

    def generate(self, items: list, output_dir: Path,
                 candidates=None) -> None:
        """Формирует Отчёт_сравнения_{date}.xlsx и txt-списки.

        Вход:
            items — объединённый список SupplyItem (все найденные
                    плюс не найденные на этапах).
            output_dir — куда писать.
            candidates — список Candidate для списка «лишних».

        Выход: нет.

        Роль:
            Порядок и состав столбцов Excel сохранены как в
            прежней версии:
                № | Наименование листа | Кол-во лист |
                Наименование поставки | Кол-во поставки |
                Серийный номер | Этап | Разница
            Для найденных строк заполняются все столбцы, для
            не найденных — только 1, 2, 3, 7 (этап = «Не найдено»).
        """
        if self._logger is not None:
            self._logger.report("=== ФОРМИРОВАНИЕ ОТЧЁТА ===")

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        headers = [
            "№", "Наименование листа", "Кол-во лист",
            "Наименование поставки", "Кол-во поставки",
            "Серийный номер", "Этап", "Разница",
        ]

        rows: list = []
        not_found: list = []
        for item in items:
            if item.found and item.matched_candidate:
                cand = item.matched_candidate
                diff = (
                    (item.count - cand.count)
                    if (item.count is not None and cand.count is not None)
                    else "?"
                )
                rows.append([
                    item.row_num, item.name, item.count,
                    cand.name, cand.count, cand.serial,
                    f"Этап {item.stage}", diff,
                ])
            else:
                not_found.append(item)
                rows.append([
                    item.row_num, item.name, item.count,
                    None, None, None, "Не найдено", None,
                ])

        report_path = output_dir / f"Отчёт_сравнения_{date_str}.xlsx"
        wb, _ = ExcelHelper.create_report_workbook(
            headers, rows, sheet_name="Сравнение",
        )
        try:
            wb.save(report_path)
        finally:
            wb.close()

        if self._logger is not None:
            self._logger.report(f"Отчёт сохранён: {report_path.name}")

        # txt-списки — через TextFileWriter.write.
        if not_found:
            not_found_path = output_dir / f"Не_найдено_{date_str}.txt"
            created = TextFileWriter.write(
                not_found_path,
                header="Товары из листа поставки, не найденные в поставках:",
                items=[
                    f"{item.name} (кол-во: {item.count})"
                    for item in not_found
                ],
                logger=self._logger,
            )
            if created and self._logger is not None:
                self._logger.report(
                    f"Список не найденных сохранён: {not_found_path.name}"
                )

        if candidates is not None:
            unused = [c for c in candidates if not c.used]
            if unused:
                unused_path = (
                        output_dir / f"Лишние_в_поставках_{date_str}.txt"
                )
                created = TextFileWriter.write(
                    unused_path,
                    header="Товары из поставок, которых нет в листе (лишние):",
                    items=[
                        f"{c.name} (кол-во: {c.count})"
                        for c in unused
                    ],
                    logger=self._logger,
                )
                if created and self._logger is not None:
                    self._logger.report(
                        f"Список лишних в поставках сохранён: "
                        f"{unused_path.name}"
                    )

