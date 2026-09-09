from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.kiz_utils import KizUtils
from utils.sales_file_generator import SalesFileGenerator

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
    """Сервис выгрузки КИЗов для возврата с валидацией и очисткой."""

    def __init__(self, kiz_validator):
        self.kiz_validator = kiz_validator

    def export(self, target_dir, log_callback=None):
        ctx = TaskContext(target_dir, "Возвраты_{date}", "log_выгрузка_КИЗов.txt", log_callback)
        source_file = ctx.get_work_file("Возвраты_{date}")
        source_file = FileHelper.ensure_file_exists(ctx, source_file, "файл возвратов")
        if source_file is None:
            return

        ctx.log(f"=== Выгрузка КИЗов для возврата (с валидацией и очисткой) ===")

        self.kiz_validator.set_log_path(ctx.work_folder)
        self.kiz_validator.load()

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
                raw_kiz = row[0]
                status = row[1]
                company = row[5]

                if status is None or str(status).strip().upper() != "ВЫБЫЛ":
                    continue
                if raw_kiz is None or company is None:
                    continue

                full_cleaned_list = KizUtils.clean_kiz_full(raw_kiz)
                if not full_cleaned_list:
                    ctx.log(f"⚠️ Некорректный КИЗ (очистка не дала результатов): {str(raw_kiz)[:50]}...")
                    continue

                company_str = str(company).strip()
                safe_company = TextUtils.sanitize_filename(company_str)

                for full_kiz in full_cleaned_list:
                    storage_list = KizUtils.clean_kiz_for_storage(full_kiz)
                    if not storage_list:
                        continue
                    storage_kiz = storage_list[0]
                    if self.kiz_validator.validate_for_return(storage_kiz):
                        txt_path = ctx.work_folder / f"{safe_company}.txt"
                        with open(txt_path, "a", encoding="utf-8") as f:
                            f.write(full_kiz + "\n")
                        counters[safe_company] = counters.get(safe_company, 0) + 1

            # Итоги
            ctx.log("Результаты выгрузки КИЗов для возврата")
            ctx.log("=" * 50)
            if counters:
                for comp, cnt in sorted(counters.items(), key=lambda x: x[0].lower()):
                    ctx.log(f"{comp}: {cnt} КИЗов")
            else:
                ctx.log("Не найдено ни одного КИЗа, прошедшего валидацию (со статусом ВЫБЫЛ).")
            ctx.log("Выгрузка завершена.")

        except Exception as e:
            ctx.log(f"Ошибка выгрузки КИЗов: {e}")
        finally:
            if wb:
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
            # Создаём генератор файлов продаж
            sales_gen = SalesFileGenerator(ctx.work_folder)

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

                # Добавляем строку через генератор
                sales_gen.add_sale_row(
                    from_seller_name=seller_brand.name,
                    to_seller_name=owner_seller.name,
                    raw_kiz=kiz if kiz is not None else "",
                    owner_company=owner_company,
                    to_seller_inn=owner_seller.inn,
                    brand=brand,
                    product_name=product_name if product_name is not None else ""
                )

            # Удаляем пустые файлы
            ctx.log("\n--- ПРОВЕРКА ФАЙЛОВ ПРОДАЖ ---")
            removed = sales_gen.remove_empty_files()
            for file_path in sales_gen.get_created_files():
                ctx.log(f"  Файл сохранён: {file_path.name}")

            if removed:
                ctx.log(f"  Удалено пустых файлов: {removed}")

            # Логируем статистику
            ctx.log("\n--- СТАТИСТИКА ПРОДАЖ ---")
            stats = sales_gen.get_stats()
            if stats:
                for (from_seller, to_seller), count in sorted(stats.items()):
                    ctx.log(f"  {from_seller} → {to_seller}: {count} КИЗов")
            else:
                ctx.log("  Нет строк для передачи между продавцами")

            ctx.log("Подготовка передач завершена.\n")

        except Exception as e:
            ctx.log(f"Ошибка подготовки передач КИЗов: {e}")
        finally:
            wb_src.close()