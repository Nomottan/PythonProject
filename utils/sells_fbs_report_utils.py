"""
Утилиты отчётов пайплайна продаж: классификатор, читатели, писатель.

Состав:
    FileTypeDetector        — определяет тип входного файла по числу листов.
    WarehouseReportWriter   — разбивает складской отчёт по продавцам.
    WarehouseReportReader   — читает разбитые складские отчёты.
    WBReportReader          — читает WB-отчёты МП.
    OZONReportReader        — читает Ozon-отчёты.
    BaseMpReportReader      — общий каркас читателей WB/Ozon/склад.

Роль в программе:
    Все утилиты отвечают только за разбор Excel и возврат
    типизированных данных. Batch-контекст KizStorage, запись .txt —
    ответственность вызывающих сервисов. WB, Ozon и Склад
    наследуются от BaseMpReportReader, который держит общий каркас;
    специфика — в наследниках.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.excel_helper import ExcelHelper, WorkbookOpener, WorkbookWriter
from utils.kiz_utils import KizUtils, KizOccurrences
from utils.parsers import DateParser
from utils.text_utils import TextUtils
from services.kiz_validator import ValidationResult

@dataclass
class MpReportData:
    """Агрегированный результат разбора одного отчёта МП.

    Роль:
        Возвращается BaseMpReportReader.read. Содержит и счётчики,
        и полезные данные (цены, полные КИЗы) для мержа в
        общесервисные структуры.

    Поля:
        seller — продавец, определённый по имени файла.
        added — сколько КИЗов прошло валидацию (result == ADDED).
        prices — dict {storage_kiz: int_price} для добавленных КИЗов.
        full_kizs — set полных КИЗов, добавленных в этом отчёте.
        skipped_dup — сколько вхождений отброшено как дубликаты.
        skipped_no_return — КИЗы, проданные без возврата.
        skipped_date_before_return — дата продажи раньше возврата.
        total_unique — всего уникальных storage_kiz в отчёте.
        skipped_by_type — dict {operation_type: count}.
        kiz_dates — {full_kiz: sale_date_str} — дата продажи КИЗа,
                    нормализованная к "%d.%m.%Y". None, если исходную
                    дату не удалось распарсить. Fallback (сегодняшняя
                    дата) НЕ применяется — значение либо дата, либо None.
    """
    seller: "Seller"
    added: int
    prices: dict
    full_kizs: set
    skipped_dup: int
    skipped_no_return: int
    skipped_date_before_return: int
    total_unique: int
    skipped_by_type: dict
    kiz_dates: dict

@dataclass
class MpReadResult:
    """Результат чтения одного WB- или Ozon-отчёта.

    Поля:
        data — MpReportData при успехе, иначе None.
        reason — None и data is not None — успех.
                 Непустой и data is None — файл пропущен.
    """
    data: Optional[MpReportData]
    reason: Optional[str]

class FileTypeDetector:
    """Классификатор входных Excel-файлов по числу листов.

    Роль:
        Единая точка определения типа файла до открытия его
        содержимым. Вызывается из PreparationService перед
        копированием файлов в рабочую папку.
        Заменяет MpReportTypeDetector: тот смотрел первый лист
        по имени («Сборочные задания» / «Отчет»), новый — по
        общему количеству листов. Причина замены: складские
        отчёты имеют 6+ листов и не отличимы по первому листу
        от WB, а Ozon-отчёт всегда однолистовой.

    Правило классификации:
        n == 1  → "ozon",
        n > 5   → "wh"  (склад),
        иначе   → "wb"  (WB-отчёт МП).
        Файл не открылся → None.

    Все методы — @staticmethod, состояние не хранится.
    """

    @staticmethod
    def detect(path) -> str | None:
        """Определяет тип одного файла.

        Вход:
            path — путь к Excel-файлу.

        Выход:
            "ozon" | "wb" | "wh" | None.

        Роль:
            Открывает workbook через WorkbookOpener.open
            (read_only=True, logger=None). Содержимое не читается,
            берётся только количество листов. При любой ошибке
            открытия WorkbookOpener возвращает None — тогда и
            detect возвращает None (файл считается неопознанным).
        """
        wb = WorkbookOpener.open(path, logger=None, read_only=True)
        if wb is None:
            return None
        try:
            n = len(wb.sheetnames)
            if n == 1:
                return "ozon"
            if n > 5:
                return "wh"
            return "wb"
        finally:
            try:
                wb.close()
            except Exception:
                pass

    @staticmethod
    def detect_all(files) -> dict:
        """Определяет типы для списка файлов за один проход.

        Вход:
            files — итерируемое путей к Excel-файлам.

        Выход:
            dict {path: "wb" | "ozon" | "wh" | None}.
            Ключ — исходное значение из files (str или Path).
            Порядок ключей сохраняется как в files.

        Роль:
            Один проход по списку; каждый файл открывается
            ровно один раз (внутри detect).
        """
        result: dict = {}
        for path in files:
            result[path] = FileTypeDetector.detect(path)
        return result

class BaseMpReportReader:
    """База для читателей отчётов МП (WB, Ozon).

    Роль:
        Общий каркас: найти продавца, открыть workbook, проверить
        обязательные листы, загрузить вхождения, валидировать,
        собрать результат. Специфика — в наследниках.

    Атрибуты класса:
        _REQUIRED_SHEETS — обязательные листы. Пустое — не проверять.
        COLLECT_PRICES — собирать ли цены из отчёта.
        _DESCRIPTION — описание для сообщений WorkbookOpener.
    """

    _REQUIRED_SHEETS: tuple = ()
    COLLECT_PRICES: bool = False
    _DESCRIPTION: str = "отчёт МП"

    @classmethod
    def read(cls, report_path, sellers, kiz_validator,
             logger) -> MpReadResult:
        """Читает один отчёт МП.

        Вход:
            report_path — путь к файлу.
            sellers — список Seller.
            kiz_validator — KizValidator.
            logger — LoggerV2.

        Выход:
            MpReadResult:
                data — MpReportData при успехе, иначе None.
                reason — None при успехе; один из ярлыков
                         ("продавец не найден", "файл не открылся",
                         "нет обязательного листа") при пропуске.

        Роль:
            Единый каркас для WB и Ozon. Исключения не
            перехватываются — пробрасываются наружу. finally
            закрывает workbook и сбрасывает статистику KizUtils.
        """
        seller = cls._find_seller(report_path, sellers, logger)
        if seller is None:
            return MpReadResult(data=None, reason="продавец не найден")

        wb = cls._open_workbook(report_path, logger)
        if wb is None:
            return MpReadResult(data=None, reason="файл не открылся")

        KizUtils.start_stats()
        try:
            if not cls._has_required_sheets(wb, logger):
                return MpReadResult(
                    data=None, reason="нет обязательного листа"
                )

            occurrences, skipped_by_type = cls._load_occurrences(wb, logger)
            dates = cls._load_dates(wb)

            result_dict = cls._validate_occurrences(
                occurrences, dates, kiz_validator, logger, seller,
            )

            result_data = cls._build_result(
                seller, result_dict, skipped_by_type,
            )
            return MpReadResult(data=result_data, reason=None)
        finally:
            try:
                wb.close()
            except Exception:
                pass
            stats = KizUtils.pop_stats()
            cls._log_stats(logger, report_path, stats)

    # ---------- Точки переопределения ----------

    @classmethod
    def _find_seller(cls, report_path, sellers, logger):
        """Ищет продавца по имени файла.

        Дефолт: TextUtils.find_seller_by_file_name(stem.lower(), sellers).
        Наследник может переопределить.
        """
        report_path = Path(report_path)
        seller = TextUtils.find_seller_by_file_name(
            report_path.stem.lower(), sellers,
        )
        if seller is None:
            logger.report("  Не удалось определить продавца – пропущен")
        else:
            logger.report(f"  Продавец определён: {seller.name}")
        return seller

    @classmethod
    def _open_workbook(cls, report_path, logger):
        """Открывает workbook через WorkbookOpener."""
        report_path = Path(report_path)
        logger.report(f"Обработка отчёта: {report_path.name}")
        return WorkbookOpener.open(
            report_path, logger=logger, read_only=True,
            description=cls._DESCRIPTION,
        )

    @classmethod
    def _has_required_sheets(cls, wb, logger) -> bool:
        """Проверяет наличие обязательных листов."""
        for name in cls._REQUIRED_SHEETS:
            if name not in wb.sheetnames:
                logger.report(f"  Лист '{name}' отсутствует – пропущен")
                return False
        return True

    @classmethod
    def _load_dates(cls, wb) -> dict:
        """Загружает словарь дат. По умолчанию пустой."""
        return {}

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Загружает вхождения КИЗов.

        Выход:
            (KizOccurrences, skipped_by_type: dict[str, int]).

        Наследник обязан переопределить.
        """
        raise NotImplementedError

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки для одного вхождения.

        Вход:
            entry — (full_kiz, sort_value, price).
            dates — словарь из _load_dates.

        Выход:
            datetime или None.

        Наследник обязан переопределить.
        """
        raise NotImplementedError

    @staticmethod
    def _normalize_kiz_date_to_dotted(date_str) -> Optional[str]:
        """Нормализует строку даты КИЗа к "%d.%m.%Y".

        Вход: date_str — строка или None.
        Выход: строка "%d.%m.%Y" или None.

        Роль: единая точка приведения даты продажи КИЗа
              к виду, принятому в отчётах. Fallback
              не применяется — что не распарсилось, то
              остаётся None.
        """
        if not date_str:
            return None
        dt = DateParser.parse_any(
            date_str, DateParser.KIZ_FORMATS
        )
        if dt is None:
            return None
        return dt.strftime("%d.%m.%Y")

        # ---------- Общая валидация ----------

    @classmethod
    def _validate_occurrences(cls, occurrences, dates, kiz_validator,
                              logger, seller) -> dict:
        """Общая валидация всех вхождений.

        Выход:
            dict с ключами:
                added, skipped_dup, skipped_no_return,
                skipped_date_before_return, prices, full_kizs,
                total_unique.
        """
        added = 0
        skipped_dup = 0
        skipped_no_return = 0
        skipped_date_before_return = 0
        prices: dict = {}
        full_kizs: set = set()
        kiz_dates: dict = {}

        for storage_kiz, _entries in occurrences.items():
            def key_func(entry):
                return cls._get_sort_key(entry, dates)

            chosen = occurrences.pick_latest(storage_kiz, key_func)
            if chosen is None:
                continue

            skipped_dup += chosen.skipped_dup_count

            sale_date_str = chosen.sale_date_str
            if sale_date_str is None:
                sale_date_str = datetime.now().strftime("%d-%m-%Y")

            result = kiz_validator.validate_for_sale(
                storage_kiz, sale_date_str,
            )

            if result == ValidationResult.ADDED:
                full_kizs.add(chosen.full_kiz)
                added += 1
                if cls.COLLECT_PRICES and chosen.price is not None:
                    prices[storage_kiz] = int(chosen.price)
                kiz_dates[chosen.full_kiz] = (
                    cls._normalize_kiz_date_to_dotted(
                        chosen.sale_date_str
                    )
                )
            elif result == ValidationResult.SKIPPED_NO_RETURN:
                skipped_no_return += 1
            elif result == ValidationResult.SKIPPED_DATE_BEFORE_RETURN:
                skipped_date_before_return += 1

        total_unique = (
            added + skipped_no_return + skipped_date_before_return
            + skipped_dup
        )

        cls._log_skipped(
            logger, skipped_dup, skipped_no_return,
            skipped_date_before_return, total_unique, added, seller,
        )

        return {
            "added": added,
            "skipped_dup": skipped_dup,
            "skipped_no_return": skipped_no_return,
            "skipped_date_before_return": skipped_date_before_return,
            "prices": prices,
            "full_kizs": full_kizs,
            "total_unique": total_unique,
            "kiz_dates": kiz_dates,
        }

    @classmethod
    def _log_skipped(cls, logger, skipped_dup, skipped_no_return,
                     skipped_date_before_return, total_unique,
                     added, seller) -> None:
        """Логирует пропущенные КИЗы и добавленные."""
        logger.report("  Пропущено КИЗов:")
        logger.report(
            f"    нет в одном экземпляре (дубликаты в отчёте): "
            f"{skipped_dup}"
        )
        logger.report(
            f"    уже проданы без возврата: {skipped_no_return}"
        )
        logger.report(
            f"    дата продажи раньше даты возврата: "
            f"{skipped_date_before_return}"
        )
        logger.report(
            f"    Итого уникальных КИЗов в отчёте: {total_unique}"
        )
        logger.report(
            f"  Добавлено {added} записей для продавца '{seller.name}'"
        )

    @classmethod
    def _build_result(cls, seller, result_dict,
                      skipped_by_type) -> MpReportData:
        """Собирает MpReportData из результатов валидации."""
        return MpReportData(
            seller=seller,
            added=result_dict["added"],
            prices=result_dict["prices"],
            full_kizs=result_dict["full_kizs"],
            skipped_dup=result_dict["skipped_dup"],
            skipped_no_return=result_dict["skipped_no_return"],
            skipped_date_before_return=result_dict["skipped_date_before_return"],
            total_unique=result_dict["total_unique"],
            skipped_by_type=skipped_by_type,
            kiz_dates=result_dict["kiz_dates"],
        )

    @classmethod
    def _log_stats(cls, logger, report_path, stats) -> None:
        """Финальный info-лог со статистикой KizUtils."""
        logger.info(
            f"\n{Path(report_path).name}: \n    успешно {stats['processed']}\n "
            f"    отброшено коротких {stats['dropped_short']}\n"
            f"    без '01' {stats['dropped_no_01']}\n"
            f"    транслитерировано {stats['transliterated']}"
        )

class WarehouseReportReader(BaseMpReportReader):
    """Читатель разбитых складских отчётов «Отчёт_склада_*».

    Роль:
        Разбирает файл, подготовленный WarehouseReportWriter:
        один лист «Склад», все непустые ячейки исходного склада
        построчно в столбце B. Каждая ячейка — потенциальный КИЗ.
        Продавец определён по имени файла (оно сформировано из
        seller.name). Даты из строк не извлекаются — склад не
        содержит даты продажи, при валидации применяется fallback
        «сегодня».

    Отличия от WB/Ozon:
        _REQUIRED_SHEETS пусто — проверять наличие конкретного
        листа не нужно, файл однолистовой по конструкции.
        COLLECT_PRICES=False — цены склад не содержит.
        _find_seller переопределён: имя файла построено из
        seller.name, а базовый поиск идёт по seller.keys и
        в этом случае не находит продавца.

    Все методы — classmethod, как в BaseMpReportReader.
    """

    _REQUIRED_SHEETS = ()
    COLLECT_PRICES = False
    _DESCRIPTION = "отчёт склада"

    @classmethod
    def _find_seller(cls, report_path, sellers, logger):
        """Ищет продавца по имени файла «Отчёт_склада_{safe}_{date}.xlsx».

        Вход:
            report_path — путь к файлу.
            sellers — список Seller.
            logger — LoggerV2.

        Роль:
            Основной путь — TextUtils.find_seller_by_file_name
            по seller.keys. Он работает для большинства имён,
            но у файла склада имя построено из seller.name через
            sanitize_filename — без ключей бренда. Поэтому при
            промахе разбираем stem: убираем префикс
            «Отчёт_склада_» и суффикс «_{D}_{M}_{YYYY}»,
            остаток сравниваем с sanitize_filename(s.name) для
            каждого продавца. Первое совпадение выигрывает.
            Логирование — как в базе.
        """
        report_path = Path(report_path)

        seller = TextUtils.find_seller_by_file_name(
            report_path.stem.lower(), sellers,
        )
        if seller is not None:
            logger.report(f"  Продавец определён: {seller.name}")
            return seller

        # Fallback: разбор имени файла.
        stem = report_path.stem
        prefix = "Отчёт_склада_"
        if stem.startswith(prefix):
            middle = stem[len(prefix):]
            # Отрезаем суффикс _D_M_YYYY (см. TaskContext.date_str).
            parts = middle.rsplit("_", 3)
            if len(parts) == 4:
                middle = parts[0]
            for s in sellers:
                if middle == TextUtils.sanitize_filename(s.name):
                    logger.report(f"  Продавец определён: {s.name}")
                    return s

        logger.report("  Не удалось определить продавца – пропущен")
        return None

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Читает все непустые ячейки всех листов.

        Вход:
            wb — открытый workbook (ожидается один лист «Склад»).
            logger — LoggerV2.

        Выход:
            (KizOccurrences, skipped_by_type).

        Роль:
            Складской отчёт после WarehouseReportWriter содержит
            КИЗы в столбце B, каждый в отдельной строке. Но
            структура может быть иной (другой склад), поэтому
            сканируем все ячейки без привязки к столбцу.
            KizUtils.clean_kiz_full чистит ячейку, возвращает
            список полных КИЗов; для каждого — storage_kiz через
            clean_kiz_for_storage. sort_value и price = None:
            даты продажи в складе нет, цены тоже.
        """
        occurrences = KizOccurrences()
        skipped_by_type: dict = {}

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell is None:
                        continue
                    raw = str(cell).strip()
                    if not raw:
                        continue
                    full_list = KizUtils.clean_kiz_full(
                        raw, logger=logger,
                    )
                    if not full_list:
                        continue
                    for full_kiz in full_list:
                        storage_list = KizUtils.clean_kiz_for_storage(
                            full_kiz, logger=logger,
                        )
                        if not storage_list:
                            continue
                        storage_kiz = storage_list[0]
                        occurrences.add(
                            storage_kiz, full_kiz, None, None,
                        )

        return occurrences, skipped_by_type

    @classmethod
    def _get_sort_key(cls, entry, dates) -> None:
        """Ключ сортировки для склада — None.

        Роль:
            Даты продажи в складском отчёте нет. pick_latest
            выберет любое вхождение (все None), sale_date_str
            останется None, и validate_for_sale подставит
            fallback «сегодня». Отдельная логика сортировки
            не нужна.
        """
        return None


class WarehouseReportWriter:
    """Разбивка складского отчёта по продавцам.

    Роль:
        Берёт один исходный .xlsx (склад ЧЗ МП), проходит по
        всем листам, определяет продавца по имени листа и
        складывает содержимое в отдельный файл на продавца
        в папке «Отчёты».

    Формат записи:
        Все непустые ячейки листа — построчно слева направо,
        сверху вниз — каждая в отдельную строку столбца B.
        Шапки нет. Порядок ячеек — как их выдаёт openpyxl
        при обходе iter_rows(values_only=True).

    Имена файлов:
        "Отчёт_склада_{safe_name}_{date_str}.xlsx",
        где safe_name — TextUtils.sanitize_filename(seller.name).
        Если файл уже есть — дополняется через WorkbookWriter.append_rows,
        иначе создаётся через WorkbookWriter.create.

    Все методы — @staticmethod, состояние не хранится.
    """

    @staticmethod
    def split(source_path, reports_dir, sellers, date_str, logger) -> dict:
        """Разбивает один складской отчёт по продавцам.

        Вход:
            source_path — путь к исходному складскому .xlsx.
            reports_dir — папка «Отчёты» рабочей папки задачи.
            sellers — список Seller для сопоставления с именами листов.
            date_str — строка даты задачи ("D_M_YYYY") для имени файла.
            logger — LoggerV2.

        Выход:
            dict {"created", "appended", "skipped_empty", "skipped_unknown"}:
                created — сколько новых файлов продавцов создано,
                appended — сколько файлов дополнено,
                skipped_empty — сколько листов пусты и пропущены,
                skipped_unknown — сколько листов без продавца.
            При неоткрывшемся исходнике — все значения нули.

        Роль:
            Единая точка разбивки. Покупателя/листы проверять
            снаружи не нужно — метод сам считает статистику.
            Workbook закрывается в finally.
        """
        stats = {
            "created": 0,
            "appended": 0,
            "skipped_empty": 0,
            "skipped_unknown": 0,
        }

        wb = WorkbookOpener.open(
            source_path, logger=logger, description="склад",
            read_only=True,
        )
        if wb is None:
            return stats

        try:
            for sheet_name in wb.sheetnames:
                seller = ExcelHelper.find_seller_by_sheet_name(
                    wb, sellers, sheet_name,
                )
                if seller is None:
                    stats["skipped_unknown"] += 1
                    continue

                sheet = wb[sheet_name]
                values: list = []
                for row in sheet.iter_rows(values_only=True):
                    for cell in row:
                        if cell is None:
                            continue
                        if isinstance(cell, str) and not cell.strip():
                            continue
                        values.append(cell)

                if not values:
                    stats["skipped_empty"] += 1
                    continue

                safe_name = TextUtils.sanitize_filename(seller.name)
                file_name = f"Отчёт_склада_{safe_name}_{date_str}.xlsx"
                dst = reports_dir / file_name
                rows = [(v,) for v in values]

                if dst.exists():
                    WorkbookWriter.append_rows(
                        dst, rows, logger=logger,
                    )
                    stats["appended"] += 1
                else:
                    WorkbookWriter.create(
                        dst, headers=None, rows=rows,
                        sheet_name="Склад", logger=logger,
                    )
                    stats["created"] += 1
        finally:
            try:
                wb.close()
            except Exception:
                pass

        return stats





class WBReportReader(BaseMpReportReader):
    """Читатель WB-отчётов МП.

    Роль:
        Обрабатывает один файл WB-отчёта: читает лист «КИЗ» с
        фильтром по типу операции «ПРОДАЖА», группирует вхождения
        одного КИЗа через KizOccurrences, читает даты из листа
        «Сборочные задания», выбирает самое позднее вхождение
        и валидирует. Возвращает MpReportData.
    """

    _REQUIRED_SHEETS = ("КИЗ",)
    COLLECT_PRICES = True
    _DESCRIPTION = "отчёт МП"

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Читает лист «КИЗ», фильтр по типу операции «ПРОДАЖА»."""
        sheet = wb["КИЗ"]
        occurrences = KizOccurrences()
        skipped_by_type: dict = {}

        for row in sheet.iter_rows(min_row=2, values_only=True):
            if len(row) < 9:
                continue
            task_num = row[0]
            raw_kiz = row[2]
            operation_type = row[8]
            price_raw = row[4] if len(row) > 4 else None

            if not (raw_kiz and task_num and operation_type and
                    str(operation_type).strip().upper() == "ПРОДАЖА"):
                op_key = (
                    str(operation_type).strip()
                    if operation_type else "(пусто)"
                )
                skipped_by_type[op_key] = (
                    skipped_by_type.get(op_key, 0) + 1
                )
                continue

            full_cleaned = KizUtils.clean_kiz_full(raw_kiz, logger=logger)
            if not full_cleaned:
                logger.report(
                    f"    Некорректный КИЗ (очистка не дала "
                    f"результатов): {str(raw_kiz)[:50]}..."
                )
                continue

            task_num_str = str(task_num).strip()

            price_value = None
            try:
                price_value = float(price_raw)
            except (TypeError, ValueError):
                pass
            if price_value is not None and price_value <= 0:
                price_value = None

            for full_kiz in full_cleaned:
                storage_list = KizUtils.clean_kiz_for_storage(
                    full_kiz, logger=logger
                )
                if not storage_list:
                    continue
                storage_kiz = storage_list[0]
                occurrences.add(
                    storage_kiz, full_kiz, task_num_str, price_value
                )

        if skipped_by_type:
            logger.report("  Пропущено строк по типу операции:")
            for op_type, count in sorted(
                skipped_by_type.items(), key=lambda x: x[0].lower()
            ):
                logger.report(f"    '{op_type}': {count}")
        else:
            logger.report(
                "  Все строки прошли фильтр по типу операции 'Продажа'"
            )

        return occurrences, skipped_by_type

    @classmethod
    def _load_dates(cls, wb) -> dict:
        """Читает task_to_date из листа «Сборочные задания»."""
        task_to_date: dict = {}
        if "Сборочные задания" in wb.sheetnames:
            sheet_tasks = wb["Сборочные задания"]
            for row in sheet_tasks.iter_rows(
                min_row=2, values_only=True
            ):
                if len(row) >= 4:
                    task_num = row[0]
                    date_created = row[3]
                    if task_num and date_created:
                        task_to_date[str(task_num).strip()] = (
                            str(date_created).strip()
                        )
        return task_to_date

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки — дата из task_to_date по task_num."""
        date_str = dates.get(entry[1])
        return DateParser.parse_any(date_str, DateParser.KIZ_FORMATS)


class OZONReportReader(BaseMpReportReader):
    """Читатель Ozon-отчётов «Продажи маркированных товаров».

    Роль:
        Читает лист «Отчет», фильтрует строки по Схема продажи == FBS
        и Тип чека == Продажа, группирует КИЗы по storage_kiz через
        KizOccurrences (ключ сортировки — готовый datetime из ячейки).
        Возвращает MpReportData. Цены не собираются.
    """

    _REQUIRED_SHEETS = ("Отчет",)
    COLLECT_PRICES = False
    _DESCRIPTION = "отчёт Ozon"

    HEADER_VARIANTS = {
        "sale_date":  ["Дата фискализации"],
        "check_type": ["Тип чека"],
        "scheme":     ["Схема продажи"],
        "kiz":        ["Код маркировки"],
    }

    FALLBACK_COLUMNS = {
        "sale_date": 0, "check_type": 2, "scheme": 6, "kiz": 8,
    }

    @classmethod
    def _load_occurrences(cls, wb, logger) -> tuple:
        """Читает лист «Отчет», фильтр FBS + ПРОДАЖА."""
        sheet = wb["Отчет"]
        header_row, columns = ExcelHelper.find_header_row_and_columns(
            sheet, cls.HEADER_VARIANTS,
        )
        if header_row is None or columns is None:
            logger.warning(
                "Не удалось найти заголовки Ozon-отчёта по именам, "
                "использую фиксированные индексы (0, 2, 6, 8)"
            )
            header_row = 1
            columns = dict(cls.FALLBACK_COLUMNS)

        col_sale_date = columns["sale_date"]
        col_check_type = columns["check_type"]
        col_scheme = columns["scheme"]
        col_kiz = columns["kiz"]

        occurrences = KizOccurrences()
        skipped_by_type: dict = {}

        for row in sheet.iter_rows(min_row=header_row + 1,
                                    values_only=True):
            scheme = (
                str(row[col_scheme]).strip()
                if len(row) > col_scheme and row[col_scheme] is not None
                else ""
            )
            check_type = (
                str(row[col_check_type]).strip()
                if len(row) > col_check_type
                   and row[col_check_type] is not None
                else ""
            )

            if scheme.upper() != "FBS":
                key = f"схема: {scheme or '(пусто)'}"
                skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                continue
            if check_type.upper() != "ПРОДАЖА":
                key = f"тип чека: {check_type or '(пусто)'}"
                skipped_by_type[key] = skipped_by_type.get(key, 0) + 1
                continue

            raw_kiz = row[col_kiz] if len(row) > col_kiz else None
            raw_date = (
                row[col_sale_date] if len(row) > col_sale_date else None
            )
            if not raw_kiz or not raw_date:
                continue

            storage_list = KizUtils.clean_kiz_for_storage(
                raw_kiz, logger=logger
            )
            full_list = KizUtils.clean_kiz_full(
                raw_kiz, logger=logger
            )
            if not storage_list or not full_list:
                continue
            storage_kiz = storage_list[0]
            full_kiz = full_list[0]

            dt = DateParser.parse_iso_datetime(str(raw_date).strip())
            if dt is None:
                logger.warning(
                    f"Не удалось распарсить дату '{raw_date}' "
                    f"для КИЗа {storage_kiz}. Использую сегодняшнюю."
                )
                dt = datetime.now()

            occurrences.add(storage_kiz, full_kiz, dt, None)

        if skipped_by_type:
            logger.report("  Пропущено строк по типу:")
            for key, count in sorted(
                skipped_by_type.items(), key=lambda x: x[0].lower()
            ):
                logger.report(f"    '{key}': {count}")

        return occurrences, skipped_by_type

    @classmethod
    def _get_sort_key(cls, entry, dates) -> Optional[datetime]:
        """Ключ сортировки — уже готовый datetime из entry[1]."""
        return entry[1]
