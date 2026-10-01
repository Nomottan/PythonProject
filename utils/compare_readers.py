"""
Ридеры файлов сравнения поставок.

Три класса:
    SupplyItemsReader        — читает лист поставки (копию) → SupplyItem.
    CandidatesReader         — читает сборный файл поставок → Candidate.
    ConsolidatedSupplyBuilder — собирает Сборный_поставок_{date}.xlsx из
                                списка файлов поставок (Excel и CSV).

Роль в программе:
    Слой чтения данных для CompareService. Разбор Excel — в
    ExcelHelper, разбор наименований — в ProductNameParser,
    нормализация CSV — в CsvNormalizer. Здесь — только оркестрация
    чтения и маппинг строк в модели.
"""

from pathlib import Path
from datetime import date
from typing import TYPE_CHECKING

from utils.excel_helper import (
    ExcelHelper, CsvNormalizer, WorkbookOpener, WorkbookWriter,
)
from utils.parsers import ProductNameParser
from utils.text_utils import TextUtils
from utils.txt_helper import TextFileWriter  # NEW
from models.models import SupplyItem, Candidate

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2

class HeadersTableReader:
    """База для читателей Excel-таблиц с поиском заголовков.

    Роль:
        Общий каркас: открыть файл, найти строку заголовков,
        проитерировать, построить items через _build_item.
        Наследник задаёт _HEADER_VARIANTS, _REQUIRED_COLUMNS
        и _build_item.

    Атрибуты класса:
        _HEADER_VARIANTS — {поле: [варианты заголовков]}.
        _REQUIRED_COLUMNS — обязательные поля. Отсутствие → [].
        _OPEN_DESCRIPTION — описание для WorkbookOpener.
    """

    _HEADER_VARIANTS: dict = {}
    _REQUIRED_COLUMNS: tuple = ("name",)
    _OPEN_DESCRIPTION: str = "файл"

    @classmethod
    def read(cls, file_path, brands_set, logger) -> list:
        """Читает items из файла.

        Вход:
            file_path — путь к файлу.
            brands_set — set[str] ключей брендов или None.
            logger — LoggerV2 или None.

        Выход:
            list items. Пустой список при ошибке.
        """
        file_path = Path(file_path)
        brands_set = brands_set or set()
        items: list = []

        if logger is not None:
            logger.report(f"Загрузка из {file_path.name}")

        wb = WorkbookOpener.open(
            file_path, logger=logger,
            description=cls._OPEN_DESCRIPTION, read_only=True,
        )
        if wb is None:
            return []
        try:
            ws = wb.active
            header_row, columns = ExcelHelper.find_header_row_and_columns(
                ws, cls._HEADER_VARIANTS,
            )
            if header_row is None or columns is None:
                if logger is not None:
                    logger.warning("Не удалось найти заголовки таблицы.")
                return []

            if logger is not None:
                logger.report(f"Заголовки найдены в строке {header_row}")
                cls._log_columns(columns, logger)

            for field in cls._REQUIRED_COLUMNS:
                if columns.get(field) is None:
                    if logger is not None:
                        logger.warning(
                            f"Не найдено обязательное поле '{field}'."
                        )
                    return []

            for row in ws.iter_rows(min_row=header_row + 1,
                                     values_only=True):
                if cls._should_skip_row(row, columns):
                    continue
                item = cls._build_item(row, columns, brands_set)
                if item is not None:
                    items.append(item)
        finally:
            try:
                wb.close()
            except Exception:
                pass

        if logger is not None:
            logger.report(f"Загружено: {len(items)}")
            if items:
                logger.report("Первые 5:")
                for i, item in enumerate(items[:5]):
                    logger.report(
                        f"  {i + 1}. {cls._format_item_for_log(item)}"
                    )
        return items

    # ---------- Точки переопределения ----------

    @classmethod
    def _should_skip_row(cls, row, columns) -> bool:
        """Пропустить ли строку. По умолчанию — False."""
        return False

    @classmethod
    def _build_item(cls, row, columns, brands_set):
        """Построить item из строки. Обязательно переопределить."""
        raise NotImplementedError

    @classmethod
    def _log_columns(cls, columns, logger) -> None:
        """Залогировать распознанные столбцы. Можно переопределить."""
        if logger is not None:
            logger.report(f"Столбцы: {columns}")

    @classmethod
    def _format_item_for_log(cls, item) -> str:
        """Формат элемента для лога «Первые 5». Можно переопределить."""
        return str(item)

class SupplyItemsReader(HeadersTableReader):
    """Читает товары из копии листа поставки.

    Роль:
        Открывает Excel через WorkbookOpener.open, ищет строку
        заголовков через ExcelHelper.find_header_row_and_columns,
        читает строки, разбирает наименование через ProductNameParser.
        Возвращает список SupplyItem. Заголовки не найдены — warning
        и пустой список.
    """

    _HEADER_VARIANTS = {
        'article': ["Артикул", "SKU", "Article", "Код", "Product code"],
        'name':    ["Наименование", "Name", "Product name",
                    "Description", "Товар"],
        'count':   ["Количество", "Quantity", "Qty", "Кол-во"],
        'row_num': ["№", "№ п/п", "№ п.п.", "Номер", "Item", "Row"],
    }

    _REQUIRED_COLUMNS = ("name",)
    _OPEN_DESCRIPTION = "лист поставки"

    @classmethod
    def _should_skip_row(cls, row, columns) -> bool:
        """Пропускает строки без name и строку-шапку 'Наименование'."""
        col_name = columns.get('name')
        if col_name is None or len(row) <= col_name or not row[col_name]:
            return True
        name_str = str(row[col_name]).strip()
        if not name_str or name_str.lower() == 'наименование':
            return True
        return False

    @classmethod
    def _build_item(cls, row, columns, brands_set):
        """Собирает SupplyItem из строки."""
        col_article = columns.get('article')
        col_name = columns.get('name')
        col_count = columns.get('count')
        col_row_num = columns.get('row_num')

        name_str = str(row[col_name]).strip()

        article = (row[col_article]
                   if col_article is not None and len(row) > col_article
                   else "")
        count_raw = (row[col_count]
                     if col_count is not None and len(row) > col_count
                     else None)
        count = None
        if count_raw is not None:
            try:
                count = int(float(count_raw))
            except (ValueError, TypeError):
                count = None

        row_num = (row[col_row_num]
                   if col_row_num is not None and len(row) > col_row_num
                   else None)

        features = ProductNameParser.extract(name_str, brands_set)
        return SupplyItem(
            row_num=row_num,
            article=str(article).strip() if article else "",
            name=name_str,
            count=count,
            keywords=features.keywords,
            brand=features.brand,
        )

    @classmethod
    def _log_columns(cls, columns, logger) -> None:
        """Детализированный лог столбцов."""
        if logger is not None:
            logger.report(
                f"Столбцы: артикул={columns.get('article')}, "
                f"наименование={columns.get('name')}, "
                f"количество={columns.get('count')}, "
                f"№={columns.get('row_num')}"
            )

    @classmethod
    def _format_item_for_log(cls, item) -> str:
        """Формат строки для лога."""
        return (
            f"{item.name} | кол-во: {item.count} | "
            f"keywords: {item.keywords}"
        )

class CandidatesReader(HeadersTableReader):
    """Читает кандидатов из сборного файла поставок.

    Роль:
        Обязательные поля — name и shk; если хотя бы одно не
        найдено — warning и пустой список (без shk сравнение
        невозможно — кандидат не может быть привязан к артикулу).
    """

    _HEADER_VARIANTS = {
        'name':        ["Наименование", "Name"],
        'count':       ["Количество_строк", "Количество строк", "Count",
                        "Quantity", "Количество"],
        'serial':      ["Серийный_номер", "Serial number"],
        'source_file': ["Файл_источник", "Source file"],
        'shk':         ["ШК", "GTIN", "Barcode"],
    }

    _REQUIRED_COLUMNS = ("name", "shk")
    _OPEN_DESCRIPTION = "сборный файл"

    @classmethod
    def _should_skip_row(cls, row, columns) -> bool:
        """Пропускает строки без name."""
        col_name = columns.get('name')
        if col_name is None or len(row) <= col_name:
            return True
        return not row[col_name]

    @classmethod
    def _build_item(cls, row, columns, brands_set):
        """Собирает Candidate из строки."""
        col_name = columns.get('name')
        col_count = columns.get('count')
        col_serial = columns.get('serial')
        col_source = columns.get('source_file')
        col_shk = columns.get('shk')

        name = row[col_name]
        count = (row[col_count]
                 if col_count is not None and len(row) > col_count
                 else None)
        if count is not None:
            try:
                count = int(count)
            except (ValueError, TypeError):
                count = None
        serial = (row[col_serial]
                  if col_serial is not None and len(row) > col_serial
                  else None)
        source_file = (row[col_source]
                       if col_source is not None and len(row) > col_source
                       else "")
        shk = (row[col_shk]
               if col_shk is not None and len(row) > col_shk
               else None)

        features = ProductNameParser.extract(str(name).strip(), brands_set)
        return Candidate(
            name=str(name).strip(),
            count=count,
            serial=str(serial).strip() if serial else None,
            source_file=str(source_file).strip() if source_file else "",
            keywords=features.keywords,
            brand=features.brand,
            shk=str(shk).strip() if shk else None,
        )

    @classmethod
    def _format_item_for_log(cls, item) -> str:
        """Формат строки для лога."""
        return f"{item.name} -> keywords: {item.keywords}"

class ConsolidatedSupplyBuilder:
    """Собирает единый файл поставок из списка входных файлов.

    Роль:
        Для каждого файла определяет формат: CSV — через
        CsvNormalizer, Excel — через WorkbookOpener.open +
        find_header_row_and_columns. Агрегирует строки по GTIN/ШК
        в словарь, пишет Сборный_поставок_{date}.xlsx через
        WorkbookWriter.create.
    """

    # Заголовки для Excel-файлов поставок.
    _EXCEL_HEADER_VARIANTS = {
        'name':   ["Наименование", "Name", "Product name", "Description", "Товар"],
        'shk':    ["ШК", "GTIN", "Штрихкод", "Barcode", "Код маркировки"],
        'serial': ["Серийный номер", "Serial number", "Код", "S/N"],
    }

    # Заголовки итогового сборного файла. Порядок столбцов сохраняется.
    _RESULT_HEADERS = ["ШК", "Наименование", "Количество",
                       "Серийный номер", "Файл-источник"]

    @staticmethod
    def build(supply_files, output_dir, logger) -> Path:
        """Собирает Сборный_поставок_{date}.xlsx.

        Вход:
            supply_files — список путей к файлам поставок (Excel или CSV).
            output_dir — папка для сохранения результата и логов
                         некорректных CSV-строк.
            logger — LoggerV2 или None.

        Выход:
            Path к сохранённому сборному файлу.

        Исключения:
            ValueError — если ни в одном файле не нашли ни одной
                         записи с GTIN/ШК; список supply_files пуст.

        Роль:
            Точный перенос CompareService.build_consolidated_supply.
            Логи некорректных CSV-строк — в
            output_dir/log_некорректные_строки_{stem}.txt. Финальный
            файл — через ExcelHelper.create_report_workbook, столбец
            «Серийный номер» пропускается через
            TextUtils.clean_invalid_excel_chars.
        """
        if not supply_files:
            raise ValueError("Список файлов поставок пуст.")

        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        consolidated: dict = {}
        total_files = len(supply_files)

        for idx, raw_path in enumerate(supply_files, start=1):
            file_path = Path(raw_path)
            if logger is not None:
                logger.report(f"Обработка файла {idx}/{total_files}: {file_path.name}")

            if file_path.suffix.lower() == '.csv':
                ConsolidatedSupplyBuilder._add_csv(
                    file_path, output_dir_path, consolidated, logger,
                )
            else:
                ConsolidatedSupplyBuilder._add_excel(
                    file_path, consolidated, logger,
                )

        if logger is not None:
            logger.report(f"Всего уникальных GTIN/ШК: {len(consolidated)}")

        if not consolidated:
            raise ValueError(
                "Не найдено ни одной записи с GTIN/ШК в файлах поставок."
            )

        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        consolidated_path = output_dir_path / f"Сборный_поставок_{date_str}.xlsx"

        rows = []
        for shk_key, data in consolidated.items():
            serial_clean = (
                TextUtils.clean_invalid_excel_chars(data['serial'])
                if data['serial'] else ''
            )
            rows.append([
                shk_key,
                data['original_name'],
                data['count'] if data['count'] is not None else 0,
                serial_clean,
                data['source_file'],
            ])

        WorkbookWriter.create(
            consolidated_path,
            ConsolidatedSupplyBuilder._RESULT_HEADERS,
            rows,
            sheet_name="Поставки",
            logger=logger,
        )

        if logger is not None:
            logger.report(f"Сборный файл сохранён: {consolidated_path.name}")
        return consolidated_path

    # ---------- Приватные помощники ----------

    @staticmethod
    def _add_csv(file_path: Path, output_dir: Path,
                 consolidated: dict, logger) -> None:
        """Добавляет строки из CSV-файла в consolidated.

        Вход:
            file_path — путь к CSV.
            output_dir — папка для log_некорректные_строки_{stem}.txt.
            consolidated — накопительный dict (мутируется).
            logger — LoggerV2 или None.

        Роль:
            Использует CsvNormalizer для разбора. Некорректные строки
            пишет в отдельный лог рядом с output_dir. В consolidated
            каждая валидная строка добавляется как отдельная запись
            по gtin, с инкрементом count.
        """
        try:
            normalizer = CsvNormalizer(file_path)
            valid_rows, invalid_log = normalizer.normalize_rows()
        except Exception as e:
            if logger is not None:
                logger.report(f"  Ошибка обработки CSV через нормализатор: {e}")
            return

        if invalid_log:
            log_path = output_dir / f"log_некорректные_строки_{file_path.stem}.txt"
            TextFileWriter.write(
                log_path,
                header=f"Некорректные строки в файле {file_path.name}",
                items=invalid_log,
                logger=logger,
            )
            if logger is not None:
                logger.report(f"  Некорректные строки сохранены в {log_path.name}")
        if not valid_rows:
            if logger is not None:
                logger.report("  Валидных строк не найдено")
            return

        if logger is not None:
            logger.report(f"  Найдено валидных строк: {len(valid_rows)}")

        for row in valid_rows:
            gtin = row['gtin']
            kiz = row['kiz']
            name = row['name']
            count = int(row['count']) if row['count'].isdigit() else 1

            if gtin not in consolidated:
                consolidated[gtin] = {
                    'original_name': name,
                    'count': 0,
                    'serial': kiz,
                    'source_file': file_path.name,
                    'gtin': gtin,
                }
            consolidated[gtin]['count'] += count
            if not consolidated[gtin]['serial'] and kiz:
                consolidated[gtin]['serial'] = kiz
            if not consolidated[gtin]['original_name'] and name:
                consolidated[gtin]['original_name'] = name

    @staticmethod
    def _add_excel(file_path: Path, consolidated: dict, logger) -> None:
        """Добавляет строки из Excel-файла поставок в consolidated.

        Вход:
            file_path — путь к Excel-файлу.
            consolidated — накопительный dict (мутируется).
            logger — LoggerV2 или None.

        Роль:
            Открывает файл через WorkbookOpener.open, ищет
            заголовки через find_header_row_and_columns. Каждая
            строка с непустым ШК добавляется в consolidated с
            инкрементом count (1 за строку — так было в исходнике).
            Файл без заголовков или без ШК-столбца пропускается.
        """
        wb = WorkbookOpener.open(
            file_path, logger=logger, description="файл поставок",
            read_only=True,
        )
        if wb is None:
            return

        try:
            ws = wb.active
            header_row, columns = ExcelHelper.find_header_row_and_columns(
                ws, ConsolidatedSupplyBuilder._EXCEL_HEADER_VARIANTS,
            )
            if header_row is None or columns is None:
                if logger is not None:
                    logger.report(
                        f"  Не удалось найти заголовки в файле {file_path.name}, "
                        f"пропускаем"
                    )
                return

            col_name = columns.get('name')
            col_shk = columns.get('shk')
            col_serial = columns.get('serial')

            if col_name is None or col_shk is None:
                if logger is not None:
                    logger.report(
                        f"  В файле {file_path.name} не найдены столбцы "
                        f"'Наименование' или 'ШК', пропускаем"
                    )
                return

            if logger is not None:
                logger.report(
                    f"  Заголовки: наименование={col_name}, ШК={col_shk}, "
                    f"серийный={col_serial}"
                )

            row_count = 0
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                shk = row[col_shk] if len(row) > col_shk else None
                if not shk:
                    continue
                shk_key = str(shk).strip()
                if not shk_key:
                    continue

                name = str(row[col_name]).strip() if row[col_name] else ""
                serial = (row[col_serial]
                          if col_serial is not None and len(row) > col_serial
                          else None)

                if shk_key in consolidated:
                    if consolidated[shk_key]['count'] is None:
                        consolidated[shk_key]['count'] = 0
                    consolidated[shk_key]['count'] += 1
                    if consolidated[shk_key]['serial'] is None and serial:
                        consolidated[shk_key]['serial'] = str(serial).strip()
                else:
                    consolidated[shk_key] = {
                        'original_name': name,
                        'count': 1,
                        'serial': str(serial).strip() if serial else None,
                        'source_file': file_path.name,
                        'gtin': shk_key,
                    }
                row_count += 1

            if logger is not None:
                logger.report(f"  Прочитано строк: {row_count}")
        finally:
            wb.close()