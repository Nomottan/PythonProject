from pathlib import Path
from datetime import date
from typing import Optional, List, Set, Dict, Any

from utils.logger import ILogger, CompositeLogger, ReportFileLogger
from utils.log_templates import LogTemplates
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.path_utils import AppPaths


class ReturnsPreparationService:
    """
    Сервис подготовки возвратов: фильтрует исходный файл по компаниям продавцов
    и создаёт рабочий файл для дальнейшей обработки.
    """

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def prepare(self, target_dir: str, source_file: str, sellers=None):
        if sellers is None:
            sellers = []

        # Создаём рабочую папку
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"Возвраты_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        # Отчётный логгер для этой задачи
        report_path = work_folder / "log_возвраты.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Обработка возвратов", source_file, str(work_folder))

            # Проверяем существование исходного файла
            source_path = FileHelper.ensure_file_exists(source_file, self.logger, "исходный файл")
            if source_path is None:
                return

            allowed_companies = TextUtils.get_allowed_companies(sellers)

            # Копируем исходный файл в рабочую папку
            if not self._copy_source_file(work_folder, source_path):
                return

            # Фильтруем возвраты
            rows_copied, rows_skipped, unknown_companies, status_counts = self._filter_returns(
                work_folder, source_path, allowed_companies
            )

            LogTemplates.report_file_created(
                self.logger,
                "возвратами",
                work_folder / f"Возвраты_{date_str}.xlsx",
                rows_copied,
                rows_skipped
            )

            # Логируем неизвестные компании
            if unknown_companies:
                log_path = work_folder / "log_компании_вне_списка.txt"
                LogTemplates.unknown_entities(
                    self.logger,
                    unknown_companies,
                    log_path,
                    "Компании из столбца L, не соответствующие ни одному продавцу (с количеством строк):",
                    self.logger
                )

            LogTemplates.task_end(self.logger, "Обработка возвратов")

        except Exception as e:
            self.logger.error(f"Ошибка при подготовке возвратов: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)

    # ---------- Приватные методы ----------

    def _copy_source_file(self, work_folder: Path, source_path: Path) -> bool:
        """Копирует исходный файл в рабочую папку с переименованием."""
        copy_name = f"Исходные данные возвратов_{date.today().strftime('%d_%m_%Y')}.xlsx"
        copy_dest = work_folder / copy_name
        return FileHelper.copy_file_with_log(source_path, copy_dest, self.logger, "исходный файл", overwrite=True)

    def _filter_returns(self, work_folder: Path, source_path: Path, allowed_companies: Set[str]):
        """
        Фильтрует строки исходного файла по разрешённым компаниям и сохраняет результат.
        Возвращает (rows_copied, rows_skipped, unknown_companies, status_counts).
        """
        wb_src = ExcelHelper.open_workbook_safe(source_path, read_only=True, data_only=True)
        if wb_src is None:
            self.logger.error("Не удалось открыть исходный файл")
            return 0, 0, {}, {}

        sheet_src = wb_src.active
        columns_to_keep = ['B', 'D', 'F', 'G', 'H', 'L']
        col_indices = [2, 4, 6, 7, 8, 12]

        # Собираем заголовки
        header_row = []
        try:
            for col_letter in columns_to_keep:
                header_value = sheet_src[f"{col_letter}1"].value
                header_row.append(header_value)
        except Exception as e:
            self.logger.error(f"Ошибка чтения заголовков: {e}")
            header_row = []

        wb_new, ws_new = ExcelHelper.create_workbook_with_headers(
            headers=header_row,
            sheet_name="Возвраты",
            write_only=True
        )

        rows_copied = 0
        rows_skipped = 0
        unknown_companies = {}
        status_counts = {}

        def filter_condition(row):
            nonlocal rows_skipped
            cell_L_val = row[11] if len(row) > 11 else None
            cell_L_str = str(cell_L_val).strip() if cell_L_val is not None else ""

            if not allowed_companies:
                return True

            check_val = TextUtils.normalize(cell_L_str)
            if check_val in allowed_companies:
                return True

            if cell_L_str:
                unknown_companies[cell_L_str] = unknown_companies.get(cell_L_str, 0) + 1
            rows_skipped += 1
            return False

        rows_copied = ExcelHelper.copy_filtered_rows(
            source_sheet=sheet_src,
            target_sheet=ws_new,
            columns_to_keep=col_indices,
            condition=filter_condition,
            start_row=2,
            status_col_idx=3,
            status_counts=status_counts
        )

        # Сохраняем результат
        result_name = f"Возвраты_{date.today().strftime('%d_%m_%Y')}.xlsx"
        result_path = work_folder / result_name
        try:
            wb_new.save(result_path)
            self.logger.info(f"Создан файл с возвратами: {result_name}")
            self.logger.info(f"Скопировано строк: {rows_copied}")
            self.logger.info(f"Пропущено строк (не совпала компания): {rows_skipped}")
            if status_counts:
                LogTemplates.log_statistics(self.logger, "Статистика по статусам (скопированные строки):", status_counts)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения файла: {e}")

        wb_src.close()
        wb_new.close()

        return rows_copied, rows_skipped, unknown_companies, status_counts


class KizExportService:
    """Сервис выгрузки КИЗов для возврата (строки со статусом «ВЫБЫЛ»)."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def export(self, target_dir: str):
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"Возвраты_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        source_file = work_folder / f"Возвраты_{date_str}.xlsx"
        if not source_file.exists():
            self.logger.error(f"Файл возвратов не найден: {source_file}")
            return

        report_path = work_folder / "log_выгрузка_КИЗов.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Выгрузка КИЗов для возврата", work_folder=str(work_folder))

            wb = ExcelHelper.open_workbook_safe(source_file, read_only=True, data_only=True)
            if wb is None:
                self.logger.error("Не удалось открыть файл возвратов")
                return

            try:
                sheet = wb.active
                counters = {}
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if len(row) < 6:
                        continue
                    kiz = row[0]        # столбец A
                    status = row[1]     # столбец B
                    company = row[5]    # столбец F

                    if status is None or str(status).strip().upper() != "ВЫБЫЛ":
                        continue
                    if not kiz or not company:
                        continue
                    kiz = str(kiz).strip()
                    company = str(company).strip()
                    if not kiz or not company:
                        continue

                    safe_company = TextUtils.sanitize_filename(company)
                    txt_path = work_folder / f"{safe_company}.txt"
                    with open(txt_path, "a", encoding="utf-8") as f:
                        f.write(kiz + "\n")
                    counters[safe_company] = counters.get(safe_company, 0) + 1

                if counters:
                    self.logger.info("Результаты выгрузки КИЗов для возврата:")
                    for comp, cnt in sorted(counters.items(), key=lambda x: x[0].lower()):
                        self.logger.info(f"  {comp}: {cnt} КИЗов")
                else:
                    self.logger.info("Не найдено ни одного КИЗа со статусом «ВЫБЫЛ».")

            finally:
                wb.close()

            LogTemplates.task_end(self.logger, "Выгрузка КИЗов для возврата")

        except Exception as e:
            self.logger.error(f"Ошибка выгрузки КИЗов: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)


class KizTransferService:
    """Сервис подготовки КИЗов для передачи между продавцами."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def prepare_transfer(self, target_dir: str, sellers):
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"Возвраты_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        source_file = work_folder / f"Возвраты_{date_str}.xlsx"
        if not source_file.exists():
            self.logger.error(f"Файл возвратов не найден: {source_file}")
            return

        report_path = work_folder / "log_передачи_КИЗов.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Подготовка передач КИЗов", work_folder=str(work_folder))

            # Строим маппинги: компания -> продавец, бренд-ключ -> продавец
            company_to_seller = TextUtils.build_key_mapping(
                sellers,
                key_extractor=lambda s: s.company,
                log_func=lambda msg: self.logger.warning(msg)
            )
            key_to_seller = TextUtils.build_key_mapping(
                sellers,
                key_extractor=lambda s: s.get_brand_keys(),
                log_func=lambda msg: self.logger.warning(msg)
            )

            wb_src = ExcelHelper.open_workbook_safe(source_file, read_only=True, data_only=True)
            if wb_src is None:
                self.logger.error("Не удалось открыть файл возвратов")
                return

            try:
                sheet_src = wb_src.active
                self._write_transfer_result(work_folder, sheet_src, company_to_seller, key_to_seller)
            finally:
                wb_src.close()

            LogTemplates.task_end(self.logger, "Подготовка передач КИЗов")

        except Exception as e:
            self.logger.error(f"Ошибка подготовки передач КИЗов: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)

    def _write_transfer_result(self, work_folder, sheet_src, company_to_seller, key_to_seller):
        """
        Формирует файлы продаж для каждой пары продавцов.
        Записывает только те строки, где владелец КИЗа не является владельцем бренда,
        и бренд ещё не привязан к владельцу.
        """
        sales_stats = {}
        sales_files_created = []
        headers = ["КИЗ", "Владелец", "на кого продать", "ИНН того на кого продать", "бренд", "название товара"]

        for row_idx, row in enumerate(sheet_src.iter_rows(min_row=2, values_only=True), start=2):
            if len(row) < 6:
                continue
            kiz = row[0]             # столбец A
            product_name = row[2]    # столбец C
            brand = row[3]           # столбец D
            owner_company = row[5]   # столбец F

            if not owner_company or not brand:
                continue

            brand_key = TextUtils.normalize(brand)
            seller_brand = key_to_seller.get(brand_key)
            if seller_brand is None:
                self.logger.warning(f"Строка {row_idx}: ключ бренда '{brand}' не найден – пропущена")
                continue

            owner_seller = TextUtils.find_seller_by_company(owner_company, list(company_to_seller.values()))
            if owner_seller is None:
                self.logger.warning(f"Строка {row_idx}: владелец '{owner_company}' не найден – пропущена")
                continue

            if owner_seller == seller_brand:
                continue

            # Проверяем, есть ли уже этот бренд у владельца КИЗа
            has_brand = any(
                TextUtils.normalize(key) == brand_key
                for brand_obj in owner_seller.brands
                for key in brand_obj.keys
            )
            if has_brand:
                self.logger.info(f"Строка {row_idx}: бренд '{brand}' уже есть у {owner_seller.name} – пропущена")
                continue

            # Формируем имя файла и данные
            safe_from = TextUtils.sanitize_filename(seller_brand.name)
            safe_to = TextUtils.sanitize_filename(owner_seller.name)
            sales_file_name = f"продажа {safe_to} - {safe_from}.xlsx"
            sales_file_path = work_folder / sales_file_name

            row_data = [
                kiz if kiz is not None else "",
                str(owner_company).strip(),
                seller_brand.name,
                seller_brand.inn,
                str(brand).strip(),
                str(product_name).strip() if product_name is not None else ""
            ]

            ExcelHelper.append_row_to_file(sales_file_path, row_data, headers=headers)

            if sales_file_path not in sales_files_created:
                sales_files_created.append(sales_file_path)

            key = (seller_brand.name, owner_seller.name)
            sales_stats[key] = sales_stats.get(key, 0) + 1

        # Удаляем пустые файлы
        self.logger.info("\n--- ПРОВЕРКА ФАЙЛОВ ПРОДАЖ ---")
        for sales_file in sales_files_created:
            if ExcelHelper.is_file_empty(sales_file):
                try:
                    sales_file.unlink()
                    self.logger.info(f"  Удалён пустой файл: {sales_file.name}")
                except Exception as e:
                    self.logger.error(f"  Ошибка удаления {sales_file.name}: {e}")
            else:
                self.logger.info(f"  Файл сохранён: {sales_file.name}")

        # Логируем статистику
        LogTemplates.transfer_preparation_result(self.logger, sales_stats, len(sales_files_created))