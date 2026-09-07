from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
import json

class ReturnsPreparationService:
    """Сервис подготовки: фильтрует исходный файл возвратов и создаёт рабочий файл."""

    def prepare(self, target_dir, source_file, sellers=None, log_callback=None):
        if log_callback is None:
            log_callback = print

        ctx = TaskContext(target_dir, "Возвраты_{date}", "log_возвраты.txt", log_callback)
        ctx.log(f"=== Обработка возвратов начата {ctx.today.strftime('%d.%m.%Y %H:%M')} ===")
        ctx.log(f"Исходный файл: {source_file}")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        source_path = FileHelper.ensure_file_exists(ctx, source_file, "исходный файл")
        if source_path is None:
            return

        allowed_companies = TextUtils.get_allowed_companies(sellers)

        if not self._copy_source_file(ctx, source_path):
            return

        rows_copied, rows_skipped, unknown_companies, _ = self._filter_returns(
            ctx, source_path, allowed_companies
        )

        TextUtils.log_unknown_entities(
            unknown_companies,
            ctx.work_folder / "log_компании_вне_списка.txt",
            "Компании из столбца L, не соответствующие ни одному продавцу (с количеством строк):",
            ctx
        )

        ctx.log("Обработка возвратов завершена.\n")

    # ---------- Приватные методы ----------

    def _copy_source_file(self, ctx: TaskContext, source_path: Path) -> bool:
        """Копирует исходный файл в рабочую папку (с перезаписью)."""
        copy_name = ctx.format_filename("Исходные данные возвратов {date}")
        copy_dest = ctx.work_folder / copy_name
        return FileHelper.copy_file_with_log(
            source_path, copy_dest, ctx,
            description="исходный файл",
            overwrite=True
        )

    def _filter_returns(self, ctx: TaskContext, source_path: Path, allowed_companies: set):
        """
        Читает исходный файл, отбирает строки по разрешённым компаниям и сохраняет новый файл.
        Возвращает кортеж (rows_copied, rows_skipped, unknown_companies, status_counts).
        """
        wb_src = ExcelHelper.open_workbook_with_ctx(
            source_path, ctx, description="исходный файл",
            read_only=True, data_only=True
        )
        if wb_src is None:
            return 0, 0, {}, {}
        sheet_src = wb_src.active

        # Столбцы для копирования (индексы 1-based)
        columns_to_keep = ['B', 'D', 'F', 'G', 'H', 'L']
        col_indices = [2, 4, 6, 7, 8, 12]

        # Собираем заголовки
        header_row = []
        try:
            for col_letter in columns_to_keep:
                header_value = sheet_src[f"{col_letter}1"].value
                header_row.append(header_value)
        except Exception as e:
            ctx.log(f"Ошибка при чтении заголовков: {e}")
            header_row = []

        # Создаём новую книгу с заголовками
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

        result_name = ctx.format_filename("Возвраты_{date}")
        result_path = ctx.work_folder / result_name
        try:
            wb_new.save(result_path)
            ctx.log(f"Создан файл с возвратами: {result_name}")
            ctx.log(f"Скопировано строк: {rows_copied}")
            ctx.log(f"Пропущено строк (не совпала компания): {rows_skipped}")
            ctx.log_statistics("Статистика по статусам (скопированные строки):", status_counts)
        except Exception as e:
            ctx.log(f"Ошибка сохранения файла: {e}")

        wb_src.close()
        wb_new.close()

        return rows_copied, rows_skipped, unknown_companies, status_counts


class KizExportService:
    """Сервис выгрузки КИЗов для возврата."""

    def export(self, target_dir, log_callback=None):
        ctx = TaskContext(target_dir, "Возвраты_{date}", "log_выгрузка_КИЗов.txt", log_callback)
        source_file = ctx.get_work_file("Возвраты_{date}")
        source_file = FileHelper.ensure_file_exists(ctx, source_file, "файл возвратов")
        if source_file is None:
            return

        ctx.log(f"=== Выгрузка КИЗов для возврата начата {ctx.today.strftime('%d.%m.%Y %H:%M')} ===")

        wb = ExcelHelper.open_workbook_with_ctx(
            source_file, ctx, description="файл возвратов",
            read_only=True, data_only=True
        )
        if wb is None:
            return

        try:
            sheet = wb.active
            counters = {}
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) < 6:
                    continue
                kiz = row[0]
                status = row[1]
                company = row[5]

                if status is None or str(status).strip().upper() != "ВЫБЫЛ":
                    continue
                if kiz is None or company is None:
                    continue
                kiz = str(kiz).strip()
                company = str(company).strip()
                if not kiz or not company:
                    continue

                safe_company = TextUtils.sanitize_filename(company)

                txt_path = ctx.work_folder / f"{safe_company}.txt"
                with open(txt_path, "a", encoding="utf-8") as f:
                    f.write(kiz + "\n")

                counters[safe_company] = counters.get(safe_company, 0) + 1

            with open(ctx.log_path, "a", encoding="utf-8") as log_file:
                log_file.write("Результаты выгрузки КИЗов для возврата\n")
                log_file.write("=" * 50 + "\n")
                if counters:
                    for comp, cnt in sorted(counters.items(), key=lambda x: x[0].lower()):
                        log_file.write(f"{comp}: {cnt} КИЗов\n")
                else:
                    log_file.write("Не найдено ни одного КИЗа со статусом «ВЫБЫЛ».\n")

            ctx.log("Выгрузка завершена.")
        except Exception as e:
            ctx.log(f"Ошибка выгрузки КИЗов: {e}")
        finally:
            wb.close()


class KizTransferService:
    """Сервис подготовки КИЗов для передачи между продавцами."""

    def prepare_transfer(self, target_dir, sellers, log_callback=None):
        ctx = TaskContext(target_dir, "Возвраты_{date}", "log_передачи_КИЗов.txt", log_callback)
        source_file = ctx.get_work_file("Возвраты_{date}")
        source_file = FileHelper.ensure_file_exists(ctx, source_file, "файл возвратов")
        if source_file is None:
            return

        ctx.log(f"=== Подготовка передач КИЗов начата {ctx.today.strftime('%d.%m.%Y %H:%M')} ===")

        company_to_seller = TextUtils.build_key_mapping(
            sellers,
            key_extractor=lambda s: s.company,
            log_func=None
        )
        key_to_seller = TextUtils.build_key_mapping(
            sellers,
            key_extractor=lambda s: s.get_brand_keys(),
            log_func=ctx.log
        )

        wb_src = ExcelHelper.open_workbook_with_ctx(
            source_file, ctx, description="исходный файл",
            read_only=True, data_only=True
        )
        if wb_src is None:
            return

        try:
            sheet_src = wb_src.active
            self._write_transfer_result(ctx, sheet_src, company_to_seller, key_to_seller)
            ctx.log("Подготовка передач завершена.\n")
        except Exception as e:
            ctx.log(f"Ошибка подготовки передач КИЗов: {e}")
        finally:
            wb_src.close()

    def _write_transfer_result(self, ctx, sheet_src, company_to_seller, key_to_seller):
        """Формирует файлы продаж для каждой пары продавцов (унифицированный формат)."""
        sales_stats = {}  # {(владелец_бренда, владелец_КИЗа): количество}
        sales_files_created = []  # список путей к созданным файлам
        headers = ["КИЗ", "Владелец", "на кого продать", "ИНН того на кого продать", "бренд", "название товара"]

        for row_idx, row in enumerate(sheet_src.iter_rows(min_row=2, values_only=True), start=2):
            if len(row) < 6:
                continue
            kiz = row[0]                # столбец A
            product_name = row[2]       # столбец C – данные/название товара
            brand = row[3]              # столбец D – бренд
            owner_company = row[5]      # столбец F – компания-владелец КИЗа

            if not owner_company or not brand:
                continue

            brand_key = TextUtils.normalize(brand)
            seller_brand = key_to_seller.get(brand_key)  # продавец, которому принадлежит бренд
            if seller_brand is None:
                ctx.log(f"Строка {row_idx}: ключ бренда '{brand}' не найден – пропущена")
                continue

            # Ищем продавца-владельца КИЗа по company
            owner_seller = TextUtils.find_seller_by_company(owner_company, list(company_to_seller.values()))
            if owner_seller is None:
                ctx.log(f"Строка {row_idx}: владелец '{owner_company}' не найден – пропущена")
                continue

            # Если владелец КИЗа уже является владельцем бренда – пропускаем
            if owner_seller == seller_brand:
                continue

            # Проверяем, есть ли уже этот бренд у владельца КИЗа
            has_brand = any(TextUtils.normalize(key) == brand_key
                            for brand_obj in owner_seller.brands
                            for key in brand_obj.keys)
            if has_brand:
                ctx.log(f"Строка {row_idx}: бренд '{brand}' уже есть у {owner_seller.name} – пропущена")
                continue

            # Формируем файл продаж
            safe_from = TextUtils.sanitize_filename(seller_brand.name)
            safe_to = TextUtils.sanitize_filename(owner_seller.name)
            sales_file_name = f"продажа {safe_to} - {safe_from}.xlsx"
            sales_file_path = ctx.work_folder / sales_file_name

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
        ctx.log("\n--- ПРОВЕРКА ФАЙЛОВ ПРОДАЖ ---")
        for sales_file in sales_files_created:
            if ExcelHelper.is_file_empty(sales_file):
                try:
                    sales_file.unlink()
                    ctx.log(f"  Удалён пустой файл: {sales_file.name}")
                except Exception as e:
                    ctx.log(f"  Ошибка удаления {sales_file.name}: {e}")
            else:
                ctx.log(f"  Файл сохранён: {sales_file.name}")

        # Логируем статистику
        ctx.log("\n--- СТАТИСТИКА ПРОДАЖ ---")
        if sales_stats:
            for (from_seller, to_seller), count in sorted(sales_stats.items()):
                ctx.log(f"  {from_seller} → {to_seller}: {count} КИЗов")
        else:
            ctx.log("  Нет строк для передачи между продавцами")