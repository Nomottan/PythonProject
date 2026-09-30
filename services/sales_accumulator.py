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

import shutil
from pathlib import Path
from datetime import date

from utils.context import TaskContext
from utils.file_helper import FileHelper
from utils.excel_helper import ExcelHelper
from utils.sales_file_generator import SalesFileKizReader, KizFilterDetailsWriter


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

    # Индекс столбца с КИЗом (0-based): [Наименование, КИЗ, GTIN, Цена].
    KIZ_COLUMN_INDEX = 1

    def __init__(self, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.

        Роль: сохраняет ссылку. Логгеры создаются в начале
              accumulate, когда известна рабочая папка.
        """
        self._log_manager_v2 = log_manager_v2

    def accumulate(self, target_dir: str) -> None:
        """Аккумулирует файлы продаж из ЧЗ_МП и Возвратов в одну папку.

        Вход: target_dir — корневая папка задачи.
        Выход: нет.

        Роль:
            Создаёт TaskContext (только пути) и LoggerV2. Сначала
            обрабатывает ЧЗ_МП (приоритет), затем Возвраты с
            фильтрацией по КИЗам из ЧЗ_МП. Ведёт детальный лог
            фильтрации отдельным логгером.
        """
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        base_path = Path(target_dir) / date_str

        chz_folder = base_path / f"ЧЗ_МП_{date_str}" / "Продажи"
        returns_folder = base_path / f"Возвраты_{date_str}" / "Продажи"

        # TaskContext — только пути. Логирование — через LoggerV2.
        ctx = TaskContext(
            target_dir,
            "Продажи_{date}",
            "log_аккумуляция.txt",
            subfolders=["Логи"],
        )
        logger = self._log_manager_v2.create_logger_v2(
            source="SalesAccumulatorService.sales_accumulator",
            domain="sales",
            work_folder=ctx.logs_dir,
            log_filename="log_аккумуляция.txt",
        )

        sales_folder = ctx.work_folder
        logger.report("=== АККУМУЛЯЦИЯ ПРОДАЖ (приоритет ЧЗ_МП) ===")
        logger.report(f"Рабочая папка: {sales_folder}")

        # ---- 1. ЧЗ_МП (первая, приоритетная) ----
        kiz_from_fbs = self._process_chz(
            chz_folder, sales_folder, logger,
        )

        # ---- 2. Возвраты (фильтрация + детали) ----
        details = self._process_returns(
            returns_folder, sales_folder, kiz_from_fbs, logger,
        )

        # Детальный лог фильтрации КИЗов — отдельным логгером.
        if details["files"]:
            KizFilterDetailsWriter.write(
                details, ctx.logs_dir, self._log_manager_v2,
            )
            logger.report(
                "  Детальный лог фильтрации КИЗов сохранён в "
                "log_фильтрация_КИЗов.txt"
            )

        logger.report("\n=== АККУМУЛЯЦИЯ ЗАВЕРШЕНА ===")

    # ---------- Приватные методы-оркестраторы ----------

    def _process_chz(self, chz_folder: Path, sales_folder: Path,
                     logger) -> set:
        """Обрабатывает файлы ЧЗ_МП: копирует и собирает КИЗы.

        Вход:
            chz_folder — папка «ЧЗ_МП_{date}/Продажи».
            sales_folder — целевая папка аккумуляции.
            logger — LoggerV2.

        Выход:
            set[str] — множество всех КИЗов из ЧЗ_МП.

        Роль:
            Копирует каждый файл без фильтрации (приоритетный
            источник), собирает множество КИЗов для последующей
            фильтрации Возвратов.
        """
        chz_files = FileHelper.find_sales_files(chz_folder)
        kiz_from_fbs = set()

        logger.report("\n--- ОБРАБОТКА ЧЗ_МП ---")
        for src_path in chz_files:
            dst_path = sales_folder / src_path.name
            shutil.copy2(src_path, dst_path)
            kiz_set = SalesFileKizReader.read(dst_path)
            kiz_from_fbs.update(kiz_set)
            logger.report(
                f"  Скопирован: {src_path.name} "
                f"(КИЗов: {len(kiz_set)})"
            )
        return kiz_from_fbs

    def _process_returns(self, returns_folder: Path, sales_folder: Path,
                         kiz_from_fbs: set, logger) -> dict:
        """Обрабатывает файлы Возвратов с фильтрацией по КИЗам ЧЗ_МП.

        Вход:
            returns_folder — папка «Возвраты_{date}/Продажи».
            sales_folder — целевая папка аккумуляции.
            kiz_from_fbs — множество КИЗов из ЧЗ_МП.
            logger — LoggerV2.

        Выход:
            dict {"kiz_from_fbs": set, "files": [...]} — данные для
            детального лога фильтрации.

        Роль:
            Для каждого файла: считает КИЗы, отделяет дубликаты,
            при необходимости вызывает ExcelHelper для записи
            отфильтрованных строк. Собирает данные для лога.
        """
        returns_files = FileHelper.find_sales_files(returns_folder)
        logger.report(
            "\n--- ОБРАБОТКА ВОЗВРАТОВ "
            "(фильтрация по КИЗам из ЧЗ_МП) ---"
        )

        details = {
            "kiz_from_fbs": kiz_from_fbs,
            "files": [],
        }

        for src_path in returns_files:
            dst_path = sales_folder / src_path.name
            src_kiz_set = SalesFileKizReader.read(src_path)
            duplicates = src_kiz_set & kiz_from_fbs
            filtered = src_kiz_set - kiz_from_fbs

            details["files"].append({
                "name": src_path.name,
                "total": len(src_kiz_set),
                "duplicates": duplicates,
                "filtered": filtered,
            })

            if not filtered:
                logger.report(
                    f"  Пропущен {src_path.name}: все КИЗы уже есть "
                    f"в ЧЗ_МП (всего {len(src_kiz_set)}, "
                    f"дубликатов {len(duplicates)})"
                )
                continue

            rows_added = ExcelHelper.copy_rows_by_column_value(
                src_path=src_path,
                dst_path=dst_path,
                column_index=self.KIZ_COLUMN_INDEX,
                allowed_values=filtered,
                append=dst_path.exists(),
            )

            if dst_path.exists() and rows_added >= 0:
                # Файл был до этой итерации — дописывали.
                action = "Дополнен"
            else:
                action = "Создан новый файл"

            # Различаем в логе: до вызова dst_path.exists() уже
            # проверяли — но после append=True файл точно был.
            # Логируем по факту: append определяли до вызова.
            logger.report(
                f"  {action} {dst_path.name}: добавлено "
                f"{rows_added} строк (всего КИЗов {len(src_kiz_set)}, "
                f"из них добавлено {len(filtered)})"
            )

        return details
