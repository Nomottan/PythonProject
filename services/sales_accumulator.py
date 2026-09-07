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

        # 2. Обработка Возвратов (с фильтрацией и сбором деталей)
        returns_files = self._find_sales_files(returns_folder)
        ctx.log(f"\n--- ОБРАБОТКА ВОЗВРАТОВ (фильтрация по КИЗам из ЧЗ_МП) ---")

        # Сбор данных для детального лога
        details = {
            "kiz_from_fbs": kiz_from_fbs,
            "files": []  # список словарей по каждому файлу
        }

        for src_path in returns_files:
            dst_path = sales_folder / src_path.name
            # Собираем КИЗы из текущего файла возвратов
            src_kiz_set = self._collect_kiz_set(src_path)
            # Определяем дубликаты (КИЗы, которые уже есть в ЧЗ_МП)
            duplicates_in_file = src_kiz_set & kiz_from_fbs
            # Фильтруем: оставляем только те КИЗы, которых нет в kiz_from_fbs
            filtered_kiz = src_kiz_set - kiz_from_fbs

            # Сохраняем данные для лога
            file_info = {
                "name": src_path.name,
                "total": len(src_kiz_set),
                "duplicates": duplicates_in_file,
                "filtered": filtered_kiz
            }
            details["files"].append(file_info)

            if not filtered_kiz:
                ctx.log(
                    f"  Пропущен {src_path.name}: все КИЗы уже есть в ЧЗ_МП (всего {len(src_kiz_set)}, дубликатов {len(duplicates_in_file)})")
                continue

            # Если целевой файл уже существует (из ЧЗ_МП), дополняем его
            if dst_path.exists():
                wb_dst = openpyxl.load_workbook(dst_path)
                sheet_dst = wb_dst.active
                wb_src = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
                sheet_src = wb_src.active
                rows_added = 0
                for row in sheet_src.iter_rows(min_row=2, values_only=True):
                    # КИЗ в первом столбце (индекс 0)
                    if len(row) >= 1:
                        kiz = str(row[0]).strip() if row[0] else ""
                        if kiz in filtered_kiz:
                            sheet_dst.append(row)
                            rows_added += 1
                wb_dst.save(dst_path)
                wb_dst.close()
                wb_src.close()
                ctx.log(
                    f"  Дополнен {dst_path.name}: добавлено {rows_added} строк (всего КИЗов {len(src_kiz_set)}, из них добавлено {len(filtered_kiz)})")
            else:
                # Если файла нет – создаём новый с фильтрацией
                wb_dst = openpyxl.Workbook()
                sheet_dst = wb_dst.active
                wb_src = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
                sheet_src = wb_src.active
                header = list(sheet_src.iter_rows(min_row=1, max_row=1, values_only=True))[0]
                sheet_dst.append(header)
                rows_added = 0
                for row in sheet_src.iter_rows(min_row=2, values_only=True):
                    # КИЗ в первом столбце (индекс 0)
                    if len(row) >= 1:
                        kiz = str(row[0]).strip() if row[0] else ""
                        if kiz in filtered_kiz:
                            sheet_dst.append(row)
                            rows_added += 1
                wb_dst.save(dst_path)
                wb_dst.close()
                wb_src.close()
                ctx.log(
                    f"  Создан новый файл {dst_path.name}: добавлено {rows_added} строк (всего КИЗов {len(src_kiz_set)}, из них добавлено {len(filtered_kiz)})")

        # Сохраняем детальный лог
        if details["files"]:
            log_path = sales_folder / "log_фильтрация_КИЗов.txt"
            self._log_kiz_details(log_path, details, ctx)

        ctx.log("\n=== АККУМУЛЯЦИЯ ЗАВЕРШЕНА ===")

    # ---------- Вспомогательные методы ----------
    def _find_sales_files(self, folder: Path) -> list[Path]:
        if not folder.exists():
            return []
        return list(folder.glob("продажа*.xlsx"))

    def _collect_kiz_set(self, file_path: Path) -> set:
        """Читает КИЗы из первого столбца (индекс 0) и возвращает множество."""
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            sheet = wb.active
            kiz_set = set()
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) >= 1 and row[0]:  # первый столбец
                    kiz = str(row[0]).strip()
                    if kiz:
                        kiz_set.add(kiz)
            wb.close()
            return kiz_set
        except Exception:
            return set()

    def _log_kiz_details(self, log_path: Path, details: dict, ctx):
        """Сохраняет детальную информацию о фильтрации КИЗов для каждого файла возвратов."""
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("=== ДЕТАЛИ ФИЛЬТРАЦИИ КИЗОВ ===\n\n")

            f.write("КИЗы из ЧЗ_МП (приоритетные):\n")
            if details["kiz_from_fbs"]:
                for kiz in sorted(details["kiz_from_fbs"]):
                    f.write(f"  {kiz}\n")
            else:
                f.write("  (нет)\n")
            f.write("\n" + "=" * 60 + "\n\n")

            for file_info in details["files"]:
                f.write(f"Файл: {file_info['name']}\n")
                f.write(f"  Всего КИЗов в файле: {file_info['total']}\n")
                f.write(f"  Дубликаты (уже есть в ЧЗ_МП): {len(file_info['duplicates'])}\n")
                if file_info['duplicates']:
                    for kiz in sorted(file_info['duplicates']):
                        f.write(f"    {kiz}\n")
                else:
                    f.write("    (нет)\n")
                f.write(f"  Отфильтрованные (добавлены): {len(file_info['filtered'])}\n")
                if file_info['filtered']:
                    for kiz in sorted(file_info['filtered']):
                        f.write(f"    {kiz}\n")
                else:
                    f.write("    (нет)\n")
                f.write("\n" + "-" * 40 + "\n")

        ctx.log(f"  Детальный лог фильтрации КИЗов сохранён в {log_path.name}")