from pathlib import Path
import xlrd, sys, csv, re, openpyxl
from openpyxl import Workbook
from typing import List, Dict, Tuple, TYPE_CHECKING
from utils.text_utils import TextUtils
from utils.parsers import NumberParser
from utils.batcher import Batcher

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2

class ExcelHelper:

    @staticmethod
    def _open_data_file(file_path, read_only=True, data_only=True):
        """
        Открывает файл любого поддерживаемого формата (.xlsx, .xls, .csv)
        и возвращает объект с интерфейсом openpyxl Workbook.

        Приватный: публичный вход — WorkbookOpener.open.
        """
        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        if ext in ('.xlsx', '.xlsm'):
            return openpyxl.load_workbook(file_path, read_only=read_only, data_only=data_only)
        elif ext == '.xls':
            wb = xlrd.open_workbook(file_path, formatting_info=False, on_demand=True)
            return XlsReader(wb)
        elif ext == '.csv':
            return CsvReader(file_path)
        else:
            raise ValueError(f"Неподдерживаемый формат файла: {ext}")

    @staticmethod
    def _is_dimension_broken(wb) -> bool:
        """Проверяет, «схлопнут» ли workbook из-за отсутствия dimension.

        Назначение:
            openpyxl в режиме read_only=True опирается на атрибут dimension
            в XML-структуре файла, чтобы определить границы листа. Если атрибут
            отсутствует, max_row и max_column остаются =1, и iter_rows не выдаёт
            ни одной строки. Метод ловит этот случай.

        Вход: wb — открытый workbook (openpyxl).
        Выход:
            True — если у ВСЕХ листов max_row is None или max_row <= 1.
            False — если хотя бы у одного листа max_row > 1.
            False — при любой ошибке (консервативно, чтобы случайно
                    не переоткрывать нормальный файл).

        Роль: решает, нужен ли fallback на read_only=False.
        """
        try:
            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                max_row = sheet.max_row
                # Любой лист с реальными данными снимает подозрение.
                if max_row is None or max_row > 1:
                    return False
            # Дошли до конца — все листы «схлопнуты».
            return True
        except Exception:
            # Ошибка чтения max_row — не рискуем, считаем файл нормальным.
            return False

    @staticmethod
    def find_header_row_and_columns(sheet, header_variants: dict,
                                    max_rows: int = 15,
                                    max_cols: int = 20) -> tuple:
        """Ищет строку с заголовками и соответствие «поле → индекс столбца».

        Вход:
            sheet — лист openpyxl (или адаптер XlsReader/CsvReader).
            header_variants — dict {поле: [варианты заголовков]}.
            max_rows — сколько первых строк сканировать.
            max_cols — сколько первых столбцов сканировать.

        Выход:
            (row_index, columns_dict) — 1-based номер строки и
            dict {поле: 0-based индекс столбца}.
            (None, None) — если строка не найдена.

        Роль:
            Точный перенос DataLoader._find_header_row_and_columns.
            Правила:
              - Ранний выход, если в строке нашлись name + shk
                или name + count.
              - Иначе запоминается лучшая строка по score
                (число найденных полей).
              - Порог: best_score >= 2 и наличие name в лучшей
                строке. Иначе — (None, None).
        """
        all_variants = {}
        for field, variants in header_variants.items():
            for v in variants:
                all_variants[v.lower().strip()] = field

        best_score = 0
        best_row = None
        best_columns = {}

        for row_idx in range(1, min(sheet.max_row, max_rows) + 1):
            header_row = list(sheet.iter_rows(
                min_row=row_idx, max_row=row_idx, values_only=True
            ))[0]
            if not header_row:
                continue
            header_row = header_row[:max_cols]

            found_columns = {}
            score = 0
            for col_idx, cell in enumerate(header_row):
                if cell is None:
                    continue
                cell_clean = str(cell).strip().lower()
                if cell_clean in all_variants:
                    field = all_variants[cell_clean]
                    if field not in found_columns:
                        found_columns[field] = col_idx
                        score += 1

            if 'name' in found_columns and 'shk' in found_columns:
                return row_idx, found_columns
            if 'name' in found_columns and 'count' in found_columns:
                return row_idx, found_columns

            if score > best_score:
                best_score = score
                best_row = row_idx
                best_columns = found_columns

        if best_row is None or best_score < 2:
            return None, None
        if 'name' not in best_columns:
            return None, None
        return best_row, best_columns

    @staticmethod
    def find_seller_by_sheet_name(wb, sellers, sheet_name):
        normalized_sheet = TextUtils.normalize(sheet_name)
        for seller in sellers:
            if any(TextUtils.normalize(key) == normalized_sheet for key in seller.keys):
                return seller
        return None


    @staticmethod
    def read_column_values(sheet, col_index, start_row=2):
        values = []
        for row in sheet.iter_rows(min_row=start_row, values_only=True):
            if len(row) >= col_index and row[col_index - 1] is not None:
                val = str(row[col_index - 1]).strip()
                if val:
                    values.append(val)
        return values

    @staticmethod
    def filter_and_clean_rows(sheet, status_col=None, owner_col=None,
                              allowed_owners=None, required_status=None):
        filtered_rows = []
        stats = {'status': {}, 'owner': {}, 'total_removed': 0, 'total_kept': 0}

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            keep = True

            if status_col is not None and required_status is not None:
                status_val = row[status_col - 1] if len(row) >= status_col else None
                status_str = str(status_val).strip() if status_val is not None else ""
                if status_str.upper() != required_status.upper():
                    stats['status'][status_str or "(пусто)"] = stats['status'].get(status_str or "(пусто)", 0) + 1
                    keep = False

            if keep and owner_col is not None and allowed_owners is not None:
                owner_val = row[owner_col - 1] if len(row) >= owner_col else None
                owner_str = str(owner_val).strip() if owner_val is not None else ""
                if not owner_str:
                    stats['owner']["(пусто)"] = stats['owner'].get("(пусто)", 0) + 1
                    keep = False
                else:
                    norm_owner = TextUtils.normalize(owner_str)
                    if norm_owner not in allowed_owners:
                        stats['owner'][owner_str] = stats['owner'].get(owner_str, 0) + 1
                        keep = False

            if keep:
                filtered_rows.append((row_idx, row))
                stats['total_kept'] += 1
            else:
                stats['total_removed'] += 1

        return filtered_rows, stats

    @staticmethod
    def is_file_empty(file_path, sheet_name=None) -> bool:
        """Проверяет, что файл пуст (только заголовки).

        Использует WorkbookOpener.open(logger=None, read_only=False).
        Если файл не открылся → True.
        """
        wb = WorkbookOpener.open(file_path, logger=None, read_only=False)
        if wb is None:
            return True
        try:
            ws = wb[sheet_name] if sheet_name else wb.active
            return ws.max_row == 1
        finally:
            try:
                wb.close()
            except Exception:
                pass


    @staticmethod
    def is_column_numeric(file_path, price_col: int, kiz_col: int,
                          logger, header: str = "КИЗ") -> bool:
        """Проверяет, что все непустые цены в столбце — числа.

        Вход:
            file_path — путь к файлу.
            price_col — номер столбца с ценой (1-based).
            kiz_col — номер столбца с КИЗ (1-based).
            logger — LoggerV2 для сообщений об ошибках открытия.
            header — значение КИЗ-ячейки в шапке, которое пропускается
                     (по умолчанию "КИЗ").

        Выход:
            True — если во всех строках с непустым КИЗ цена числовая.
            False — если хотя бы одна такая цена не число; если файл
                    не открылся; если строк с КИЗ нет вовсе.

        Роль:
            Определяет, обработан ли уже файл — все ли цены
            проставлены. Строки без КИЗ и строка заголовка
            (значение == header) в проверке не участвуют.
            Ранний выход False при первой нечисловой цене.
        """
        wb = WorkbookOpener.open(
            file_path, logger=logger, description="проверка итога",
            read_only=False,
        )
        if wb is None:
            return False
        try:
            sheet = wb.active
            if sheet.max_row < 2:
                return False
            for row_idx in range(2, sheet.max_row + 1):
                kiz_cell = sheet.cell(row=row_idx, column=kiz_col)
                kiz = (
                    str(kiz_cell.value).strip()
                    if kiz_cell.value is not None else ""
                )
                if not kiz or kiz == header:
                    continue
                price_cell = sheet.cell(row=row_idx, column=price_col)
                if not NumberParser.is_numeric(price_cell.value):
                    return False
            return True
        finally:
            wb.close()

class CsvReader:
    """Адаптер для чтения CSV-файлов как Excel-листа."""

    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self._sheet_names = ['Sheet1']
        self._active_sheet = 'Sheet1'
        self._dialect = None
        self._max_row = None
        self._max_column = None
        self._data = None
        self._is_closed = False

    def _detect_dialect(self):
        if self._dialect is not None:
            return self._dialect
        with open(self.file_path, 'r', encoding='utf-8-sig') as f:
            sample = f.read(1024)
            f.seek(0)
            try:
                self._dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                self._dialect = csv.excel()
            return self._dialect

    def _load_data(self):
        if self._data is not None:
            return
        if self._is_closed:
            return
        dialect = self._detect_dialect()
        self._data = []
        with open(self.file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, dialect)
            for row in reader:
                self._data.append(row)
        self._max_row = len(self._data)
        self._max_column = max((len(row) for row in self._data), default=0)

    def close(self):
        self._is_closed = True
        self._data = None

    @property
    def sheetnames(self):
        return self._sheet_names

    @property
    def active(self):
        return self

    @property
    def max_row(self):
        self._load_data()
        return self._max_row

    @property
    def max_column(self):
        self._load_data()
        return self._max_column

    def iter_rows(self, min_row=1, max_row=None, values_only=True):
        if not values_only:
            raise NotImplementedError("Только values_only=True поддерживается для CSV")
        self._load_data()
        if self._is_closed or self._data is None:
            return
        start = min_row - 1
        end = self._max_row if max_row is None else min(max_row, self._max_row)
        for row_idx in range(start, end):
            if row_idx < len(self._data):
                yield self._data[row_idx]

class XlsReader:
    """Адаптер для чтения .xls файлов через xlrd."""

    def __init__(self, workbook):
        self.workbook = workbook
        self._sheet_names = workbook.sheet_names()
        self._active = None
        self._is_closed = False

    def close(self):
        self._is_closed = True
        if hasattr(self.workbook, 'release_resources'):
            self.workbook.release_resources()

    @property
    def sheetnames(self):
        return self._sheet_names

    @property
    def active(self):
        if self._active is None and not self._is_closed:
            self._active = self.workbook.sheet_by_index(0)
        return self._active

    @property
    def max_row(self):
        if self._is_closed:
            return 0
        return self.active.nrows

    @property
    def max_column(self):
        if self._is_closed:
            return 0
        return self.active.ncols

    def iter_rows(self, min_row=1, max_row=None, values_only=True):
        if self._is_closed:
            return
        sheet = self.active
        if not values_only:
            raise NotImplementedError("Только values_only=True поддерживается для .xls")
        start = min_row - 1
        end = min(sheet.nrows, max_row) if max_row is not None else sheet.nrows
        for row_idx in range(start, end):
            yield sheet.row_values(row_idx)

class CsvNormalizer:
    """
    Нормализует CSV-файлы поставок: извлекает GTIN, КИЗ, название из всех ячеек строки.
    Валидирует данные и логирует некорректные строки.
    """

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.dialect = None

    def _detect_dialect(self):
        if self.dialect is not None:
            return self.dialect
        with open(self.file_path, 'r', encoding='utf-8-sig') as f:
            sample = f.read(1024)
            f.seek(0)
            try:
                self.dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                self.dialect = csv.excel()
            return self.dialect

    def normalize_rows(self, log_callback=None) -> Tuple[List[Dict[str, str]], List[str]]:
        """
        Нормализует данные по строкам: извлекает GTIN, КИЗ, название из всех ячеек строки.
        Возвращает (валидные_записи, список_некорректных_строк).
        """
        dialect = self._detect_dialect()
        rows = []
        with open(self.file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f, dialect)
            for row in reader:
                rows.append(row)

        if not rows:
            return [], []

        # Пропускаем заголовок (первая строка)
        data_rows = rows[1:] if len(rows) > 1 else []

        valid_rows = []
        invalid_log = []

        for row_idx, row in enumerate(data_rows, start=2):
            gtin = None
            kiz = None
            name = None
            count = None

            # Сканируем все ячейки строки
            for cell in row:
                if not cell:
                    continue
                cell_str = str(cell).strip()
                if not cell_str:
                    continue

                # Проверяем на GTIN (число 13-14 цифр, часто начинается с 46)
                if re.match(r'^46\d{11,12}$', cell_str):
                    gtin = cell_str
                    continue
                elif re.match(r'^\d{13,14}$', cell_str) and not gtin:
                    gtin = cell_str
                    continue

                # Проверяем на КИЗ (начинается с 01, длина > 31)
                if cell_str.startswith('01') and len(cell_str) > 31:
                    # Берём только до первого разделителя  (ASCII 29)
                    if '' in cell_str:
                        kiz = cell_str.split('')[0]
                    else:
                        kiz = cell_str
                    continue

                # Проверяем на название (длинный текст > 31 символов с пробелами)
                if len(cell_str) > 31 and ' ' in cell_str and not cell_str.isdigit():
                    name = cell_str
                    continue

                # Проверяем на количество (если есть отдельный числовой столбец)
                if cell_str.isdigit() and len(cell_str) <= 6 and not gtin:
                    # Если число меньше 10000 и это не GTIN, считаем количеством
                    if int(cell_str) < 10000:
                        count = cell_str

            # Валидация: строка валидна, если есть GTIN и хотя бы один из (КИЗ, название)
            if gtin and (kiz or name):
                record = {
                    'gtin': gtin,
                    'kiz': kiz if kiz else '',
                    'name': name if name else '',
                    'count': '1',  # по умолчанию 1
                    'source_file': self.file_path.name
                }
                valid_rows.append(record)
            else:
                # Формируем лог-сообщение
                missing = []
                if not gtin:
                    missing.append("GTIN")
                if not kiz and not name:
                    missing.append("КИЗ/название")
                invalid_log.append(f"Строка {row_idx}: отсутствуют {', '.join(missing)}")
                invalid_log.append(f"  Данные: {row[:10]}")  # только первые 10 ячеек для краткости

        return valid_rows, invalid_log

class WorkbookOpener:
    """Единая точка открытия workbook.

    Роль:
        Определяет формат по расширению, делегирует в
        ExcelHelper._open_data_file. Обрабатывает битый dimension
        для .xlsx/.xlsm при read_only=True. Не бросает исключений:
        на ошибке — logger.critical + return None.
    """

    @staticmethod
    def open(path, logger=None, description="файл",
             read_only=True, auto_fallback=True):
        """Открывает workbook.

        Вход:
            path — путь к файлу (.xlsx/.xlsm/.xls/.csv).
            logger — LoggerV2 или None.
            description — описание для сообщений.
            read_only — режим чтения для .xlsx/.xlsm.
            auto_fallback — переоткрывать ли при битом dimension.

        Выход:
            openpyxl.Workbook / XlsReader / CsvReader или None.

        Роль:
            - data_only=True всегда (параметр не выносится).
            - Пробует открыть через ExcelHelper._open_data_file.
            - Если ошибка/None → logger.critical(can_influence=False)
              или молча (logger=None) → return None.
            - Fallback для .xlsx/.xlsm при read_only=True:
              _is_dimension_broken → close → logger.warning →
              переоткрытие с read_only=False. Если не удалось →
              logger.critical, return None.
            - Для .xls/.csv fallback не срабатывает.
        """
        path_obj = Path(path)

        # 1. Первичное открытие.
        try:
            wb = ExcelHelper._open_data_file(
                path_obj, read_only=read_only, data_only=True,
            )
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка открытия {description}: "
                    f"{path_obj.name} ({e})",
                    can_influence=False,
                )
            return None

        if wb is None:
            if logger is not None:
                logger.critical(
                    f"Ошибка открытия {description}: {path_obj.name}",
                    can_influence=False,
                )
            return None

        # 2. Fallback только для .xlsx/.xlsm при read_only=True.
        suffix = path_obj.suffix.lower()
        if auto_fallback and read_only and suffix in ('.xlsx', '.xlsm'):
            if ExcelHelper._is_dimension_broken(wb):
                try:
                    wb.close()
                except Exception:
                    pass
                if logger is not None:
                    logger.warning(
                        f"Файл {path_obj.name} не содержит корректного "
                        f"dimension. Переоткрываю без read_only."
                    )
                try:
                    wb = ExcelHelper._open_data_file(
                        path_obj, read_only=False, data_only=True,
                    )
                except Exception as e:
                    if logger is not None:
                        logger.critical(
                            f"Ошибка повторного открытия {description}: "
                            f"{path_obj.name} ({e})",
                            can_influence=False,
                        )
                    return None
                if wb is None:
                    if logger is not None:
                        logger.critical(
                            f"Ошибка повторного открытия {description}: "
                            f"{path_obj.name}",
                            can_influence=False,
                        )
                    return None

        return wb

class WorkbookWriter:
    """Единая точка записи workbook.

    Роль:
        Четыре публичных метода. Использует Batcher(threshold=50)
        для буферизации строк внутри одного вызова. Сохранение
        на диск — само. При ошибке → logger.critical(can_influence=False),
        return False.

    Атрибуты класса:
        _BATCH_THRESHOLD — порог промежуточного flush для Batcher.
    """

    _BATCH_THRESHOLD = 50

    @staticmethod
    def create(path, headers, rows=None, sheet_name="Лист1",
               logger=None) -> bool:
        """Создаёт новый файл с заголовками и (опционально) строками.

        Вход:
            path — путь к создаваемому .xlsx.
            headers — список заголовков. None или пусто → шапка не пишется.
            rows — итерируемое строк. None или пусто → только заголовки.
            sheet_name — имя листа.
            logger — LoggerV2 или None.

        Выход:
            True — файл создан; False — ошибка.

        Роль:
            Объединяет create_report_workbook и
            create_workbook_with_headers. Буферизация строк —
            через Batcher(threshold=50).
        """
        path_obj = Path(path)
        wb = None
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = sheet_name
            if headers:
                ws.append(headers)

            if rows:
                buffer: list = []

                def flush():
                    for r in buffer:
                        ws.append(r)
                    buffer.clear()

                batcher = Batcher(
                    flush, threshold=WorkbookWriter._BATCH_THRESHOLD,
                )
                with batcher.batch():
                    for row in rows:
                        buffer.append(row)
                        batcher.mark_dirty()

            wb.save(path_obj)
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка создания файла {path_obj.name}: {e}",
                    can_influence=False,
                )
            return False
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    @staticmethod
    def overwrite(path, headers, rows, sheet_name="Лист1",
                  logger=None) -> bool:
        """Перезаписывает существующий файл. Заменяет rewrite_sheet.

        Вход:
            path — путь к файлу (содержимое затирается).
            headers — список заголовков. None или пусто → шапка не пишется.
            rows — итерируемое строк.
            sheet_name — имя листа.
            logger — LoggerV2 или None.

        Выход:
            True — файл записан; False — ошибка.

        Роль:
            Создаёт новый Workbook по тому же пути — исходное
            содержимое полностью заменяется. Буферизация строк —
            через Batcher(threshold=50).
        """
        path_obj = Path(path)
        wb = None
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = sheet_name
            if headers:
                ws.append(headers)

            if rows:
                buffer: list = []

                def flush():
                    for r in buffer:
                        ws.append(r)
                    buffer.clear()

                batcher = Batcher(
                    flush, threshold=WorkbookWriter._BATCH_THRESHOLD,
                )
                with batcher.batch():
                    for row in rows:
                        buffer.append(row)
                        batcher.mark_dirty()

            wb.save(path_obj)
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка перезаписи файла {path_obj.name}: {e}",
                    can_influence=False,
                )
            return False
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    @staticmethod
    def append(path, row, headers=None, logger=None) -> bool:
        """Дописывает одну строку.

        Вход:
            path — путь к .xlsx.
            row — список значений одной строки.
            headers — заголовки. Используются только если файла
                      нет — тогда создаётся с ними.
            logger — LoggerV2 или None.

        Выход:
            True — успех; False — ошибка.

        Роль:
            Если файл существует → открывает и добавляет строку;
            иначе создаёт с headers. Заменяет append_row_to_file.
        """
        path_obj = Path(path)
        wb = None
        try:
            if path_obj.exists():
                wb = openpyxl.load_workbook(path_obj)
            else:
                wb = Workbook()
                if headers:
                    wb.active.append(headers)
            wb.active.append(row)
            wb.save(path_obj)
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка записи в {path_obj.name}: {e}",
                    can_influence=False,
                )
            return False
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    @staticmethod
    def append_rows(path, rows, logger=None) -> bool:
        """Дописывает пачку строк в существующий файл.

        Вход:
            path — путь к существующему .xlsx файлу.
            rows — итерируемое строк для записи.
            logger — LoggerV2 или None.

        Выход:
            True — успех, False — ошибка.

        Роль:
            Используется SalesAccumulatorService для сценария
            «append к существующему файлу продаж». Открывает файл,
            добавляет строки через Batcher(50), сохраняет.
        """
        path_obj = Path(path)
        wb = None
        try:
            wb = openpyxl.load_workbook(path_obj)
            ws = wb.active

            buffer: list = []

            def flush():
                for r in buffer:
                    ws.append(r)
                buffer.clear()

            batcher = Batcher(
                flush, threshold=WorkbookWriter._BATCH_THRESHOLD,
            )
            with batcher.batch():
                for row in rows:
                    buffer.append(row)
                    batcher.mark_dirty()

            wb.save(path_obj)
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка записи в {path_obj.name}: {e}",
                    can_influence=False,
                )
            return False
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass