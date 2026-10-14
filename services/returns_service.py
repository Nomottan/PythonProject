from pathlib import Path
from utils.context import TaskContext
from utils.excel_helper import ExcelHelper
from utils.excel_helper import WorkbookWriter
from utils.txt_helper import TextFileWriter
from utils.text_utils import TextUtils
from utils.file_helper import FileHelper, FilenameUtils
from utils.sales_file_generator import SalesFileGenerator
from utils.returns_readers import (
    ReturnsSourceReportReader, ReturnsKizReader, ReturnsTransferReader,
)
from utils.kiz_utils import KizUtils

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
                sellers=None) -> dict:
        """Запускает подготовку с дедупликацией по индексу КИЗов.

        Вход:
            target_dir — корневая папка задачи.
            source_file — путь к исходному файлу возвратов.
            sellers — список Seller. None → пустой список.

        Выход:
            dict с ключами:
                new — строк прошло фильтр по компании
                      (data.stats.copied).
                old — удалено «был в прошлых отчётах».
                dup — удалено «дубль в файле».
                saved — реально записано в Возвраты_{date}.xlsx.
            saved == 0 — файл Возвраты_{date}.xlsx не перезаписывался.
            При критических ошибках — все нули.

        Роль:
            Создаёт TaskContext и LoggerV2. Копирует исходник с
            N-суффиксом. Читает индекс КИЗов из reports_dir/КИЗы.txt.
            Читает исходник через ReturnsSourceReportReader.read,
            дедуплицирует строки по индексу и внутри файла. Пишет
            Возвраты_{date}.xlsx, если остались новые КИЗы.
            Обновляет индекс КИЗов объединением прочитанного и
            новых, но только если что-то записано.
        """
        if sellers is None:
            sellers = []

        ctx = TaskContext(
            target_dir,
            "Возвраты_{date}",
            "log_подготовка.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )

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
        logger.status("Подготовка возвратов начата")

        source_path = FileHelper.ensure_file_exists(
            logger, source_file, "исходный файл"
        )
        if source_path is None:
            return {"new": 0, "old": 0, "dup": 0, "saved": 0}

        logger.status("Копирование исходника")

        # Информативно: сколько уже накопилось копий за сегодня.
        existing = FileHelper.find_files_by_pattern(
            ctx.reports_dir,
            f"*Исходные данные возвратов {ctx.date_str}*.xlsx",
        )

        n = 0
        while (
            ctx.reports_dir
            / f"{n}_Исходные данные возвратов {ctx.date_str}.xlsx"
        ).exists():
            n += 1

        copy_name = f"{n}_Исходные данные возвратов {ctx.date_str}.xlsx"
        copy_dest = ctx.reports_dir / copy_name
        result = FileHelper.copy_file_with_log(
            source_path, copy_dest, logger,
            description="исходный файл", overwrite=True,
        )
        if result["status"] != "copied":
            logger.critical(
                f"Не удалось скопировать исходник: {result['status']}",
                can_influence=False,
            )
            return {"new": 0, "old": 0, "dup": 0, "saved": 0}
        logger.report(f"Сохранён исходник: {copy_name}")

        logger.status("Чтение индекса КИЗов")
        index_path = ctx.reports_dir / "КИЗы.txt"
        existing_kiz_set: set = set()
        if not index_path.is_file():
            logger.warning(
                "Индекс КИЗов не прочитан, будет создан заново"
            )
        else:
            lines = TextFileWriter.read(index_path, logger=logger)
            if lines is None:
                logger.warning(
                    "Индекс КИЗов не прочитан, будет создан заново"
                )
            else:
                existing_kiz_set = set(lines)
        logger.debug(
            f"prepare: индекс КИЗов до обработки, "
            f"размер={len(existing_kiz_set)}"
        )

        allowed_companies = TextUtils.get_allowed_companies(sellers)
        data = ReturnsSourceReportReader.read(
            source_path, allowed_companies, logger
        )

        # Пустой результат означает «файл не открылся» —
        # в успешном случае headers содержит 6 значений.
        if not data.headers and not data.rows:
            logger.critical(
                "Не удалось открыть исходник", can_influence=False,
            )
            return {"new": 0, "old": 0, "dup": 0, "saved": 0}

        logger.status("Дедупликация строк")
        new_rows = []
        old_count = 0
        dup_count = 0
        seen_in_file: set = set()
        for row in data.rows:
            raw_kiz = row[0] if row else None
            if not raw_kiz:
                new_rows.append(row)
                continue
            storage_list = KizUtils.clean_kiz_for_storage(
                raw_kiz, logger=None,
            )
            if not storage_list:
                new_rows.append(row)
                continue
            k = storage_list[0]
            if k in existing_kiz_set:
                old_count += 1
                logger.report(
                    f"Удалено : {k} «был в прошлых отчётах»"
                )
                continue
            if k in seen_in_file:
                dup_count += 1
                logger.report(f"Удалено : {k} «дубль в файле»")
                continue
            seen_in_file.add(k)
            new_rows.append(row)

        saved = len(new_rows)
        new = data.stats.copied

        if saved == 0 and new > 0:
            logger.warning(
                "Все строки исходника — дубли прошлых прогонов"
            )
        if dup_count > 0:
            logger.warning(
                f"Найдено {dup_count} внутрифайловых дублей"
            )

        logger.status("Запись файла возвратов")
        if saved > 0:
            result_name = FilenameUtils.format_with_extension(
                "Возвраты_{date}", ctx.date_str,
            )
            result_path = ctx.reports_dir / result_name
            ok = WorkbookWriter.create(
                result_path,
                headers=data.headers or [],
                rows=new_rows,
                sheet_name="Возвраты",
                logger=logger,
            )
            if not ok:
                logger.critical(
                    "Не удалось записать Возвраты_{date}.xlsx",
                    can_influence=False,
                )
                return {"new": 0, "old": 0, "dup": 0, "saved": 0}
            logger.report(f"Создан файл с возвратами: {result_name}")

        logger.status("Обновление индекса КИЗов")
        was_size = len(existing_kiz_set)
        now_size = was_size
        if saved > 0:
            new_index = existing_kiz_set | seen_in_file
            TextFileWriter.write(
                index_path, header=None, items=sorted(new_index),
                logger=logger,
            )
            now_size = len(new_index)

        logger.status("Подготовка завершена")

        if saved == 0:
            logger.debug(
                f"prepare: индекс КИЗов после обработки, "
                f"размер={len(existing_kiz_set)}"
            )
        else:
            logger.debug(
                f"prepare: индекс КИЗов после обработки, "
                f"размер={now_size}"
            )

        # Info-сводка.
        total_in = new + data.stats.skipped
        lines = ["Подготовка возвратов:"]
        lines.append(f"  Исходник сохранён как: {copy_name}")
        lines.append(f"  Строк во входе: {total_in}")
        lines.append(
            f"  Удалено «был в прошлых отчётах»: {old_count}"
        )
        lines.append(f"  Удалено «дубль в файле»: {dup_count}")
        lines.append(f"  Прошло фильтр: {new}")
        if saved > 0:
            lines.append(
                f"  Записано в Возвраты_{{date}}.xlsx: {saved}"
            )
            lines.append(
                f"  КИЗов в индексе: {was_size} → {now_size}"
            )
        else:
            lines.append(
                "  Новых КИЗов не обнаружено, индекс не изменён"
            )
        logger.info("\n".join(lines))
        # ---END---

        return {
            "new": new,
            "old": old_count,
            "dup": dup_count,
            "saved": saved,
        }

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

    def __init__(self, kiz_validator, log_manager_v2, *,
                 overwrite_requester=None) -> None:
        """Конструктор.

        Вход:
            kiz_validator — KizValidator.
            log_manager_v2 — LogManagerV2.
            overwrite_requester — Callable[[], bool | None] | None.
                Callback выбора режима записи .txt. True — перезапись,
                False — дополнение, None — отмена. Вызов только в
                UI-потоке (сервис сам диалог не открывает).

        Роль: сохраняет ссылки. Логгер создаётся в начале export.
        """
        self.kiz_validator = kiz_validator
        self._log_manager_v2 = log_manager_v2
        self._overwrite_requester = overwrite_requester

    def export(self, target_dir, sellers=None) -> None:
        """Запускает выгрузку КИЗов для возврата.

        Вход:
            target_dir — корневая папка задачи.
            sellers — список Seller (не используется в этом методе;
                      оставлен для совместимости сигнатуры).

        Выход: нет.

        Роль:
            Создаёт TaskContext и LoggerV2, находит
            Возвраты_{date}.xlsx в reports_dir, вызывает reader,
            пишет .txt-файлы по компаниям. Если у каких-то компаний
            .txt уже существуют — спрашивает режим через
            overwrite_requester: перезаписать или дополнить.
        """
        ctx = TaskContext(
            target_dir,
            "Возвраты_{date}",
            "log_выгрузка_кизов.txt",
            subfolders=["Логи", "Отчёты", "Продажи"],
        )

        logger = self._log_manager_v2.create_logger_v2(
            source="KizExportService.returns_service",
            domain="returns",
            work_folder=ctx.logs_dir,
            log_filename="log_выгрузка_кизов.txt",
        )

        logger.status("Выгрузка КИЗов начата")
        logger.report(
            "=== Выгрузка КИЗов для возврата "
            "(с валидацией и очисткой) ==="
        )
        logger.debug(
            f"export: sellers={len(sellers or [])}, "
            f"target_dir={target_dir}"
        )

        source_file = ctx.reports_dir / FilenameUtils.format_with_extension(
            "Возвраты_{date}", ctx.date_str
        )
        source_file = FileHelper.ensure_file_exists(
            logger, source_file, "файл возвратов"
        )
        if source_file is None:
            return

        logger.status("Загрузка базы КИЗов для валидации")
        self.kiz_validator.load()

        logger.status("Чтение файла возвратов")
        data = ReturnsKizReader.read(
            source_file, self.kiz_validator, logger
        )

        # ---New---
        logger.status("Проверка существующих файлов КИЗов")
        existing_txts: dict = {}
        for company in data.full_kizs_by_company.keys():
            txt_path = ctx.work_folder / f"{company}.txt"
            if txt_path.is_file():
                existing_txts[company] = txt_path

        # Решение о режиме.
        mode = "overwrite"
        if existing_txts and self._overwrite_requester is not None:
            logger.status("Запрос режима записи")
            decision = None
            try:
                decision = self._overwrite_requester()
            except Exception as e:
                logger.critical(
                    f"Ошибка запроса режима записи: {e}",
                    can_influence=False,
                )
                decision = None
            if decision is True:
                mode = "overwrite"
                logger.report(
                    "Запрос режима записи: пользователь выбрал "
                    "перезаписать"
                )
            elif decision is False:
                mode = "append"
                logger.report(
                    "Запрос режима записи: пользователь выбрал "
                    "дополнить"
                )
            else:
                logger.warning("Пользователь отменил выгрузку")
                logger.status("Выгрузка отменена")
                return

        logger.debug(
            f"export: существующих .txt — {len(existing_txts)}, "
            f"режим={mode}"
        )
        logger.status("Сохранение файлов КИЗов")

        total_appended_duplicates = 0
        per_seller_lines: list = []
        if data.full_kizs_by_company:
            for company, kiz_list in sorted(
                data.full_kizs_by_company.items(),
                key=lambda x: x[0].lower(),
            ):
                txt_path = ctx.work_folder / f"{company}.txt"
                new_set = set(kiz_list)

                if mode == "append" and txt_path.is_file():
                    existing_lines = TextFileWriter.read(
                        txt_path, logger=logger,
                    )
                    if existing_lines is None:
                        logger.warning(
                            f"Файл {txt_path.name} не прочитан, "
                            f"будет перезаписан"
                        )
                        combined = sorted(new_set)
                        TextFileWriter.write(
                            txt_path, header=None, items=combined,
                            logger=logger,
                        )
                        per_seller_lines.append(
                            f"Продавец {company}: перезапись, "
                            f"{len(combined)} КИЗов в {txt_path.name}"
                        )
                    else:
                        existing_set = set(existing_lines)
                        combined = existing_set | new_set
                        duplicates = (
                            len(existing_set) + len(new_set)
                            - len(combined)
                        )
                        total_appended_duplicates += duplicates
                        TextFileWriter.write(
                            txt_path, header=None,
                            items=sorted(combined), logger=logger,
                        )
                        per_seller_lines.append(
                            f"Продавец {company}: дополнение, "
                            f"было {len(existing_set)}, "
                            f"стало {len(combined)}, "
                            f"дублей {duplicates}, "
                            f"файл {txt_path.name}"
                        )
                else:
                    combined = sorted(new_set)
                    TextFileWriter.write(
                        txt_path, header=None, items=combined,
                        logger=logger,
                    )
                    per_seller_lines.append(
                        f"Продавец {company}: перезапись, "
                        f"{len(combined)} КИЗов в {txt_path.name}"
                    )
        else:
            logger.report(
                "  Не найдено ни одного КИЗа, прошедшего валидацию "
                "(со статусом ВЫБЫЛ)."
            )

        for line in per_seller_lines:
            logger.report(line)

        # Info-сводка по выгрузке.
        total_returns = (
            data.returns_updated_in_base + data.returns_not_in_base
        )
        if mode == "overwrite":
            if existing_txts:
                mode_str = "перезаписать"
            else:
                mode_str = (
                    f"перезаписать (новых файлов: "
                    f"{len(per_seller_lines)})"
                )
        else:
            mode_str = "дополнить"

        lines = ["Выгрузка КИЗов:"]
        lines.append(
            f"  Продавцов в файле: "
            f"{len(data.full_kizs_by_company)}"
        )
        lines.append(f"  КИЗов обработано: {total_returns}")
        lines.append(
            f"  Обновлено в базе: {data.returns_updated_in_base}"
        )
        lines.append(
            f"  Отсутствует в базе: {data.returns_not_in_base}"
        )
        lines.append(f"  Режим записи: {mode_str}")
        lines.append(
            f"  Файлов КИЗов записано: {len(per_seller_lines)}"
        )
        if mode == "append" and total_appended_duplicates > 0:
            lines.append(
                f"  Дублей при дополнении: "
                f"{total_appended_duplicates}"
            )
        logger.info("\n".join(lines))

        # Существующие info-сводки — как раньше.
        logger.info(
            f"\nВозвраты:    \nобработано {total_returns}\n"
            f"({data.returns_updated_in_base} обновлено в базе\n"
            f"{data.returns_not_in_base} отсутствует в базе — "
            f"запись не создана).\n"
        )

        kiz_stats = data.kiz_stats or {}
        logger.info(
            f"\nОбработка КИЗов: \n    успешно {kiz_stats.get('processed', 0)}\n "
            f"    отброшено коротких: {kiz_stats.get('dropped_short', 0)}\n "
            f"    без '01': {kiz_stats.get('dropped_no_01', 0)}\n"
            f"    транслитерировано: {kiz_stats.get('transliterated', 0)}"
        )
        # ---END---

        logger.status("Выгрузка завершена")
        logger.report("---Выгрузка завершена.---\n")
        logger.debug(
            f"export: выход, файлов записано {len(per_seller_lines)}"
        )

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

    def __init__(self, log_manager_v2, priority_resolver=None) -> None:
        """Конструктор.

        Вход:
            log_manager_v2 — LogManagerV2.
            priority_resolver — Callable[[dict], dict[str, Seller]]
                или None. Принимает conflicts (см. формат
                ReturnsTransferData.conflicts), возвращает
                {brand_key: Seller}. Вызов — только в UI-потоке
                (сервис сам не открывает диалог). При None —
                конфликты не разрешаются, строки из pending_rows
                пропускаются с warning.

        Роль: сохраняет ссылки. Логгер создаётся в начале
              prepare_transfer.
        """
        self._log_manager_v2 = log_manager_v2
        self._priority_resolver = priority_resolver

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

        logger.debug("KizTransferService.prepare_transfer: старт")
        logger.status("Подготовка передач КИЗов начата")
        logger.report(
            f"=== Подготовка передач КИЗов начата "
            f"{ctx.today.strftime('%d.%m.%Y %H:%M')} ==="
        )

        source_file = ctx.reports_dir / FilenameUtils.format_with_extension(
            "Возвраты_{date}", ctx.date_str
        )
        source_file = FileHelper.ensure_file_exists(
            logger, source_file, "файл возвратов"
        )
        if source_file is None:
            return

        # Генератор продаж — с логгером V2, чтобы debug-сообщения
        # не терялись.
        sales_gen = SalesFileGenerator(ctx.sales_dir, logger=logger)
        logger.status("Чтение файла возвратов")
        # Reader возвращает готовые строки передач и агрегаты.
        data = ReturnsTransferReader.read(source_file, sellers, logger)
        all_rows = list(data.rows)

        if data.conflicts:
            logger.status("Разрешение конфликтов брендов")
            if self._priority_resolver is None:
                logger.warning(
                    f"Конфликтов: {len(data.conflicts)}. "
                    f"UI-резолвер не передан — строки пропущены: "
                    f"{len(data.pending_rows)}"
                )
            else:
                try:
                    resolution = self._priority_resolver(
                        data.conflicts
                    )
                except Exception as e:
                    logger.critical(
                        f"Ошибка резолвера приоритетов: {e}",
                        can_influence=False,
                    )
                    resolution = None

                if isinstance(resolution, dict):
                    for pending_row in data.pending_rows:
                        selected = resolution.get(
                            pending_row.brand_key
                        )
                        if selected is None:
                            logger.warning(
                                f"Конфликт по бренду "
                                f"'{pending_row.brand}' не "
                                f"разрешён — строка пропущена"
                            )
                            continue
                        pending_row.to_seller_name = selected.name
                        pending_row.to_seller_inn = selected.inn
                        all_rows.append(pending_row)
                    logger.info(
                        f"\nРазрешено конфликтов: "
                        f"{len(resolution)}"
                    )
                else:
                    logger.warning(
                        f"Резолвер вернул некорректный результат "
                        f"— строки пропущены: "
                        f"{len(data.pending_rows)}"
                    )

        logger.status("Генерация файлов продаж")
        # Прогон готовых строк через генератор — без дополнительных
        # проверок: всё уже проверено в reader'е.
        for transfer in data.rows:
            sales_gen.add_sale_row(
                from_seller_name=transfer.from_seller_name,
                to_seller_name=transfer.to_seller_name,
                to_seller_inn=transfer.to_seller_inn,
                product_name=transfer.product_name,
                raw_kiz=transfer.raw_kiz,
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
        if data.conflicts:
            total_c = len(data.conflicts)
            if self._priority_resolver is not None:
                resolved_c = 0
                if isinstance(locals().get("resolution"), dict):
                    resolved_c = len(resolution)
            else:
                resolved_c = 0
            skipped_c = total_c - resolved_c
            if skipped_c < 0:
                skipped_c = 0
            logger.info(
                f"\nКонфликты брендов:\n"
                f"  Всего: {total_c}\n"
                f"  Разрешено: {resolved_c}\n"
                f"  Пропущено: {skipped_c}"
            )

        logger.report("Подготовка передач завершена.\n")
        logger.status("Подготовка передач завершена")
        logger.debug("KizTransferService.prepare_transfer: выход")