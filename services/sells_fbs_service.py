from PySide6.QtWidgets import QDialog
from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.price_utils import PriceUtils
from utils.kiz_utils import KizUtils
from utils.sales_file_generator import SalesFileGenerator

class PreparationService:
    """Сервис подготовки: копирование файлов ЧЗ МП и отчётов МП в рабочую папку."""

    def __init__(self, kiz_validator):
        self.kiz_validator = kiz_validator

    def prepare(self, target_dir, fbs_files=None, mp_files=None, sellers=None, log_callback=None):
        if sellers is None:
            sellers = []

        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_подготовка.txt", log_callback)
        ctx.log(f"=== Подготовка от {ctx.today.strftime('%d.%m.%Y %H:%M')} ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        self._copy_fbs_files(ctx, fbs_files or [])
        self._copy_mp_files(ctx, mp_files or [], sellers)

        ctx.log("Подготовка завершена.")
        # очистка устаревших записей КИЗов
        # set_log_path — чтобы KizStorage логировал в рабочую папку прогона
        self.kiz_validator.set_log_path(ctx.work_folder)
        # load() обязателен: clean_old_entries работает с _data,
        # а он пуст, пока не загружен с диска
        self.kiz_validator.load()
        # Удаляем записи старше 1 месяца
        deleted = self.kiz_validator.clean_old_entries(months=1)
        ctx.log(f"Очистка старых записей: удалено {deleted}.")

    # ---------- Приватные методы ----------
    def _copy_fbs_files(self, ctx: TaskContext, fbs_files):
        if not fbs_files:
            return
        for i, src in enumerate(fbs_files):
            src_path = Path(src)
            if i == 0:
                new_name = ctx.format_filename("ЧЗ_МП_{date}")
            else:
                new_name = ctx.format_filename(f"ЧЗ_МП_{{date}}_{i + 1}")
            dst = ctx.work_folder / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, ctx,
                description="ЧЗ МП",
                overwrite=False
            )

    def _copy_mp_files(self, ctx: TaskContext, mp_files, sellers):
        if not mp_files:
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
                    new_name = ctx.format_filename(f"ОТЧЁТ МП ПО {found_seller.name} {{date}}")
                else:
                    new_name = ctx.format_filename(f"ОТЧЁТ МП ПО {found_seller.name} {{date}}_{idx}")
            else:
                new_name = src_path.name
                ctx.log(f"Не удалось определить продавца для: {src_path.name}")

            dst = ctx.work_folder / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, ctx,
                description="отчёт",
                overwrite=False
            )

    def _determine_seller_for_mp_file(self, file_name_lower: str, sellers):
        for seller in sellers:
            if any(key.lower() in file_name_lower for key in seller.keys):
                return seller
        return None

class ExportKizService:
    """Сервис выгрузки КИЗов из ЧЗ_МП и отчётов МП в текстовые файлы с валидацией."""

    def __init__(self, kiz_validator):
        self.kiz_validator = kiz_validator

    def export(self, target_dir, sellers, log_callback=None):
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_выгрузка_кизов.txt", log_callback)
        ctx.log("=== ВЫГРУЗКА КИЗОВ В ТЕКСТОВЫЕ ФАЙЛЫ (с валидацией и очисткой) ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        self.kiz_validator.set_log_path(ctx.work_folder)
        self.kiz_validator.load()

        kiz_by_seller = {seller.name: set() for seller in sellers}

        # NEW: единый батч на оба цикла. Все вызовы validate_for_sale внутри
        # накапливают изменения в памяти; финальный save() — на выходе из with.
        # Промежуточные save() каждые BATCH_SAVE_THRESHOLD изменений добавляет
        # сам KizStorage.add_or_update — здесь об этом не думаем.
        with self.kiz_validator.batch():
            # ------------------------------------------------------------
            # 1. Обработка ЧЗ_МП
            # ------------------------------------------------------------
            chz_files = FileHelper.find_files_by_pattern(ctx.work_folder, "ЧЗ_МП*.xlsx")
            for chz_path in chz_files:
                # NEW: ошибка на одном файле не должна прерывать обработку
                # остальных — логируем и переходим к следующему файлу.
                # Накопленные изменения сохранятся на выходе из батча.
                try:
                    ctx.log(f"\nОбработка ЧЗ_МП: {chz_path.name}")
                    wb = ExcelHelper.open_workbook_with_ctx(
                        chz_path, ctx, description="ЧЗ_МП",
                        read_only=True, data_only=True
                    )
                    if wb is None:
                        continue
                    try:
                        for sheet_name in wb.sheetnames:
                            seller = ExcelHelper.find_seller_by_sheet_name(wb, sellers, sheet_name)
                            if seller is None:
                                ctx.log(f"  Лист '{sheet_name}' не соответствует ни одному продавцу – пропущен")
                                continue
                            sheet = wb[sheet_name]
                            raw_kiz_list = ExcelHelper.read_column_values(sheet, col_index=1, start_row=1)
                            for raw_kiz in raw_kiz_list:
                                full_cleaned_list = KizUtils.clean_kiz_full(raw_kiz)
                                if not full_cleaned_list:
                                    ctx.log(f"    ⚠️ Некорректный КИЗ (очистка не дала результатов): {raw_kiz[:50]}...")
                                    continue
                                for full_kiz in full_cleaned_list:
                                    storage_list = KizUtils.clean_kiz_for_storage(full_kiz)
                                    if not storage_list:
                                        continue
                                    storage_kiz = storage_list[0]  # обычно один
                                    if self.kiz_validator.validate_for_sale(storage_kiz):
                                        kiz_by_seller[seller.name].add(full_kiz)   # сохраняем полный для txt
                            ctx.log(f"  Лист '{sheet_name}' → продавец '{seller.name}': обработано {len(raw_kiz_list)} записей")
                    finally:
                        if wb:
                            wb.close()
                except Exception as e:
                    ctx.log(f"Ошибка обработки файла {chz_path.name}: {e}")
                    continue

            # ------------------------------------------------------------
            # 2. Обработка отчётов МП (с датами из листа "Сборочные задания")
            # ------------------------------------------------------------
            mp_files = FileHelper.find_files_by_pattern(ctx.work_folder, "ОТЧЁТ МП ПО *.xlsx")
            for mp_path in mp_files:
                # NEW: тот же принцип — одна ошибка на файле, продолжаем со следующего
                try:
                    ctx.log(f"\nОбработка отчёта МП: {mp_path.name}")

                    found_seller = None
                    for seller in sellers:
                        if any(key.lower() in mp_path.stem.lower() for key in seller.keys):
                            found_seller = seller
                            ctx.log(f"  Удалось определить продавца из имени файла {mp_path} - {found_seller}")
                            break
                    if found_seller is None:
                        ctx.log(f"  Не удалось определить продавца из имени файла – пропущен")
                        continue
                    seller = found_seller

                    wb = ExcelHelper.open_workbook_with_ctx(
                        mp_path, ctx, description="отчёт МП",
                        read_only=True, data_only=True
                    )
                    if wb is None:
                        continue

                    try:
                        if "КИЗ" not in wb.sheetnames:
                            ctx.log(f"  Лист 'КИЗ' отсутствует – пропущен")
                            continue
                        sheet_kiz = wb["КИЗ"]
                        kiz_to_task = {}
                        for row in sheet_kiz.iter_rows(min_row=2, values_only=True):
                            if len(row) >= 9:  # как минимум до столбца I
                                task_num = row[0]  # столбец A
                                kiz = row[2]  # столбец C
                                operation_type = row[8]  # столбец I (тип операции)
                                if kiz and task_num and operation_type and str(operation_type).strip().upper() == "ПРОДАЖА":
                                    kiz_to_task[str(kiz).strip()] = str(task_num).strip()
                                else:
                                    ctx.log(f"  Пропущен КИЗ {kiz} (задание {task_num}) – тип операции '{operation_type}'")

                        if "Сборочные задания" not in wb.sheetnames:
                            ctx.log(f"  Лист 'Сборочные задания' отсутствует – даты не будут загружены, используем сегодняшнюю")
                            task_to_date = {}
                        else:
                            sheet_tasks = wb["Сборочные задания"]
                            task_to_date = {}
                            for row in sheet_tasks.iter_rows(min_row=2, values_only=True):
                                if len(row) >= 4:
                                    task_num = row[0]
                                    date_created = row[3]
                                    if task_num and date_created:
                                        task_to_date[str(task_num).strip()] = str(date_created).strip()

                        for raw_kiz, task_num in kiz_to_task.items():
                            full_cleaned_list = KizUtils.clean_kiz_full(raw_kiz)
                            if not full_cleaned_list:
                                ctx.log(f"    ⚠️ Некорректный КИЗ (очистка не дала результатов): {raw_kiz[:50]}...")
                                continue
                            for full_kiz in full_cleaned_list:
                                storage_list = KizUtils.clean_kiz_for_storage(full_kiz)
                                if not storage_list:
                                    continue
                                storage_kiz = storage_list[0]
                                sale_date_str = task_to_date.get(task_num)
                                if sale_date_str is None:
                                    ctx.log(f"  ⚠️ Для КИЗа {storage_kiz} (задание {task_num}) не найдена дата. Использую сегодняшнюю.")
                                    if self.kiz_validator.validate_for_sale(storage_kiz):
                                        kiz_by_seller[seller.name].add(full_kiz)
                                else:
                                    if self.kiz_validator.validate_for_sale(storage_kiz, sale_date_str):
                                        kiz_by_seller[seller.name].add(full_kiz)

                        ctx.log(f"  Добавлено {len(kiz_to_task)} записей для продавца '{seller.name}'")
                    finally:
                        if wb:
                            wb.close()
                except Exception as e:
                    ctx.log(f"Ошибка обработки файла {mp_path.name}: {e}")
                    continue

        # ------------------------------------------------------------
        # 3. Сохранение текстовых файлов — ВНЕ батча.
        # .txt-файлы не связаны с used_kiz.json, поэтому их запись
        # не должна зависеть от финального save() KizStorage.
        # ------------------------------------------------------------
        ctx.log("\n--- СОХРАНЕНИЕ ТЕКСТОВЫХ ФАЙЛОВ ---")
        for seller_name, kiz_set in kiz_by_seller.items():
            if not kiz_set:
                ctx.log(f"  {seller_name}: нет КИЗов – файл не создан")
                continue
            txt_path = ctx.work_folder / f"{seller_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                for kiz in sorted(kiz_set):
                    f.write(kiz + "\n")
            ctx.log(f"  {seller_name}: сохранено {len(kiz_set)} КИЗов в {txt_path.name}")

        ctx.log("\n=== ВЫГРУЗКА ЗАВЕРШЕНА ===")

class FilterPreFinalService:
    """Сервис фильтрации предитоговых файлов по статусу и владельцу."""

    def filter_files(self, target_dir, sellers, log_callback=None):
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_фильтрация.txt", log_callback)
        ctx.log("=== ФИЛЬТРАЦИЯ ПРЕДИТОГОВЫХ ФАЙЛОВ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        allowed_companies = TextUtils.get_allowed_companies(sellers)

        for seller in sellers:
            file_path = ctx.work_folder / f"{seller.name}.xlsx"
            if not file_path.is_file():
                ctx.log(f"Файл для продавца '{seller.name}' не найден – пропущен")
                continue

            ctx.log(f"\nОбработка файла: {file_path.name}")
            wb = ExcelHelper.open_workbook_with_ctx(file_path, ctx, description="предитоговый файл", read_only=False, data_only=True)
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    ctx.log("  Файл пуст (только заголовки) – пропущен")
                    continue

                # Сохраняем заголовки
                headers = [cell.value for cell in sheet[1]]

                # Фильтруем строки
                filtered_rows, stats = ExcelHelper.filter_and_clean_rows(
                    sheet,
                    status_col=4,          # столбец D
                    owner_col=12,          # столбец L
                    allowed_owners=allowed_companies,
                    required_status="В ОБОРОТЕ"
                )

                # Логируем статистику
                ctx.log(f"  Всего строк: {sheet.max_row - 1}")
                if stats['status']:
                    ctx.log("  Удалено по статусу:")
                    for status, count in sorted(stats['status'].items(), key=lambda x: x[0].lower()):
                        ctx.log(f"    Статус '{status}': {count} строк")
                if stats['owner']:
                    ctx.log("  Удалено по владельцу:")
                    for owner, count in sorted(stats['owner'].items(), key=lambda x: x[0].lower()):
                        ctx.log(f"    Владелец '{owner}': {count} строк")
                ctx.log(f"  Сохранено: {stats['total_kept']} строк")

                # Перезаписываем файл
                if stats['total_kept'] == 0:
                    ctx.log("  Нет строк для сохранения – файл будет очищен (только заголовки)")
                    # Создаём новую книгу только с заголовками
                    new_wb, new_sheet = ExcelHelper.create_workbook_with_headers(headers, sheet_name=sheet.title)
                    new_wb.save(file_path)
                    new_wb.close()
                else:
                    # Создаём новую книгу и записываем заголовки + отфильтрованные строки
                    new_wb, new_sheet = ExcelHelper.create_workbook_with_headers(headers, sheet_name=sheet.title)
                    for _, row_values in filtered_rows:
                        new_sheet.append(row_values)
                    new_wb.save(file_path)
                    new_wb.close()

            except Exception as e:
                ctx.log(f"  Ошибка обработки файла: {e}")
            finally:
                wb.close()

        ctx.log("\n=== ФИЛЬТРАЦИЯ ЗАВЕРШЕНА ===")

class GenerateSalesService:
    """Сервис формирования файлов продаж на основе владельца (company) КИЗов."""

    def generate(self, target_dir, sellers, log_callback=None):
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_продажи.txt", log_callback)
        ctx.log("=== ФОРМИРОВАНИЕ ФАЙЛОВ ПРОДАЖ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        # Создаём генератор файлов продаж
        sales_gen = SalesFileGenerator(ctx.work_folder)

        for seller in sellers:
            file_path = ctx.work_folder / f"{seller.name}.xlsx"
            if not file_path.is_file():
                ctx.log(f"Файл для продавца '{seller.name}' не найден – пропущен")
                continue

            ctx.log(f"\nОбработка файла: {file_path.name}")
            wb = ExcelHelper.open_workbook_with_ctx(file_path, ctx, description="предитоговый файл", read_only=True, data_only=True)
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    ctx.log("  Файл пуст (только заголовки) – пропущен")
                    continue

                for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                    if len(row) < 12:
                        continue

                    kiz = str(row[1]).strip() if row[1] is not None else ""       # столбец B
                    owner_company = str(row[11]).strip() if row[11] is not None else ""   # столбец L
                    brand = str(row[6]).strip() if row[6] is not None else ""     # столбец G
                    product_name = str(row[5]).strip() if row[5] is not None else ""  # столбец F

                    if not kiz or not owner_company:
                        ctx.log(f"  ⚠️ Строка {row_idx}: Нет КИЗа или Владельца")
                        continue

                    # Находим продавца по company (владельцу)
                    owner_seller = TextUtils.find_seller_by_company(owner_company, sellers)
                    if owner_seller is None:
                        ctx.log(f"  ⚠️ Строка {row_idx}: владелец '{owner_company}' не найден среди продавцов – пропущена")
                        continue

                    # Если владелец совпадает с текущим продавцом – пропускаем
                    if owner_seller.name == seller.name:
                        continue

                    # Добавляем строку через генератор
                    sales_gen.add_sale_row(
                        from_seller_name=owner_seller.name,
                        to_seller_name=seller.name,
                        to_seller_inn=seller.inn,
                        product_name=product_name,
                        raw_kiz=kiz,  # сырой КИЗ
                        owner_company=owner_company,
                        brand=brand
                    )

            finally:
                wb.close()

        # ---- УДАЛЕНИЕ ПУСТЫХ ФАЙЛОВ ПРОДАЖ ----
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

        ctx.log("\n=== ФОРМИРОВАНИЕ ПРОДАЖ ЗАВЕРШЕНО ===")

class FinalizePricesService:
    """Сервис внесения цен из отчётов МП и финализации итоговых файлов."""


    def finalize(self, target_dir, sellers, saved_prices=None, log_callback=None):
        if saved_prices is None:
            saved_prices = {}

        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_цены.txt", log_callback)
        ctx.log("=== ВНЕСЕНИЕ ЦЕН И ФИНАЛИЗАЦИЯ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")
        self.kiz_validator.set_log_path(ctx.work_folder)
        self.kiz_validator.load()
        for seller in sellers:
            # ---- 1. Загрузка цен из отчёта МП ----
            price_map = {}
            prices_list = []
            average_price = None
            mp_files = FileHelper.find_files_by_pattern(ctx.work_folder, f"ОТЧЁТ МП ПО {seller.name}*.xlsx")
            if mp_files:
                mp_path = mp_files[0]
                ctx.log(f"\nЗагрузка цен из отчёта: {mp_path.name}")
                wb_mp = ExcelHelper.open_workbook_with_ctx(mp_path, ctx, description="отчёт МП", read_only=True, data_only=True)
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
                                ctx.log(f"  Загружено {len(prices_list)} цен, новая средняя: {average_price}")
                            else:
                                ctx.log("  В отчёте не найдено ни одной цены")
                        else:
                            ctx.log("  Лист 'КИЗ' отсутствует – цены не загружены")
                    finally:
                        wb_mp.close()
            else:
                ctx.log(f"\nОтчёт МП для продавца '{seller.name}' не найден – цены не загружены")

            # ---- 2. Если средняя цена не определена, запрашиваем у пользователя ----
            if average_price is None:
                # Используем сохранённую, если есть
                if saved_prices.get(seller.name):
                    average_price = saved_prices[seller.name]
                    ctx.log(f"  Использую сохранённую цену: {average_price}")
                else:
                    # Вызываем диалог ввода
                    from ui.windows.shared_dialogs import AveragePriceInputDialog
                    dialog = AveragePriceInputDialog(self, seller.name)
                    if dialog.exec_() == QDialog.Accepted:
                        average_price = dialog.get_price()
                        saved_prices[seller.name] = average_price
                        ctx.log(f"  Пользователь ввёл цену: {average_price}")
                    else:
                        ctx.log(f"  ⚠️ Пользователь отменил ввод для продавца '{seller.name}' – пропускаем")
                        continue

            # ---- 3. Обработка предитогового файла ----
            file_path = ctx.work_folder / f"{seller.name}.xlsx"
            if not file_path.is_file():
                ctx.log(f"Файл для продавца '{seller.name}' не найден – пропущен")
                continue

            ctx.log(f"\nОбработка файла: {file_path.name}")
            wb = ExcelHelper.open_workbook_with_ctx(file_path, ctx, description="предитоговый файл", read_only=False, data_only=True)
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    ctx.log("  Файл пуст (только заголовки) – пропущен")
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

                ctx.log(f"  Установлено цен из отчёта: {from_report_count}")
                ctx.log(f"  Сгенерировано цен по средней: {generated_count}")

                # ---- Сохранение и переименование ----
                wb.save(file_path)
                wb.close()

                new_name = ctx.format_filename(f"ИТОГ {seller.name} {{date}}")
                new_path = ctx.work_folder / new_name
                file_path.rename(new_path)
                ctx.log(f"  Файл переименован в {new_path.name}")

                # Сохраняем среднюю цену
                saved_prices[seller.name] = average_price

                # Дополнительное сохранение (на случай, если rename сбросил изменения)
                wb = ExcelHelper.open_workbook_with_ctx(new_path, ctx, description="итоговый файл", read_only=False, data_only=True)
                if wb:
                    wb.save(new_path)
                    wb.close()

            except Exception as e:
                ctx.log(f"  Ошибка обработки файла: {e}")
            finally:
                if wb:
                    wb.close()

        ctx.log("\n=== ФИНАЛИЗАЦИЯ ЗАВЕРШЕНА ===")
        return saved_prices