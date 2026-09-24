"""
Сервисы ЧЗ МП: подготовка файлов, выгрузка КИЗов, фильтрация,
формирование продаж, финализация цен.

Содержит пять сервисов пайплайна:
    PreparationService     — копирование входных файлов в рабочую папку.
    ExportKizService       — выгрузка КИЗов из ЧЗ_МП и отчётов МП.
    FilterPreFinalService  — фильтрация предитоговых файлов.
    GenerateSalesService   — формирование файлов продаж между продавцами.
    FinalizePricesService  — установка цен и финализация ИТОГ-файлов.

Роль в программе:
    Вызываются из ChzMPWindow по кнопкам пайплайна. Каждый сервис
    работает через TaskContext — единую точку рабочей папки и
    логирования. Сервисы независимы: порядок задаёт UI.
"""

from PySide6.QtWidgets import QDialog
from datetime import datetime
from pathlib import Path
from decimal import Decimal
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.price_utils import PriceUtils
from utils.kiz_utils import KizUtils
from utils.sales_file_generator import SalesFileGenerator
from utils.fbs_buferprices import FbsBufferPrices
from services.kiz_validator import ValidationResult, KizValidator
import random

class PreparationService:
    """Сервис подготовки: копирование входных файлов в рабочую папку.

    Роль: создаёт структуру рабочей папки задачи и складывает туда
          исходные файлы — ЧЗ МП и отчёты МП. Оригиналы в источнике
          не трогаются. Заодно чистит устаревшие записи КИЗов
          (старше 1 месяца) через KizValidator.

    Публичный API:
        prepare(target_dir, fbs_files, mp_files, sellers, log_callback).
    """

    def __init__(self, kiz_validator):
        """Конструктор.

                Вход: kiz_validator — KizValidator для очистки старых записей.
                Роль: сохраняет ссылку на валидатор.
                """
        self.kiz_validator = kiz_validator

    def prepare(self, target_dir, fbs_files=None, mp_files=None, sellers=None, log_callback=None):
        """Запускает подготовку.

            Вход:
                target_dir — корневая папка, куда складываются задачи.
                fbs_files — список путей к файлам ЧЗ МП.
                mp_files — список путей к отчётам МП.
                sellers — список Seller (для определения продавца по имени файла).
                log_callback — колбэк для логов.

            Выход: нет.
            Роль: создаёт TaskContext, копирует файлы, чистит старые
                записи КИЗов. Одна точка входа для окна ЧЗ МП.
        """
        if sellers is None:
            sellers = []

        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_подготовка.txt", log_callback,
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.log(f"=== Подготовка от {ctx.today.strftime('%d.%m.%Y %H:%M')} ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        self._copy_fbs_files(ctx, fbs_files or [])
        self._copy_mp_files(ctx, mp_files or [], sellers)

        ctx.log("Подготовка завершена.")
        # очистка устаревших записей КИЗов
        # set_log_path — чтобы KizStorage логировал в рабочую папку прогона
        self.kiz_validator.set_log_path(ctx.logs_dir)
        # load() обязателен: clean_old_entries работает с _data,
        # а он пуст, пока не загружен с диска
        self.kiz_validator.load()
        # Удаляем записи старше 1 месяца
        deleted = self.kiz_validator.clean_old_entries(months=1)
        ctx.log(f"Очистка старых записей: удалено {deleted}.")

    # ---------- Приватные методы ----------
    def _copy_fbs_files(self, ctx: TaskContext, fbs_files):
        """Копирует файлы ЧЗ МП в подпапку Отчёты/.
        Вход: ctx — TaskContext; fbs_files — список путей.
        Роль: первому файлу даёт имя "ЧЗ_МП_{date}", последующим —
              "ЧЗ_МП_{date}_2", "ЧЗ_МП_{date}_3" и т.д.
        """
        if not fbs_files:
            return
        for i, src in enumerate(fbs_files):
            src_path = Path(src)
            if i == 0:
                new_name = ctx.format_filename("ЧЗ_МП_{date}")
            else:
                new_name = ctx.format_filename(f"ЧЗ_МП_{{date}}_{i + 1}")
            dst = ctx.reports_dir / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, ctx,
                description="ЧЗ МП",
                overwrite=False
            )

    def _copy_mp_files(self, ctx: TaskContext, mp_files, sellers):
        """Копирует отчёты МП в подпапку Отчёты/.

            Вход: ctx — TaskContext; mp_files — список путей;
                sellers — список Seller.
            Роль: имя отчёта формируется по имени продавца. Если
                  продавца определить не удалось — файл копируется
                  под исходным именем, и в лог идёт предупреждение.
                  Одноимённые отчёты одного продавца нумеруются.
            """
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

            dst = ctx.reports_dir / new_name
            FileHelper.copy_file_with_log(
                src_path, dst, ctx,
                description="отчёт",
                overwrite=False
            )

    def _determine_seller_for_mp_file(self, file_name_lower: str, sellers):
        """Определяет продавца по имени файла отчёта.

            Вход: file_name_lower — имя файла в нижнем регистре;
                    sellers — список Seller.
            Выход: Seller или None.
            Роль: ищет в имени файла любой из ключей продавца
                    (seller.keys). Возвращает первого совпавшего.
        """
        for seller in sellers:
            if any(key.lower() in file_name_lower for key in seller.keys):
                return seller
        return None

class ExportKizService:
    """Сервис выгрузки КИЗов из ЧЗ_МП и отчётов МП в текстовые файлы.

    Роль: обрабатывает скопированные отчёты — ЧЗ_МП (прямое списание)
          и отчёты МП (продажи с проверкой возвратов). КИЗы валидируются
          через KizValidator и попадают в used_kiz.json. Для каждого
          продавца пишется .txt со списком очищенных полных КИЗов.
          Цены из отчётов МП кладутся в prices_from_mp.json —
          их потом использует FinalizePricesService.

    Публичный API:
        export(target_dir, sellers, log_callback).
    """

    def __init__(self, kiz_validator):
        """Конструктор.
            Вход: kiz_validator — KizValidator для валидации КИЗов.
            Роль: сохраняет ссылку на валидатор.
        """
        self.kiz_validator = kiz_validator

    def export(self, target_dir, sellers, log_callback=None):
        """Запускает выгрузку КИЗов.

                Вход:
                    target_dir — корневая папка задачи.
                    sellers — список Seller.
                    log_callback — колбэк для логов.
                Выход: нет.

                Роль: два больших цикла — ЧЗ_МП и отчёты МП — работают в одном
                batch-контексте KizStorage: накопленные изменения
                сохраняются одним флешем на выходе. По завершении:
                    1) в «Обработке» появляются .txt со списками КИЗов;
                    2) туда же кладётся prices_from_mp.json.
            """
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_выгрузка_кизов.txt", log_callback,
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.log("=== ВЫГРУЗКА КИЗОВ В ТЕКСТОВЫЕ ФАЙЛЫ (с валидацией и очисткой) ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        self.kiz_validator.set_log_path(ctx.logs_dir)
        self.kiz_validator.load()

        kiz_by_seller = {seller.name: set() for seller in sellers}
        prices_by_seller = {seller.name: {} for seller in sellers}
        # NEW: единый батч на оба цикла. Все вызовы validate_for_sale внутри
        # накапливают изменения в памяти; финальный save() — на выходе из with.
        # Промежуточные save() каждые BATCH_SAVE_THRESHOLD изменений добавляет
        # сам KizStorage.add_or_update — здесь об этом не думаем.
        with self.kiz_validator.batch():
            # ------------------------------------------------------------
            # 1. Обработка ЧЗ_МП
            # ------------------------------------------------------------
            chz_files = FileHelper.find_files_by_pattern(ctx.reports_dir, "ЧЗ_МП*.xlsx")
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
                                    result = self.kiz_validator.validate_for_sale(storage_kiz)
                                    if result == ValidationResult.ADDED:
                                        kiz_by_seller[seller.name].add(full_kiz)  # сохраняем полный для txt
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
            mp_files = FileHelper.find_files_by_pattern(ctx.reports_dir, "ОТЧЁТ МП ПО *.xlsx")
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
                        # REPLACE: occurrences вместо kiz_to_task.
                        # {storage_kiz: [(full_kiz, sale_date_str, price_value, task_num), ...]}
                        occurrences = {}
                        skipped_by_type = {}

                        for row in sheet_kiz.iter_rows(min_row=2, values_only=True):
                            if len(row) >= 9:
                                task_num = row[0]
                                raw_kiz = row[2]
                                operation_type = row[8]
                                price_raw = row[4] if len(row) > 4 else None

                                # Фильтр "ПРОДАЖА".
                                if not (raw_kiz and task_num and operation_type and
                                        str(operation_type).strip().upper() == "ПРОДАЖА"):
                                    op_key = str(operation_type).strip() if operation_type else "(пусто)"
                                    skipped_by_type[op_key] = skipped_by_type.get(op_key, 0) + 1
                                    continue

                                full_cleaned_list = KizUtils.clean_kiz_full(raw_kiz, logger=ctx.logger)
                                if not full_cleaned_list:
                                    ctx.log(
                                        f"    ⚠️ Некорректный КИЗ (очистка не дала результатов): {str(raw_kiz)[:50]}...")
                                    continue

                                task_num_str = str(task_num).strip()

                                # Обработка цены.
                                price_value = None
                                try:
                                    price_value = float(price_raw)
                                except (TypeError, ValueError):
                                    pass
                                if price_value is not None and price_value <= 0:
                                    price_value = None

                                for full_kiz in full_cleaned_list:
                                    storage_list = KizUtils.clean_kiz_for_storage(full_kiz, logger=ctx.logger)
                                    if not storage_list:
                                        continue
                                    storage_kiz = storage_list[0]
                                    occurrences.setdefault(storage_kiz, []).append(
                                        (full_kiz, task_num_str, price_value)
                                    )

                        if skipped_by_type:
                            ctx.log("  Пропущено строк по типу операции:")
                            for op_type, count in sorted(skipped_by_type.items(), key=lambda x: x[0].lower()):
                                ctx.log(f"    '{op_type}': {count}")
                        else:
                            ctx.log("  Все строки прошли фильтр по типу операции 'Продажа'")

                            # NEW: загрузка дат продажи из листа "Сборочные задания".
                            # Формат ячейки D: "HH:MM:SS DD.MM.YYYY" или "DD.MM.YYYY".
                            # Если листа нет — работаем с пустым словарём, в
                            # validate_for_sale передастся сегодняшняя дата.
                        if "Сборочные задания" not in wb.sheetnames:
                            ctx.log(
                                "  Лист 'Сборочные задания' отсутствует – даты не будут загружены, используем сегодняшнюю")
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

                        # NEW: обработка сгруппированных по storage_kiz вхождений.
                        added = 0
                        skipped_dup = 0
                        skipped_no_return = 0
                        skipped_date_before_return = 0

                        for storage_kiz, entries in occurrences.items():
                            # REPLACE: task_to_date уже загружена — вычисляем
                            # sale_date_str здесь. У каждой записи свой task_num.
                            def get_sale_date(entry):
                                """Возвращает sale_date_str из task_to_date или None."""
                                task_num = entry[1]
                                return task_to_date.get(task_num)

                            def sort_key(entry):
                                """Ключ сортировки: самая поздняя дата — первая."""
                                dt = KizValidator._parse_date(get_sale_date(entry))
                                return dt or datetime.min

                            entries_sorted = sorted(entries, key=sort_key, reverse=True)
                            chosen = entries_sorted[0]
                            skipped_dup += len(entries) - 1

                            full_kiz, task_num, price_value = chosen
                            sale_date_str = get_sale_date(chosen)

                            # Если дата не найдена или не парсится — today.
                            if sale_date_str is None or KizValidator._parse_date(sale_date_str) is None:
                                sale_date_str = datetime.now().strftime("%d-%m-%Y")

                            result = self.kiz_validator.validate_for_sale(storage_kiz, sale_date_str)

                            if result == ValidationResult.ADDED:
                                kiz_by_seller[seller.name].add(full_kiz)
                                added += 1
                                if price_value is not None:
                                    prices_by_seller[seller.name][storage_kiz] = int(price_value)
                            elif result == ValidationResult.SKIPPED_NO_RETURN:
                                skipped_no_return += 1
                            elif result == ValidationResult.SKIPPED_DATE_BEFORE_RETURN:
                                skipped_date_before_return += 1

                        total_unique = added + skipped_no_return + skipped_date_before_return + skipped_dup

                        ctx.log(f"  Пропущено КИЗов:")
                        ctx.log(f"    нет в одном экземпляре (дубликаты в отчёте): {skipped_dup}")
                        ctx.log(f"    уже проданы без возврата: {skipped_no_return}")
                        ctx.log(f"    дата продажи раньше даты возврата: {skipped_date_before_return}")
                        ctx.log(f"    Итого уникальных КИЗов в отчёте: {total_unique}")
                        ctx.log(f"  Добавлено {added} записей для продавца '{seller.name}'")
                    finally:
                        if wb:
                            wb.close()
                except Exception as e:
                    ctx.log(f"Ошибка обработки файла {mp_path.name}: {e}")
                    continue
        try:
            FbsBufferPrices(ctx.processing_dir).save(prices_by_seller)
            ctx.log(f"  Цены сохранены в {FbsBufferPrices.FILENAME}")
        except (IOError, OSError) as e:
            ctx.log(f"  ⚠️ Не удалось сохранить {FbsBufferPrices.FILENAME}: {e}")
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
            txt_path = ctx.processing_dir/ f"{seller_name}.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                for kiz in sorted(kiz_set):
                    f.write(kiz + "\n")
            ctx.log(f"  {seller_name}: сохранено {len(kiz_set)} КИЗов в {txt_path.name}")

        ctx.log("\n=== ВЫГРУЗКА ЗАВЕРШЕНА ===")

class FilterPreFinalService:
    """Сервис фильтрации предитоговых файлов.

    Роль: для каждого продавца берёт файл из «Обработки» и
          оставляет только строки со статусом «В ОБОРОТЕ» и
          допустимым владельцем (см. TextUtils.get_allowed_companies).
          Файл перезаписывается на месте — дальнейшие шаги пайплайна
          работают с уже очищенными данными.

    Публичный API:
        filter_files(target_dir, sellers, log_callback).
    """

    def filter_files(self, target_dir, sellers, log_callback=None):
        """Запускает фильтрацию.

                Вход:
                    target_dir — корневая папка задачи.
                    sellers — список Seller.
                    log_callback — колбэк для логов.

                Выход: нет.

                Роль: собирает разрешённые компании из sellers, фильтрует
                      строки по статусу (столбец D) и владельцу (столбец L).
                      Пишет статистику в лог. Перезаписывает предитоговый
                      файл — исходник не сохраняется.
                """
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_фильтрация.txt", log_callback,
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.log("=== ФИЛЬТРАЦИЯ ПРЕДИТОГОВЫХ ФАЙЛОВ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        allowed_companies = TextUtils.get_allowed_companies(sellers)

        for seller in sellers:
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
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
    """Сервис формирования файлов продаж.

    Роль: по предитоговым файлам продавцов строит файлы передачи
          КИЗов между продавцами. Владелец КИЗа (company, столбец L)
          определяет отправителя, текущий продавец — получателя.
          Если владелец = текущий продавец, строка пропускается.
          Файлы продаж пишет SalesFileGenerator в подпапку Продажи/,
          пустые файлы в конце удаляются.

    Публичный API:
        generate(target_dir, sellers, log_callback).
    """

    def generate(self, target_dir, sellers, log_callback=None):
        """Запускает формирование файлов продаж.

                Вход:
                    target_dir — корневая папка задачи.
                    sellers — список Seller.
                    log_callback — колбэк для логов.

                Выход: нет.

                Роль: проходит по предитоговым файлам продавцов, для каждой
                      строки определяет отправителя (по company) и получателя
                      (текущий продавец). Итог — файлы передачи между
                      продавцами + лог со статистикой по направлениям.
        """
        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_продажи.txt", log_callback,
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.log("=== ФОРМИРОВАНИЕ ФАЙЛОВ ПРОДАЖ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")

        # Создаём генератор файлов продаж
        sales_gen = SalesFileGenerator(ctx.sales_dir)

        for seller in sellers:
            file_path = ctx.processing_dir  / f"{seller.name}.xlsx"
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
    """Сервис внесения цен и финализации итоговых файлов.

    Роль: для каждого продавца создаёт ИТОГ в корне рабочей папки
          (копия предитогового файла из «Обработки») и заполняет
          цены в три этапа:
            1. Цены из отчёта МП — точное совпадение по КИЗу.
            2. Распределение числовых цен внутри кластеров GTIN.
            3. Генерация по средней для оставшихся нечисловых C.

    Исходник в «Обработке» не изменяется — вся работа идёт с копией.
    """
    def __init__(self, kiz_validator):
        self.kiz_validator = kiz_validator

    def _load_prices_from_json(self, ctx) -> dict:
        """Читает цены из буфера FbsBufferPrices.

        Вход: ctx — TaskContext с processing_dir.
        Выход: dict {seller_name: {storage_kiz: price}} или {} если
               файл не найден / битый.

        Роль: тонкая обёртка над FbsBufferPrices.load() — добавляет
              только логирование в ctx. Ошибки чтения FbsBufferPrices
              глотает и возвращает {}; мы сообщаем об этом в лог.
        """
        data = FbsBufferPrices(ctx.processing_dir).load()
        if not data:
            ctx.log(
                f"  ⚠️ {FbsBufferPrices.FILENAME} не найден или пуст – "
                f"цены не будут применены"
            )
        return data

    @staticmethod
    def _is_numeric(value) -> bool:
        """Проверяет, что значение — число (int, float, Decimal), но не bool.

        Вход: value — значение ячейки.
        Выход: True, если число. False для None, str, bool.

        Роль: используется в этапах 2 и 3 и в _is_processed.
              bool исключён намеренно — в Excel True/False могут
              случайно попасть в C, их нельзя принимать за 1/0.
        """
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float, Decimal))

    def _is_processed(self, path, ctx) -> bool:
        """Проверяет, все ли непустые C в файле числовые.

        Вход:
            path — путь к файлу ИТОГ.
            ctx — TaskContext для логирования.

        Выход: True, если все непустые C числовые; иначе False.

        Роль: если ИТОГ уже создан и обработан ранее, повторно
              его не перезаписываем. Строки без КИЗа и строки
              заголовка пропускаем — они не участвуют.
        """
        wb = ExcelHelper.open_workbook_with_ctx(
            path, ctx, description="проверка итога",
            read_only=False, data_only=True,
        )
        if wb is None:
            return False
        try:
            sheet = wb.active
            if sheet.max_row < 2:
                return False
            for row_idx in range(2, sheet.max_row + 1):
                kiz_cell = sheet.cell(row=row_idx, column=2)
                kiz = (
                    str(kiz_cell.value).strip()
                    if kiz_cell.value is not None else ""
                )
                if not kiz or kiz == "КИЗ":
                    continue
                price_cell = sheet.cell(row=row_idx, column=3)
                if not self._is_numeric(price_cell.value):
                    return False
            return True
        finally:
            wb.close()

    # ---------- Три этапа установки цен ----------

    def _apply_stage1(self, sheet, price_map) -> int:
        """Этап 1: цены из отчёта по КИЗу.

        Вход:
            sheet — открытый лист.
            price_map — dict {kiz: price} из отчёта МП.

        Выход: количество установленных цен.

        Роль: точное совпадение КИЗа. Если КИЗа нет в price_map —
              C не трогаем (там криптохвост от BestMark).
        """
        count = 0
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=2)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == "КИЗ":
                continue
            if kiz in price_map:
                sheet.cell(row=row_idx, column=3).value = price_map[kiz]
                count += 1
        return count

    def _apply_stage2(self, sheet, ctx) -> dict:
        """Этап 2: распределение цен по кластерам GTIN.

        Вход:
            sheet — открытый лист.
            ctx — TaskContext для логирования.

        Выход: dict со статистикой:
            total_clusters      — всего кластеров GTIN;
            processed           — кластеров, где распределяли;
            skipped_no_numeric  — кластеров без числовых цен;
            skipped_all_numeric — кластеров, где всё уже числовое;
            filled_rows         — сколько строк заполнено.

        Роль: в каждом кластере GTIN берём все числовые C и
              распределяем их random.choice по строкам с нечисловым C.
              Если в кластере числовых нет — пропускаем (этап 3
              разберётся позже). Если все числовые — уже готово.
              Строки без GTIN в кластеры не попадают.
        """
        # Шаг 1: строим кластеры {gtin: [row_indexes]}.
        gtin_clusters = {}
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=2)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == "КИЗ":
                continue
            gtin_cell = sheet.cell(row=row_idx, column=8)  # H
            gtin = (
                str(gtin_cell.value).strip()
                if gtin_cell.value is not None else ""
            )
            if not gtin:
                continue
            gtin_clusters.setdefault(gtin, []).append(row_idx)

        # Шаг 2: обрабатываем кластеры.
        stats = {
            "total_clusters": len(gtin_clusters),
            "processed": 0,
            "skipped_no_numeric": 0,
            "skipped_all_numeric": 0,
            "filled_rows": 0,
        }
        for gtin, row_indexes in gtin_clusters.items():
            numeric_values = []
            non_numeric_rows = []
            for row_idx in row_indexes:
                price_cell = sheet.cell(row=row_idx, column=3)
                if self._is_numeric(price_cell.value):
                    numeric_values.append(price_cell.value)
                else:
                    non_numeric_rows.append(row_idx)

            # Нет числовых — распределять нечего, ждём этапа 3.
            if not numeric_values:
                stats["skipped_no_numeric"] += 1
                continue
            # Всё уже числовое — кластер готов.
            if not non_numeric_rows:
                stats["skipped_all_numeric"] += 1
                continue

            # Заполняем нечисловые строки случайной числовой ценой.
            for row_idx in non_numeric_rows:
                sheet.cell(row=row_idx, column=3).value = random.choice(
                    numeric_values
                )
                stats["filled_rows"] += 1
            stats["processed"] += 1

        return stats

    def _apply_stage3(self, sheet, average_price) -> int:
        """Этап 3: добиваем остатки по средней.

        Вход:
            sheet — открытый лист.
            average_price — средняя для генерации.

        Выход: количество сгенерированных цен.

        Роль: проходим по всем строкам. Если C не числовое —
              генерируем цену по средней. Сюда попадают строки
              без GTIN и кластеры, где числовых не было.
        """
        count = 0
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=2)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == "КИЗ":
                continue
            price_cell = sheet.cell(row=row_idx, column=3)
            if not self._is_numeric(price_cell.value):
                price_cell.value = PriceUtils.generate_varied_price(
                    average_price
                )
                count += 1
        return count

    def finalize(self, target_dir, sellers, saved_prices=None, log_callback=None):
        """Финализация цен по продавцам.

        Вход:
            target_dir — корень рабочей папки.
            sellers — список Seller.
            saved_prices — dict {seller_name: средняя}, может быть пуст.
            log_callback — колбэк для логов.

        Выход: обновлённый saved_prices.

        Роль: для каждого продавца:
            1. Определяем среднюю (из отчёта / сохранённую / диалог).
            2. Если ИТОГ уже есть и обработан — пропускаем.
            3. Если исходника в «Обработке» нет — пропускаем.
            4. Копируем исходник в корень как ИТОГ.
            5. Открываем ИТОГ и применяем три этапа.
            6. Сохраняем ИТОГ. Исходник не трогаем.
        """

        if saved_prices is None:
            saved_prices = {}

        ctx = TaskContext(target_dir, "ЧЗ_МП_{date}", "log_цены.txt", log_callback,
                          subfolders=["Логи", "Отчёты", "Обработка", "Продажи"])
        ctx.log("=== ВНЕСЕНИЕ ЦЕН И ФИНАЛИЗАЦИЯ ===")
        ctx.log(f"Рабочая папка: {ctx.work_folder}")
        self.kiz_validator.set_log_path(ctx.logs_dir)
        self.kiz_validator.load()

        # читаем цены из JSON один раз — до цикла по продавцам.
        all_prices = self._load_prices_from_json(ctx)

        for seller in sellers:
            price_map = all_prices.get(seller.name, {})
            prices_list = list(price_map.values())
            average_price = None
            # средняя рассчитывается сразу, если есть цены.
            if prices_list:
                average_price = PriceUtils.calculate_average(
                    saved_prices.get(seller.name), prices_list
                )
                ctx.log(
                    f"\nПродавец '{seller.name}': загружено "
                    f"{len(prices_list)} цен из отчёта, средняя: "
                    f"{average_price}"
                )
            else:
                ctx.log(f"\nПродавец '{seller.name}': в отчётах нет цен – "
                    f"средняя будет определена ниже")

            # ---- 1. Средняя цена ----
            if average_price is None:
                # Сначала — сохранённая цена текущего продавца.
                if saved_prices.get(seller.name):
                    average_price = saved_prices[seller.name]
                    ctx.log(f"  Использую сохранённую цену: {average_price}")
                # Затем — случайная средняя с другого продавца.
                elif saved_prices:
                    average_price = random.choice(list(saved_prices.values()))
                    ctx.log(f"  Использую случайную среднюю с другого "
                        f"продавца: {average_price}")
                # Диалог ввода — крайний случай.
                else:
                    from ui.windows.shared_dialogs import AveragePriceInputDialog
                    dialog = AveragePriceInputDialog(self, seller.name)
                    if dialog.exec_() == QDialog.Accepted:
                        average_price = dialog.get_price()
                        saved_prices[seller.name] = average_price
                        ctx.log(f"  Пользователь ввёл цену: {average_price}")
                    else:
                        ctx.log(f"  ⚠️ Пользователь отменил ввод для продавца '{seller.name}' – пропускаем")
                        continue

            # ---- 2. Проверка существующего ИТОГа ----
            new_name = ctx.format_filename(f"ИТОГ {seller.name} {{date}}")
            new_path = ctx.work_folder / new_name

            if new_path.is_file() and self._is_processed(new_path, ctx):
                ctx.log(
                    f"\nИТОГ {seller.name} уже создан и обработан "
                    f"ранее – пропускаем."
                )
                saved_prices[seller.name] = average_price
                continue

            # ---- 3. Обработка предитогового файла ----
            file_path = ctx.processing_dir / f"{seller.name}.xlsx"
            if not file_path.is_file():
                ctx.log(f"Файл для продавца '{seller.name}' не найден – пропущен")
                continue

            # ---- 4. Копирование в корень как ИТОГ ----
            FileHelper.copy_file_with_log(
                file_path, new_path, ctx,
                description="итоговый файл", overwrite=True
            )
            ctx.log(f"\nФайл скопирован в корень: {new_path.name}")

            # ---- 5. Открытие ИТОГа и применение трёх этапов ----
            wb = ExcelHelper.open_workbook_with_ctx(
                new_path, ctx, description="итоговый файл",
                read_only=False, data_only=True,
            )
            if wb is None:
                continue

            try:
                sheet = wb.active
                if sheet.max_row < 2:
                    ctx.log("  Файл пуст (только заголовки) – пропущен")
                    continue

                # Этап 1 — цены из отчёта.
                stage1_count = self._apply_stage1(sheet, price_map)
                ctx.log(f"  Установлено цен из отчёта: {stage1_count}")

                # Этап 2 — кластеры GTIN.
                stage2_stats = self._apply_stage2(sheet, ctx)
                ctx.log(
                    f"  Кластеров GTIN: {stage2_stats['total_clusters']}"
                )
                ctx.log(
                    f"  Обработано кластеров: {stage2_stats['processed']}"
                )
                ctx.log(
                    f"  Пропущено (нет числовых): "
                    f"{stage2_stats['skipped_no_numeric']}"
                )
                ctx.log(
                    f"  Пропущено (все числовые): "
                    f"{stage2_stats['skipped_all_numeric']}"
                    )
                ctx.log(
                    f"  Установлено цен по кластерам GTIN: "
                    f"{stage2_stats['filled_rows']}"
                )

                # Этап 3 — добиваем остатки по средней.
                stage3_count = self._apply_stage3(sheet, average_price)
                ctx.log(
                    f"  Сгенерировано цен по средней: {stage3_count}"
                )

                # ---- 6. Сохранение ИТОГа ----
                wb.save(new_path)
                ctx.log(f"  Итоговый файл сохранён: {new_path.name}")
                saved_prices[seller.name] = average_price

            except Exception as e:
                ctx.log(f"  Ошибка обработки файла: {e}")
            finally:
                wb.close()

        ctx.log("\n=== ФИНАЛИЗАЦИЯ ЗАВЕРШЕНА ===")
        return saved_prices