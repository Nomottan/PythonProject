import shutil
import openpyxl
from pathlib import Path
from datetime import date
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils

class SalesAccumulatorService:
    """Сервис аккумуляции файлов продаж из двух папок в одну общую."""

    def accumulate(self, target_dir: str, first_folder: str, log_callback=None):
        """
        Аккумулирует файлы продаж из папок ЧЗ_МП и Возвраты в папку Продажи.
        Приоритет отдаётся файлам из ЧЗ_МП (Sells_FBS):
          - если КИЗ присутствует в ЧЗ_МП, то строки из Возвратов с этим КИЗом игнорируются.
        Параметр first_folder игнорируется (всегда сначала ЧЗ_МП).
        """
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        base_path = Path(target_dir) / date_str

        chz_folder = base_path / f"ЧЗ_МП_{date_str}"
        returns_folder = base_path / f"Возвраты_{date_str}"
        sales_folder = base_path / f"Продажи_{date_str}"

        ctx = TaskContext(target_dir, "Продажи_{date}", "log_аккумуляция.txt", log_callback)
        sales_folder.mkdir(parents=True, exist_ok=True)

        ctx.log("=== АККУМУЛЯЦИЯ ПРОДАЖ (приоритет ЧЗ_МП) ===")
        ctx.log(f"Рабочая папка: {sales_folder}")

        # 1. Обработка ЧЗ_МП (первая, приоритетная)
        chz_files = self._find_sales_files(chz_folder)
        kiz_from_fbs = set()  # множество КИЗов из ЧЗ_МП

        ctx.log(f"\n--- ОБРАБОТКА ЧЗ_МП ---")
        for src_path in chz_files:
            dst_path = sales_folder / src_path.name
            shutil.copy2(src_path, dst_path)
            kiz_set = self._collect_kiz_set(dst_path)
            kiz_from_fbs.update(kiz_set)
            ctx.log(f"  Скопирован: {src_path.name} (КИЗов: {len(kiz_set)})")

        # 2. Обработка Возвратов (с фильтрацией)
        returns_files = self._find_sales_files(returns_folder)
        ctx.log(f"\n--- ОБРАБОТКА ВОЗВРАТОВ (фильтрация по КИЗам из ЧЗ_МП) ---")
        for src_path in returns_files:
            dst_path = sales_folder / src_path.name
            # Собираем КИЗы из текущего файла возвратов
            src_kiz_set = self._collect_kiz_set(src_path)
            # Фильтруем: оставляем только те КИЗы, которых нет в kiz_from_fbs
            filtered_kiz = src_kiz_set - kiz_from_fbs
            if not filtered_kiz:
                ctx.log(f"  Пропущен {src_path.name}: все КИЗы уже есть в ЧЗ_МП")
                continue

            # Если целевой файл уже существует (из ЧЗ_МП), дополняем его
            if dst_path.exists():
                # Читаем все строки из dst, чтобы не потерять данные
                wb_dst = openpyxl.load_workbook(dst_path)
                sheet_dst = wb_dst.active
                # Читаем строки из src, фильтруем по filtered_kiz
                wb_src = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
                sheet_src = wb_src.active
                rows_added = 0
                for row in sheet_src.iter_rows(min_row=2, values_only=True):
                    if len(row) >= 1:
                        kiz = str(row[0]).strip() if row[0] else ""
                        if kiz in filtered_kiz:
                            sheet_dst.append(row)
                            rows_added += 1
                wb_dst.save(dst_path)
                wb_dst.close()
                wb_src.close()
                ctx.log(
                    f"  Дополнен {dst_path.name}: добавлено {rows_added} строк (всего КИЗов из возвратов: {len(filtered_kiz)})")
            else:
                # Если файла нет – копируем с фильтрацией
                wb_dst = openpyxl.Workbook()
                sheet_dst = wb_dst.active
                # Копируем заголовки из src (первая строка)
                wb_src = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
                sheet_src = wb_src.active
                header = list(sheet_src.iter_rows(min_row=1, max_row=1, values_only=True))[0]
                sheet_dst.append(header)
                rows_added = 0
                for row in sheet_src.iter_rows(min_row=2, values_only=True):
                    if len(row) >= 1:
                        kiz = str(row[0]).strip() if row[0] else ""
                        if kiz in filtered_kiz:
                            sheet_dst.append(row)
                            rows_added += 1
                wb_dst.save(dst_path)
                wb_dst.close()
                wb_src.close()
                ctx.log(
                    f"  Создан новый файл {dst_path.name}: добавлено {rows_added} строк (всего КИЗов из возвратов: {len(filtered_kiz)})")

        ctx.log("\n=== АККУМУЛЯЦИЯ ЗАВЕРШЕНА ===")

    # ---------- Вспомогательные методы ----------
    def _find_sales_files(self, folder: Path) -> list[Path]:
        """Возвращает список файлов продаж в папке (продажа*.xlsx)."""
        if not folder.exists():
            return []
        return list(folder.glob("продажа*.xlsx"))

    def _collect_kiz_set(self, file_path: Path) -> set:
        """Читает КИЗы из столбца B (индекс 2) и возвращает множество."""
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet = wb.active
            kiz_set = set()
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) >= 2 and row[1]:
                    kiz = str(row[1]).strip()
                    if kiz:
                        kiz_set.add(kiz)
            wb.close()
            return kiz_set
        except Exception:
            return set()

    def _merge_files(self, src_path: Path, dst_path: Path, existing_kiz_set: set, ctx) -> list:
        """
        Дополняет dst_path данными из src_path (пропуская заголовки).
        Возвращает список КИЗов, которые уже существовали (дубликаты).
        """
        duplicates = []
        try:
            wb_src = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
            sheet_src = wb_src.active
            wb_dst = openpyxl.load_workbook(dst_path)
            sheet_dst = wb_dst.active

            # Определяем следующую свободную строку в dst
            next_row = sheet_dst.max_row + 1

            for row in sheet_src.iter_rows(min_row=2, values_only=True):
                if len(row) >= 1:
                    kiz = str(row[0]).strip() if row[0] else ""
                    if kiz and kiz in existing_kiz_set:
                        duplicates.append(kiz)
                    # Добавляем строку (все значения)
                    sheet_dst.append(row)

            wb_dst.save(dst_path)
            wb_src.close()
            wb_dst.close()
            return duplicates
        except Exception as e:
            ctx.log(f"    Ошибка при объединении {src_path.name}: {e}")
            return []

    def _log_duplicates(self, log_path: Path, duplicates: list, ctx):
        """Сохраняет список дубликатов в файл."""
        if not duplicates:
            return
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("Дубликаты КИЗов при аккумуляции продаж\n")
            f.write("=" * 50 + "\n")
            for kiz in sorted(set(duplicates)):
                f.write(f"{kiz}\n")
        ctx.log(f"  Список дубликатов КИЗов сохранён в {log_path.name}")