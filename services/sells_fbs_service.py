from pathlib import Path
from datetime import date
from typing import Optional, List, Set, Dict, Any
import re

from PySide6.QtWidgets import QDialog

from utils.logger import ILogger, CompositeLogger, ReportFileLogger
from utils.log_templates import LogTemplates
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.price_utils import PriceUtils
from utils.path_utils import AppPaths


class PreparationService:
    """Сервис подготовки: копирование файлов ЧЗ МП и отчётов МП в рабочую папку."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def prepare(self, target_dir: str, fbs_files=None, mp_files=None, sellers=None):
        if sellers is None:
            sellers = []
        if fbs_files is None:
            fbs_files = []
        if mp_files is None:
            mp_files = []

        # Создаём рабочую папку
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        # Отчётный логгер
        report_path = work_folder / "log_подготовка.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Подготовка ЧЗ МП", work_folder=str(work_folder))

            self._copy_fbs_files(work_folder, fbs_files)
            self._copy_mp_files(work_folder, mp_files, sellers)

            LogTemplates.task_end(self.logger, "Подготовка ЧЗ МП")

        except Exception as e:
            self.logger.error(f"Ошибка подготовки: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)

    # ---------- Приватные методы ----------
    def _copy_fbs_files(self, work_folder: Path, fbs_files: List[str]):
        """Копирует файлы ЧЗ МП с последовательным переименованием."""
        if not fbs_files:
            self.logger.info("Нет файлов ЧЗ МП для копирования")
            return

        for i, src in enumerate(fbs_files):
            src_path = Path(src)
            if i == 0:
                new_name = f"ЧЗ_МП_{date.today().strftime('%d_%m_%Y')}.xlsx"
            else:
                new_name = f"ЧЗ_МП_{date.today().strftime('%d_%m_%Y')}_{i + 1}.xlsx"
            dst = work_folder / new_name
            FileHelper.copy_file_with_log(src_path, dst, self.logger, "ЧЗ МП", overwrite=False)

    def _copy_mp_files(self, work_folder: Path, mp_files: List[str], sellers):
        """Копирует отчёты МП, определяя продавца по ключам в имени файла."""
        if not mp_files:
            self.logger.info("Нет отчётов МП для копирования")
            return

        seller_counters = {}
        for src in mp_files:
            src_path = Path(src)
            fname_lower = src_path.stem.lower()
            found_seller = self._determine_seller_for_mp_file(fname_lower, sellers)

            if found_seller:
                seller_counters[found_seller.name] = seller_counters.get(found_seller.name, 0) + 1
                idx = seller_counters[found_seller.name]
                if idx == 1:
                    new_name = f"ОТЧЁТ МП ПО {found_seller.name}_{date.today().strftime('%d_%m_%Y')}.xlsx"
                else:
                    new_name = f"ОТЧЁТ МП ПО {found_seller.name}_{date.today().strftime('%d_%m_%Y')}_{idx}.xlsx"
            else:
                new_name = src_path.name
                self.logger.warning(f"Не удалось определить продавца для: {src_path.name}")

            dst = work_folder / new_name
            FileHelper.copy_file_with_log(src_path, dst, self.logger, "отчёт", overwrite=False)

    def _determine_seller_for_mp_file(self, file_name_lower: str, sellers):
        """Ищет продавца по вхождению любого ключа в имя файла."""
        for seller in sellers:
            if any(key.lower() in file_name_lower for key in seller.keys):
                return seller
        return None


class ExportKizService:
    """Сервис выгрузки КИЗов из ЧЗ_МП и отчётов МП в текстовые файлы."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def export(self, target_dir: str, sellers):
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        report_path = work_folder / "log_выгрузка_кизов.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Выгрузка КИЗов", work_folder=str(work_folder))

            kiz_by_seller = {seller.name: set() for seller in sellers}

            # 1. Обработка ЧЗ_МП
            chz_files = FileHelper.find_files_by_pattern(work_folder, "ЧЗ_МП*.xlsx")
            for chz_path in chz_files:
                LogTemplates.processing_chz_file(self.logger, chz_path.name)
                wb = ExcelHelper.open_workbook_safe(chz_path, read_only=True, data_only=True)
                if wb is None:
                    continue
                try:
                    for sheet_name in wb.sheetnames:
                        seller = ExcelHelper.find_seller_by_sheet_name(wb, sellers, sheet_name)
                        if seller is None:
                            self.logger.debug(f"  Лист '{sheet_name}' не соответствует ни одному продавцу – пропущен")
                            continue
                        sheet = wb[sheet_name]
                        kiz_list = ExcelHelper.read_column_values(sheet, col_index=1, start_row=2)
                        for kiz in kiz_list:
                            kiz_by_seller[seller.name].add(kiz)
                        LogTemplates.processing_chz_file(
                            self.logger,
                            chz_path.name,
                            seller_name=seller.name,
                            count=len(kiz_list)
                        )
                finally:
                    wb.close()

            # 2. Обработка отчётов МП
            mp_files = FileHelper.find_files_by_pattern(work_folder, "ОТЧЁТ МП ПО *.xlsx")
            for mp_path in mp_files:
                found_seller = None
                for seller in sellers:
                    if any(key.lower() in mp_path.stem.lower() for key in seller.keys):
                        found_seller = seller
                        break
                if found_seller is None:
                    self.logger.debug(f"  Не удалось определить продавца из имени файла – пропущен")
                    continue
                seller = found_seller

                LogTemplates.processing_mp_report(self.logger, mp_path.name)
                wb = ExcelHelper.open_workbook_safe(mp_path, read_only=True, data_only=True)
                if wb is None:
                    continue
                try:
                    if "КИЗ" not in wb.sheetnames:
                        self.logger.debug(f"  Лист 'КИЗ' отсутствует – пропущен")
                        continue
                    sheet = wb["КИЗ"]
                    kiz_list = ExcelHelper.read_column_values(sheet, col_index=2, start_row=2)
                    for kiz in kiz_list:
                        kiz_by_seller[seller.name].add(kiz)
                    LogTemplates.processing_mp_report(
                        self.logger,
                        mp_path.name,
                        seller_name=seller.name,
                        count=len(kiz_list)
                    )
                finally:
                    wb.close()

            # 3. Сохранение текстовых файлов
            self.logger.info("\n--- СОХРАНЕНИЕ ТЕКСТОВЫХ ФАЙЛОВ ---")
            for seller_name, kiz_set in kiz_by_seller.items():
                if not kiz_set:
                    self.logger.info(f"  {seller_name}: нет КИЗов – файл не создан")
                    continue

                cleaned_kiz_set = set()
                corrupted_count = 0

                for raw in kiz_set:
                    if len(raw) <= 31:
                        corrupted_count += 1
                        continue

                    cleaned = re.sub(r'_x001[dD]_', '', raw)
                    cleaned = ''.join(ch for ch in cleaned if ord(ch) >= 32)

                    fragments = []
                    if len(cleaned) > 100:
                        pattern = re.compile(r'01\d{14}')
                        match = pattern.search(cleaned, pos=80)
                        if match:
                            split_pos = match.start()
                            if split_pos > 0 and len(cleaned) - split_pos >= 31:
                                fragments.append(cleaned[:split_pos])
                                fragments.append(cleaned[split_pos:])
                        if not fragments:
                            fragments.append(cleaned)
                    else:
                        fragments.append(cleaned)

                    for frag in fragments:
                        if not frag.startswith("01"):
                            pos_01 = frag.find("01")
                            if pos_01 != -1 and len(frag) - pos_01 >= 31:
                                frag = frag[pos_01:]
                            else:
                                corrupted_count += 1
                                continue

                        if len(frag) <= 31:
                            corrupted_count += 1
                            continue

                        if TextUtils.is_cyrillic(frag):
                            frag = TextUtils.keyboard_translit(frag)

                        cleaned_kiz_set.add(frag)

                if not cleaned_kiz_set:
                    self.logger.info(f"  {seller_name}: после очистки не осталось КИЗов – файл не создан")
                    continue

                txt_path = work_folder / f"{seller_name}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    for kiz in sorted(cleaned_kiz_set):
                        f.write(kiz + "\n")

                LogTemplates.saving_kiz_files(
                    self.logger,
                    seller_name,
                    len(cleaned_kiz_set),
                    txt_path.name,
                    corrupted_count
                )

            LogTemplates.task_end(self.logger, "Выгрузка КИЗов")

        except Exception as e:
            self.logger.error(f"Ошибка выгрузки КИЗов: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)


class FilterPreFinalService:
    """Сервис фильтрации предитоговых файлов по статусу и владельцу."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def filter_files(self, target_dir: str, sellers):
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        report_path = work_folder / "log_фильтрация.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Фильтрация предитоговых файлов", work_folder=str(work_folder))

            allowed_companies = TextUtils.get_allowed_companies(sellers)

            for seller in sellers:
                file_path = work_folder / f"{seller.name}.xlsx"
                if not file_path.is_file():
                    self.logger.info(f"Файл для продавца '{seller.name}' не найден – пропущен")
                    continue

                wb = ExcelHelper.open_workbook_safe(file_path, read_only=False, data_only=True)
                if wb is None:
                    continue

                try:
                    sheet = wb.active
                    if sheet.max_row < 2:
                        self.logger.info(f"  Файл {file_path.name} пуст (только заголовки) – пропущен")
                        continue

                    headers = [cell.value for cell in sheet[1]]
                    filtered_rows, stats = ExcelHelper.filter_and_clean_rows(
                        sheet,
                        status_col=4,
                        owner_col=12,
                        allowed_owners=allowed_companies,
                        required_status="В ОБОРОТЕ"
                    )

                    LogTemplates.filtering_file(
                        self.logger,
                        file_path.name,
                        sheet.max_row - 1,
                        stats['total_kept'],
                        stats['status'],
                        stats['owner']
                    )

                    if stats['total_kept'] == 0:
                        new_wb, new_sheet = ExcelHelper.create_workbook_with_headers(headers, sheet_name=sheet.title)
                        new_wb.save(file_path)
                        new_wb.close()
                    else:
                        new_wb, new_sheet = ExcelHelper.create_workbook_with_headers(headers, sheet_name=sheet.title)
                        for _, row_values in filtered_rows:
                            new_sheet.append(row_values)
                        new_wb.save(file_path)
                        new_wb.close()

                except Exception as e:
                    self.logger.error(f"  Ошибка обработки файла {file_path.name}: {e}")
                finally:
                    wb.close()

            LogTemplates.task_end(self.logger, "Фильтрация предитоговых файлов")

        except Exception as e:
            self.logger.error(f"Ошибка фильтрации: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)


class GenerateSalesService:
    """Сервис формирования файлов продаж на основе владельца (company) КИЗов."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def generate(self, target_dir: str, sellers):
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        report_path = work_folder / "log_продажи.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Формирование файлов продаж", work_folder=str(work_folder))

            sales_stats = {}
            sales_files_created = []

            for seller in sellers:
                file_path = work_folder / f"{seller.name}.xlsx"
                if not file_path.is_file():
                    self.logger.info(f"Файл для продавца '{seller.name}' не найден – пропущен")
                    continue

                self.logger.info(f"\nОбработка файла: {file_path.name}")
                wb = ExcelHelper.open_workbook_safe(file_path, read_only=True, data_only=True)
                if wb is None:
                    continue

                try:
                    sheet = wb.active
                    if sheet.max_row < 2:
                        self.logger.info("  Файл пуст (только заголовки) – пропущен")
                        continue

                    for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                        if len(row) < 12:
                            continue

                        kiz = str(row[1]).strip() if row[1] is not None else ""
                        owner_company = str(row[11]).strip() if row[11] is not None else ""
                        brand = str(row[6]).strip() if row[6] is not None else ""
                        product_name = str(row[5]).strip() if row[5] is not None else ""

                        if not kiz or not owner_company:
                            continue

                        owner_seller = TextUtils.find_seller_by_company(owner_company, sellers)
                        if owner_seller is None:
                            self.logger.debug(f"  Строка {row_idx}: владелец '{owner_company}' не найден – пропущена")
                            continue

                        if owner_seller.name == seller.name:
                            continue

                        safe_from = TextUtils.sanitize_filename(owner_seller.name)
                        safe_to = TextUtils.sanitize_filename(seller.name)
                        sales_file_name = f"продажа {safe_from} - {safe_to}.xlsx"
                        sales_file_path = work_folder / sales_file_name

                        ExcelHelper.append_row_to_file(
                            sales_file_path,
                            [
                                kiz,
                                owner_company,
                                seller.name,
                                seller.inn,
                                brand,
                                product_name
                            ],
                            headers=["КИЗ", "Владелец", "на кого продать", "ИНН того на кого продать", "бренд", "название товара"]
                        )

                        if sales_file_path not in sales_files_created:
                            sales_files_created.append(sales_file_path)

                        key = (owner_seller.name, seller.name)
                        sales_stats[key] = sales_stats.get(key, 0) + 1

                finally:
                    wb.close()

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

            LogTemplates.sales_statistics(self.logger, sales_stats, len(sales_files_created))
            LogTemplates.task_end(self.logger, "Формирование файлов продаж")

        except Exception as e:
            self.logger.error(f"Ошибка формирования продаж: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)


class FinalizePricesService:
    """Сервис внесения цен из отчётов МП и финализации итоговых файлов."""

    def __init__(self, logger: ILogger, app_paths: Optional[AppPaths] = None):
        self.logger = logger
        self.app_paths = app_paths or AppPaths()

    def finalize(self, target_dir: str, sellers, saved_prices: dict = None):
        if saved_prices is None:
            saved_prices = {}

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        work_folder.mkdir(parents=True, exist_ok=True)

        report_path = work_folder / "log_цены.txt"
        report_logger = ReportFileLogger(report_path)
        if isinstance(self.logger, CompositeLogger):
            self.logger.add_logger(report_logger)

        try:
            LogTemplates.task_start(self.logger, "Внесение цен и финализация", work_folder=str(work_folder))

            for seller in sellers:
                # ---- 1. Загрузка цен из отчёта МП ----
                price_map = {}
                prices_list = []
                average_price = None

                mp_files = FileHelper.find_files_by_pattern(work_folder, f"ОТЧЁТ МП ПО {seller.name}*.xlsx")
                if mp_files:
                    mp_path = mp_files[0]
                    self.logger.info(f"\nЗагрузка цен из отчёта: {mp_path.name}")
                    wb_mp = ExcelHelper.open_workbook_safe(mp_path, read_only=True, data_only=True)
                    if wb_mp:
                        try:
                            if "КИЗ" in wb_mp.sheetnames:
                                sheet = wb_mp["КИЗ"]
                                for row in sheet.iter_rows(min_row=2, values_only=True):
                                    if len(row) >= 3 and row[1] and row[2] is not None:
                                        kiz = str(row[1]).strip()
                                        price = row[2]
                                        if isinstance(price, (int, float)):
                                            price_map[kiz] = price
                                            prices_list.append(price)
                                if prices_list:
                                    average_price = PriceUtils.calculate_average(saved_prices.get(seller.name), prices_list)
                                    self.logger.info(f"  Загружено {len(prices_list)} цен, новая средняя: {average_price}")
                                else:
                                    self.logger.info("  В отчёте не найдено ни одной цены")
                            else:
                                self.logger.info("  Лист 'КИЗ' отсутствует – цены не загружены")
                        finally:
                            wb_mp.close()
                else:
                    self.logger.info(f"\nОтчёт МП для продавца '{seller.name}' не найден – цены не загружены")

                # ---- 2. Если средняя цена не определена, запрашиваем у пользователя ----
                if average_price is None:
                    if saved_prices.get(seller.name):
                        average_price = saved_prices[seller.name]
                        self.logger.info(f"  Использую сохранённую цену: {average_price}")
                    else:
                        from ui.windows.shared_dialogs import AveragePriceInputDialog
                        dialog = AveragePriceInputDialog(None, seller.name)
                        if dialog.exec_() == QDialog.Accepted:
                            average_price = dialog.get_price()
                            saved_prices[seller.name] = average_price
                            self.logger.info(f"  Пользователь ввёл цену: {average_price}")
                        else:
                            self.logger.info(f"  ⚠️ Пользователь отменил ввод для продавца '{seller.name}' – пропускаем")
                            continue

                # ---- 3. Обработка предитогового файла ----
                file_path = work_folder / f"{seller.name}.xlsx"
                if not file_path.is_file():
                    self.logger.info(f"Файл для продавца '{seller.name}' не найден – пропущен")
                    continue

                self.logger.info(f"\nОбработка файла: {file_path.name}")
                wb = ExcelHelper.open_workbook_safe(file_path, read_only=False, data_only=True)
                if wb is None:
                    continue

                try:
                    sheet = wb.active
                    if sheet.max_row < 2:
                        self.logger.info("  Файл пуст (только заголовки) – пропущен")
                        continue

                    from_report_count = 0
                    generated_count = 0

                    for row_idx in range(2, sheet.max_row + 1):
                        kiz_cell = sheet.cell(row=row_idx, column=2)
                        price_cell = sheet.cell(row=row_idx, column=3)

                        kiz = str(kiz_cell.value).strip() if kiz_cell.value is not None else ""
                        if not kiz or kiz == "КИЗ":
                            continue

                        price_cell.value = None

                        if kiz in price_map:
                            price_cell.value = price_map[kiz]
                            from_report_count += 1
                        else:
                            price_cell.value = PriceUtils.generate_varied_price(average_price)
                            generated_count += 1

                    LogTemplates.price_finalization(
                        self.logger,
                        seller.name,
                        from_report_count,
                        generated_count,
                        average_price
                    )

                    # ---- Сохранение и переименование ----
                    wb.save(file_path)
                    wb.close()

                    new_name = f"ИТОГ {seller.name}_{date.today().strftime('%d_%m_%Y')}.xlsx"
                    new_path = work_folder / new_name
                    file_path.rename(new_path)
                    self.logger.info(f"  Файл переименован в {new_path.name}")

                    saved_prices[seller.name] = average_price

                    # Дополнительное сохранение
                    wb = ExcelHelper.open_workbook_safe(new_path, read_only=False, data_only=True)
                    if wb:
                        wb.save(new_path)
                        wb.close()

                except Exception as e:
                    self.logger.error(f"  Ошибка обработки файла: {e}")
                finally:
                    if wb:
                        wb.close()

            LogTemplates.task_end(self.logger, "Внесение цен и финализация")

        except Exception as e:
            self.logger.error(f"Ошибка финализации цен: {e}")
        finally:
            if isinstance(self.logger, CompositeLogger):
                self.logger.remove_logger(report_logger)

        return saved_prices