from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper
from utils.filename_utils import FilenameUtils
from utils.sales_file_generator import SalesFileGenerator
from utils.report_readers import (
    ReturnsSourceReportReader, ReturnsKizReader, ReturnsTransferReader,
)

class ReturnsPreparationService:
    """Сервис подготовки возвратов.

    Роль:
        Готовит рабочую папку задачи, копирует исходный файл
        возвратов и создаёт отфильтрованный «Возвраты_{date}.xlsx»,
        в котором остаются только строки с компаниями из списка
        продавцов. Разбор Excel — в ReturnsSourceReportReader
        (utils/report_readers.py). Сервис отвечает за:
            - TaskContext и LoggerV2;
            - копирование исходника (через FileHelper, долг);
            - запись .xlsx из headers и rows, полученных от reader'а;
            - логирование статистики.

    Публичный API:
        prepare(target_dir, source_file, sellers=None).
    """

    def __init__(self, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2, фабрика логгеров V2.

        Роль: сохраняет ссылку. Логгер создаётся в начале prepare,
              когда уже известна рабочая папка.
        """
        self._log_manager_v2 = log_manager_v2

    def prepare(self, target_dir, source_file,
                sellers=None) -> None:
        """Запускает подготовку.

        Вход:
            target_dir — корневая папка задачи.
            source_file — путь к исходному файлу возвратов.
            sellers — список Seller. None → пустой список.

        Выход: нет.

        Роль:
            Создаёт TaskContext (только пути и дата), затем
            LoggerV2 с именем файла log_подготовка.txt. Копирует
            исходник, читает его через reader, пишет результат
            в reports_dir/Возвраты_{date}.xlsx.
        """
        if sellers is None:
            sellers = []

        # TaskContext — только пути и дата. Логирование — через LoggerV2.
        ctx = TaskContext(
            target_dir,
            "Возвраты_{date}",
            "log_подготовка.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )

        # Логгер V2 с историческим именем файла.
        logger = self._log_manager_v2.create_logger_v2(
            source="ReturnsPreparationService.returns_service",
            domain="returns",
            work_folder=ctx.logs_dir,
            log_filename="log_подготовка.txt",
        )

        logger.report(
            f"=== Обработка возвратов начата "
            f"{ctx.today.strftime('%d.%m.%Y %H:%M')} ==="
        )
        logger.report(f"Исходный файл: {source_file}")
        logger.report(f"Рабочая папка: {ctx.work_folder}")

        # ensure_file_exists требует ctx — FileHelper пишет через
        # ctx.log. Это долг, но так было и раньше.
        source_path = FileHelper.ensure_file_exists(
            ctx, source_file, "исходный файл"
        )
        if source_path is None:
            return

        # Копия исходника в рабочую папку — тоже через FileHelper
        # (долг). Используем FilenameUtils вместо ctx.format_filename.
        copy_name = FilenameUtils.format_with_extension(
            "Исходные данные возвратов {date}", ctx.date_str
        )
        copy_dest = ctx.reports_dir / copy_name
        if not FileHelper.copy_file_with_log(
            source_path, copy_dest, ctx,
            description="исходный файл", overwrite=True,
        ):
            # FileHelper уже написал причину в ctx.log.
            return

        allowed_companies = TextUtils.get_allowed_companies(sellers)

        # Reader возвращает заголовки, отфильтрованные строки и статистику.
        data = ReturnsSourceReportReader.read(
            source_path, allowed_companies, logger
        )

        # Запись нового файла — ответственность сервиса.
        result_name = FilenameUtils.format_with_extension(
            "Возвраты_{date}", ctx.date_str
        )
        result_path = ctx.reports_dir / result_name
        try:
            wb_new, ws_new = ExcelHelper.create_workbook_with_headers(
                headers=data.headers or [],
                sheet_name="Возвраты",
                write_only=False,
            )
            for row_values in data.rows:
                ws_new.append(row_values)
            wb_new.save(result_path)
            wb_new.close()
            logger.report(f"Создан файл с возвратами: {result_name}")
        except Exception as e:
            logger.critical(
                f"Ошибка сохранения файла {result_name}: {e}",
                can_influence=False,
            )
            return

        # Агрегаты.
        stats = data.stats
        logger.report(f"Скопировано строк: {stats.copied}")
        logger.report(
            f"Пропущено строк (не совпала компания): {stats.skipped}"
        )

        # Статистика по статусам скопированных строк.
        if stats.status_counts:
            logger.report("Статистика по статусам (скопированные строки):")
            for status, count in sorted(
                stats.status_counts.items(), key=lambda x: x[0].lower()
            ):
                logger.report(f"   {status}: {count}")

        # Итоги — на уровне info.
        logger.info(
            f"Всего строк в исходном файле: "
            f"{stats.copied + stats.skipped}"
        )
        logger.info(
            f"Уникальных компаний после фильтрации: "
            f"{len(stats.passed_companies)}"
        )

        if stats.unknown_companies:
            logger.info(
                "Компании из столбца L, не соответствующие ни одному "
                "продавцу (с количеством строк):"
            )
            for company, count in sorted(
                stats.unknown_companies.items(), key=lambda x: x[0].lower()
            ):
                logger.info(f"   {company}: {count}")
        else:
            logger.info("Компаний вне списка не обнаружено.")

        logger.report("Обработка возвратов завершена.\n")


class KizExportService:
    """Сервис выгрузки КИЗов для возврата.

    Роль:
        Для каждой компании, встретившейся в «Возвраты_{date}.xlsx»
        со статусом «ВЫБЫЛ», пишет .txt-файл со списком полных
        КИЗов. Валидация КИЗов и обновление used_kiz.json — в
        ReturnsKizReader (utils/report_readers.py). Сервис
        отвечает за:
            - TaskContext и LoggerV2;
            - поиск файла возвратов в reports_dir;
            - вызов reader'а (batch-контекст внутри reader'а);
            - запись .txt одним open на компанию;
            - логирование агрегатов.

    Публичный API:
        export(target_dir).
    """

    def __init__(self, kiz_validator, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator.
            log_manager_v2 — LogManagerV2.

        Роль: сохраняет ссылки. Логгер создаётся в начале export.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2

    def export(self, target_dir) -> None:
        """Запускает выгрузку КИЗов для возврата.

        Вход:
            target_dir — корневая папка задачи.

        Выход: нет.

        Роль:
            Создаёт TaskContext и LoggerV2, находит
            Возвраты_{date}.xlsx в reports_dir, вызывает reader,
            пишет .txt-файлы по компаниям, логирует агрегаты.
        """
        ctx = TaskContext(
            target_dir,
            "Возвраты_{date}",
            "log_выгрузка_кизов.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )

        # Логгер V2. Source исправлен на KizExportService.
        logger = self._log_manager_v2.create_logger_v2(
            source="KizExportService.returns_service",
            domain="returns",
            work_folder=ctx.logs_dir,
            log_filename="log_выгрузка_кизов.txt",
        )

        logger.report(
            "=== Выгрузка КИЗов для возврата "
            "(с валидацией и очисткой) ==="
        )

        source_file = ctx.reports_dir / FilenameUtils.format_with_extension(
            "Возвраты_{date}", ctx.date_str
        )
        source_file = FileHelper.ensure_file_exists(
            ctx, source_file, "файл возвратов"
        )
        if source_file is None:
            return

        self.kiz_validator.load()

        data = ReturnsKizReader.read(source_file, self.kiz_validator, logger)

        # Запись .txt — по одному open на компанию.
        logger.report("Сохранение текстовых файлов с КИЗами:")
        if data.full_kizs_by_company:
            for company, kiz_list in sorted(
                data.full_kizs_by_company.items(),
                key=lambda x: x[0].lower(),
            ):
                txt_path = ctx.work_folder / f"{company}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    for kiz in kiz_list:
                        f.write(kiz + "\n")
                logger.report(
                    f"  {company}: сохранено {len(kiz_list)} КИЗов "
                    f"в {txt_path.name}"
                )
        else:
            logger.report(
                "  Не найдено ни одного КИЗа, прошедшего валидацию "
                "(со статусом ВЫБЫЛ)."
            )

        # Агрегаты.
        total_returns = (
            data.returns_updated_in_base + data.returns_not_in_base
        )
        logger.info(
            f"Возвраты: обработано {total_returns} "
            f"({data.returns_updated_in_base} обновлено в базе, "
            f"{data.returns_not_in_base} отсутствует в базе — "
            f"запись не создана)."
        )

        kiz_stats = data.kiz_stats or {}
        logger.info(
            f"Обработка КИЗов: успешно {kiz_stats.get('processed', 0)}, "
            f"отброшено коротких {kiz_stats.get('dropped_short', 0)}, "
            f"без '01' {kiz_stats.get('dropped_no_01', 0)}, "
            f"транслитерировано {kiz_stats.get('transliterated', 0)}."
        )

        logger.report("---Выгрузка завершена.---\n")


class KizTransferService:
    """Сервис подготовки КИЗов для передачи между продавцами.

    Роль:
        Формирует файлы продаж по «Возвраты_{date}.xlsx»: для каждой
        строки, где бренд принадлежит одному продавцу, а владелец —
        другому, создаёт запись в файле передачи. Разбор файла и все
        проверки строк — в ReturnsTransferReader
        (utils/report_readers.py). Сервис отвечает за:
            - TaskContext и LoggerV2;
            - поиск «Возвраты_{date}.xlsx» в reports_dir;
            - вызов reader'а;
            - прогон готовых строк через SalesFileGenerator;
            - удаление пустых файлов и логирование итогов.

    Публичный API:
        prepare_transfer(target_dir, sellers).
    """

    def __init__(self, log_manager_v2) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2.

        Роль: сохраняет ссылку. Логгер создаётся в начале
              prepare_transfer.
        """
        self._log_manager_v2 = log_manager_v2

    def prepare_transfer(self, target_dir, sellers) -> None:
        """Запускает подготовку передач КИЗов.

        Вход:
            target_dir — корневая папка задачи.
            sellers — список Seller.

        Выход: нет.

        Роль:
            Создаёт TaskContext и LoggerV2 с именем файла
            log_продажи.txt (историческое имя сохранено).
            SalesFileGenerator создаётся с logger=logger:
            отладочные сообщения уйдут в debug.txt.
        """
        ctx = TaskContext(
            target_dir,
            "Возвраты_{date}",
            "log_продажи.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )

        # Логгер V2 с историческим именем файла.
        logger = self._log_manager_v2.create_logger_v2(
            source="KizTransferService.returns_service",
            domain="returns",
            work_folder=ctx.logs_dir,
            log_filename="log_продажи.txt",
        )

        logger.report(
            f"=== Подготовка передач КИЗов начата "
            f"{ctx.today.strftime('%d.%m.%Y %H:%M')} ==="
        )

        source_file = ctx.reports_dir / FilenameUtils.format_with_extension(
            "Возвраты_{date}", ctx.date_str
        )
        source_file = FileHelper.ensure_file_exists(
            ctx, source_file, "файл возвратов"
        )
        if source_file is None:
            return

        # Генератор продаж — с логгером V2, чтобы debug-сообщения
        # не терялись.
        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)

        # Reader возвращает готовые строки передач и агрегаты.
        data = ReturnsTransferReader.read(source_file, sellers, logger)

        # Прогон готовых строк через генератор — без дополнительных
        # проверок: всё уже проверено в reader'е.
        for transfer in data.rows:
            sales_gen.add_sale_row(
                from_seller_name=transfer.from_seller_name,
                to_seller_name=transfer.to_seller_name,
                to_seller_inn=transfer.to_seller_inn,
                product_name=transfer.product_name,
                raw_kiz=transfer.raw_kiz,
                # REPLACE: раньше передавался seller_brand (Seller),
                # что противоречило контракту параметра owner_company.
                # Теперь передаём исходную строку владельца.
                owner_company=transfer.owner_company_str,
                brand=transfer.brand,
            )

        # Агрегаты по строкам и брендам.
        logger.report(f"Всего строк: {data.total_rows}")
        logger.report(f"Уникальных брендов: {len(data.unique_brands)}")

        # Удаление пустых файлов и лог по созданным.
        logger.report("\n--- ПРОВЕРКА ФАЙЛОВ ПРОДАЖ ---")
        removed = sales_gen.remove_empty_files()
        for file_path in sales_gen.get_created_files():
            logger.report(f"  Файл сохранён: {file_path.name}")
        if removed:
            logger.report(f"  Удалено пустых файлов: {removed}")

        # Статистика по направлениям передач.
        logger.report("\n--- СТАТИСТИКА ПРОДАЖ ---")
        sales_stats = sales_gen.get_stats()
        if sales_stats:
            for (from_seller, to_seller), count in sorted(sales_stats.items()):
                logger.report(
                    f"  {from_seller} → {to_seller}: {count} КИЗов"
                )
        else:
            logger.report("  Нет строк для передачи между продавцами")

        logger.report("Подготовка передач завершена.\n")