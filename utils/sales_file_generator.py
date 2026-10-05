import random
from pathlib import Path
from typing import List, Dict, Optional, TYPE_CHECKING
from utils.excel_helper import (
    ExcelHelper, WorkbookOpener, WorkbookWriter,
)
from utils.text_utils import TextUtils
from utils.kiz_utils import KizUtils
from services.subservices.logging import LoggerV2
if TYPE_CHECKING:
    from services.subservices.logging import LogManagerV2

class SalesFileGenerator:
    """
    Генератор файлов продаж (Excel) с новой структурой.
    Имя файла: "{от кого} - {кому} : {ИНН}.xlsx"
    Столбцы: Наименование продукта, КИЗ (31 символов), GTIN (с 3 по 16), Цена (случайная 10-20)
    """

    DEFAULT_HEADERS = [
        "Наименование продукта",
        "КИЗ",
        "GTIN",
        "НДС"
    ]

    def __init__(self, work_folder: Path, headers: Optional[List[str]] = None,
                 logger: Optional[LoggerV2] = None):
        """Генератор файлов продаж.

        Вход:
            work_folder — папка, куда складываются файлы.
            headers — заголовки столбцов; None → DEFAULT_HEADERS.
            logger — опциональный LoggerV2. Если передан, отладочные
                     сообщения идут через него (в debug.txt при
                     включённом debug). Если нет — fallback на print.

        Роль:
            Сервис может создавать генератор с логгером V2 (новый путь)
            или без него (легаси-путь). Поведение не ломается.
        """
        self.work_folder = work_folder
        self.headers = headers or self.DEFAULT_HEADERS
        self.created_files: List[Path] = []
        self._stats: Dict[tuple, int] = {}
        self._logger = logger
        self._file_to_receiver: Dict[Path, str] = {}

    def add_sale_row(self,
                     from_seller_name: str,
                     to_seller_name: str,
                     to_seller_inn: str,
                     product_name: str,
                     raw_kiz: str,
                     brand: Optional[str] = None,
                     owner_company: Optional[str] = None) -> Path:
        """
        Добавляет строку продажи в файл.
        :param from_seller_name: продавец-отправитель (для имени файла)
        :param to_seller_name: продавец-получатель (для имени файла)
        :param to_seller_inn: ИНН получателя (для имени файла)
        :param product_name: наименование продукта (записывается в файл)
        :param raw_kiz: полный КИЗ (из него будет взят сокращённый и GTIN)
        :param brand: бренд (не используется в новой структуре, но передаётся для совместимости)
        :param owner_company: компания-владелец (не используется, передаётся для совместимости)
        :return: путь к файлу
        """
        # Получаем сокращённый КИЗ (31 символ).
        # NEW: передаём logger — детальные сообщения от KizUtils уйдут в debug.
        storage_list = KizUtils.clean_kiz_for_storage(raw_kiz, logger=self._logger)
        if not storage_list:
            raise ValueError(f"Не удалось получить сокращённый КИЗ из {raw_kiz[:30]}...")
        kiz_short = storage_list[0]

        # GTIN – символы с 3 по 16 (индексы 2..15)
        gtin = kiz_short[2:16] if len(kiz_short) >= 16 else ""

        # ндс 5%
        vad = "5%"

        # Имя файла
        safe_from = TextUtils.sanitize_filename(from_seller_name)
        safe_to = TextUtils.sanitize_filename(to_seller_name)
        file_name = f"{safe_from} - {safe_to} _ {to_seller_inn}.xlsx"
        file_path = self.work_folder / file_name

        row_data = [
            product_name,
            kiz_short,
            gtin,
            vad
        ]

        ok = WorkbookWriter.append(
            file_path, row_data, headers=self.headers, logger=self._logger,
        )
        if not ok:
            raise RuntimeError(f"Ошибка записи в {file_path}")

        if file_path not in self.created_files:
            self.created_files.append(file_path)
            self._file_to_receiver[file_path] = to_seller_name

        key = (from_seller_name, to_seller_name)
        self._stats[key] = self._stats.get(key, 0) + 1

        return file_path

    def get_created_files(self) -> List[Path]:
        return self.created_files

    def get_receiver_name(self, file_path) -> Optional[str]:
        """Возвращает имя получателя для созданного файла продаж.

        Вход:
            file_path — путь к файлу (Path или str).
        Выход:
            str — сырое имя получателя (как передавалось в
            add_sale_row), либо None, если файл не создавался
            в этой сессии.

        Роль: используется сервисом и UI для подписи кнопок
              в диалоге выбора получателя.
        """
        return self._file_to_receiver.get(Path(file_path))

    def remove_empty_files(self) -> int:
        """Удаляет пустые файлы продаж из списка созданных.

        Вход: нет.
        Выход: количество удалённых файлов.
        Роль: после генерации часть файлов может остаться только с
              заголовками — их удаляем, чтобы не путать пользователя.
        """
        removed = 0
        for file_path in self.created_files[:]:
            if file_path.exists():
                size = file_path.stat().st_size
                # NEW: вместо print — _log_debug, сам выберет канал.
                self._log_debug(f"Проверка файла {file_path.name}, размер {size} байт")
                if ExcelHelper.is_file_empty(file_path):
                    self._log_debug(f"Файл {file_path.name} считается пустым, удаляем")
                    try:
                        file_path.unlink()
                        removed += 1
                        self.created_files.remove(file_path)
                        self._file_to_receiver.pop(file_path, None)
                    except Exception as e:
                        self._log_debug(f"Ошибка удаления {file_path.name}: {e}")
                else:
                    self._log_debug(f"Файл {file_path.name} не пустой, оставляем")
        return removed

    def get_stats(self) -> Dict[tuple, int]:
        return self._stats.copy()

    # ---------- Приватные помощники ----------

    def _log_debug(self, message: str) -> None:
        """Логирует отладочное сообщение через logger или через print.

        Вход: message — текст.
        Выход: нет.
        Роль: единая точка выбора канала. При наличии logger — debug-уровень
              (в debug.txt при включённом debug). Без logger — печать в stdout
              для обратной совместимости.
        """
        if self._logger is not None:
            self._logger.debug(message)
        else:
            # Префикс [DEBUG] только в fallback — Logger сам знает про уровень.
            print(f"[DEBUG] {message}")

class SalesFileKizReader:
    """Читает КИЗы из файла продаж.

    Роль:
        Единая точка чтения КИЗов из второго столбца файла продаж.
        Возвращает set[str]. Ошибки чтения не пробрасываются —
        возвращается пустое множество (аккумуляция продолжается).
    """

    # Индекс столбца с КИЗом (0-based): [Наименование, КИЗ, GTIN, Цена].
    # Единственный источник для всех потребителей, включая
    # SalesAccumulatorService и SalesFileRowsReader.
    KIZ_COLUMN_INDEX = 1

    @staticmethod
    def read(file_path) -> set:
        """Возвращает множество непустых КИЗов из файла.

        Вход:
            file_path — путь к файлу продаж (Path или str).

        Выход:
            set[str] — непустые КИЗы из второго столбца, без
            дубликатов. Пустое множество при ошибке чтения.

        Роль:
            Точный перенос SalesAccumulatorService._collect_kiz_set.
            Строки, короче KIZ_COLUMN_INDEX+1 или с пустым КИЗом,
            пропускаются.
        """
        wb = WorkbookOpener.open(file_path, logger=None, read_only=True)
        if wb is None:
            return set()

        try:
            sheet = wb.active
            kiz_set = set()
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) > SalesFileKizReader.KIZ_COLUMN_INDEX:
                    raw = row[SalesFileKizReader.KIZ_COLUMN_INDEX]
                    if raw:
                        kiz = str(raw).strip()
                        if kiz:
                            kiz_set.add(kiz)
            return kiz_set
        finally:
            try:
                wb.close()
            except Exception:
                pass

    @staticmethod
    def read_with_counts(file_path) -> dict:
        """Читает КИЗы из файла продаж и считает их повторения.

        Вход:
            file_path — путь к файлу продаж (Path или str).

        Выход:
            dict[str, int] — {kiz: count} по непустым КИЗам из
            второго столбца. Пустые ячейки игнорируются. Пустой
            словарь при ошибке открытия.

        Роль:
            Используется KizDuplicatesFinder для поиска дублей.
            Открытие — через WorkbookOpener.open(read_only=True),
            закрытие — в finally.
        """
        wb = WorkbookOpener.open(file_path, logger=None, read_only=True)
        if wb is None:
            return {}

        try:
            sheet = wb.active
            counts: dict = {}
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) > SalesFileKizReader.KIZ_COLUMN_INDEX:
                    raw = row[SalesFileKizReader.KIZ_COLUMN_INDEX]
                    if raw is None:
                        continue
                    kiz = str(raw).strip()
                    if kiz:
                        counts[kiz] = counts.get(kiz, 0) + 1
            return counts
        finally:
            try:
                wb.close()
            except Exception:
                pass

class SalesFileRowsReader:
    """Читает строки файла продаж с фильтром по значению столбца.

    Роль:
        Единая точка чтения строк файла продаж с фильтром.
        Заменяет логику ExcelHelper.copy_rows_by_column_value на
        «читающей» стороне. Возвращает заголовок и отфильтрованные
        строки. Запись результата — ответственность WorkbookWriter.
    """

    @staticmethod
    def read_filtered(file_path, column_index, allowed_values,
                      logger=None) -> tuple:
        """Читает строки с фильтром по значению столбца.

        Вход:
            file_path — путь к файлу продаж.
            column_index — 0-based индекс столбца для фильтра.
            allowed_values — set/коллекция допустимых значений
                             (сравнение по str(value).strip()).
            logger — LoggerV2 или None.

        Выход:
            (header, rows):
                header — list значений первой строки файла.
                rows — list кортежей строк, прошедших фильтр.
            При ошибке открытия — ([], []).

        Роль:
            Единая точка чтения отфильтрованных строк. Открывает
            через WorkbookOpener.open(read_only=True). Строки, где
            ячейка column_index пустая или не в allowed_values,
            пропускаются.
        """
        wb = WorkbookOpener.open(file_path, logger=logger, read_only=True)
        if wb is None:
            return [], []

        try:
            sheet = wb.active
            header = [cell.value for cell in sheet[1]]
            rows: list = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) > column_index:
                    cell = row[column_index]
                    if cell and str(cell).strip() in allowed_values:
                        rows.append(row)
            return header, rows
        finally:
            try:
                wb.close()
            except Exception:
                pass

    @staticmethod
    def _rewrite_rows(file_path, header, rows, logger) -> bool:
        """Перезаписывает файл продаж новым набором строк.

        Вход:
            file_path — путь к файлу.
            header — список значений заголовков.
            rows — список кортежей/списков строк.
            logger — LoggerV2 или None.

        Выход:
            True — файл перезаписан;
            False — WorkbookWriter.overwrite вернул False.

        Роль: общая точка записи для remove_kiz и
              remove_duplicates_in_file.
        """
        return WorkbookWriter.overwrite(
            file_path, header, rows, logger=logger,
        )

    @staticmethod
    def remove_kiz(file_path, kiz, logger) -> bool:
        """Удаляет все строки с указанным КИЗом из файла продаж.

        Вход:
            file_path — путь к файлу продаж.
            kiz — 31-символьный КИЗ.
            logger — LoggerV2 или None.

        Выход:
            False — файл не открылся.
            True — во всех остальных случаях (в т.ч. если КИЗ
                   не найден или файл пуст).

        Роль:
            Открывает read-only, читает заголовок, проходит строки,
            собирает те, у которых КИЗ в столбце
            SalesFileKizReader.KIZ_COLUMN_INDEX не совпадает с kiz.
            Если удалений не было — True без перезаписи. Иначе —
            _rewrite_rows.
        """
        wb = WorkbookOpener.open(file_path, logger=logger, read_only=True)
        if wb is None:
            return False

        kiz_col = SalesFileKizReader.KIZ_COLUMN_INDEX
        header: list = []
        rows_kept: list = []
        removed_any = False
        try:
            sheet = wb.active
            header = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) > kiz_col:
                    cell = row[kiz_col]
                    if cell is not None and str(cell).strip() == kiz:
                        removed_any = True
                        continue
                rows_kept.append(row)
        finally:
            try:
                wb.close()
            except Exception:
                pass

        if not removed_any:
            return True
        return SalesFileRowsReader._rewrite_rows(
            file_path, header, rows_kept, logger,
        )

    # REPLACE: SalesFileRowsReader.remove_duplicates_in_file
    @staticmethod
    def remove_duplicates_in_file(file_path, logger) -> int:
        """Удаляет дублирующиеся строки по КИЗу внутри файла.

        Вход:
            file_path — путь к файлу продаж.
            logger — LoggerV2 или None.

        Выход:
            0 — файл не открылся или перезапись не удалась.
            int > 0 — количество удалённых строк-дублей.

        Роль:
            Оставляет первое вхождение КИЗа, остальные отбрасывает.
            Пустой КИЗ пропускается как есть. Заголовок сохраняется.
            Если удалений не было — 0 без перезаписи.
        """
        wb = WorkbookOpener.open(file_path, logger=logger, read_only=True)
        if wb is None:
            return 0

        kiz_col = SalesFileKizReader.KIZ_COLUMN_INDEX
        header: list = []
        rows_kept: list = []
        seen: set = set()
        removed = 0
        try:
            sheet = wb.active
            header = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                kiz = ""
                if len(row) > kiz_col:
                    cell = row[kiz_col]
                    if cell is not None:
                        kiz = str(cell).strip()
                if kiz:
                    if kiz in seen:
                        removed += 1
                        continue
                    seen.add(kiz)
                rows_kept.append(row)
        finally:
            try:
                wb.close()
            except Exception:
                pass

        if removed == 0:
            return 0
        ok = SalesFileRowsReader._rewrite_rows(
            file_path, header, rows_kept, logger,
        )
        if not ok:
            return 0
        return removed

class KizFilterDetailsWriter:
    """Пишет детальный лог фильтрации КИЗов при аккумуляции продаж.

    Роль:
        Единая точка записи log_фильтрация_КИЗов.txt. Создаёт
        отдельный LoggerV2 через переданный LogManagerV2 — так
        структура лога совпадает с основным log_аккумуляция.txt
        (те же префиксы [ts] [SEVERITY] [source]). Сохраняет
        заголовки, отступы и порядок сортировки из прежней версии
        SalesAccumulatorService._log_kiz_details.
    """

    @staticmethod
    def write(details: dict, logs_dir, log_manager_v2) -> None:
        """Пишет детальный лог фильтрации КИЗов.

        Вход:
            details — словарь {"kiz_from_fbs": set[str],
                               "files": [{"name": str,
                                          "total": int,
                                          "duplicates": set[str],
                                          "filtered": set[str]}, ...]}.
            logs_dir — папка «Логи» рабочей папки.
            log_manager_v2 — LogManagerV2 для создания логгера.

        Выход: нет.

        Роль:
            Создаёт логгер SalesAccumulatorService.kiz_filter с
            именем log_фильтрация_КИЗов.txt и построчно пишет
            структуру. Пустые строки и разделители сохранены —
            лог читается глазами, как и раньше.
        """
        logger = log_manager_v2.create_logger_v2(
            source="SalesAccumulatorService.kiz_filter",
            domain="sales",
            work_folder=logs_dir,
            log_filename="log_фильтрация_КИЗов.txt",
        )

        logger.report("=== ДЕТАЛИ ФИЛЬТРАЦИИ КИЗОВ ===")
        logger.report("")
        logger.report("КИЗы из ЧЗ_МП (приоритетные):")
        if details["kiz_from_fbs"]:
            for kiz in sorted(details["kiz_from_fbs"]):
                logger.report(f"  {kiz}")
        else:
            logger.report("  (нет)")
        logger.report("")
        logger.report("=" * 60)
        logger.report("")

        for file_info in details["files"]:
            logger.report(f"Файл: {file_info['name']}")
            logger.report(
                f"  Всего КИЗов в файле: {file_info['total']}"
            )
            logger.report(
                f"  Дубликаты (уже есть в ЧЗ_МП): "
                f"{len(file_info['duplicates'])}"
            )
            if file_info["duplicates"]:
                for kiz in sorted(file_info["duplicates"]):
                    logger.report(f"    {kiz}")
            else:
                logger.report("    (нет)")
            logger.report(
                f"  Отфильтрованные (добавлены): "
                f"{len(file_info['filtered'])}"
            )
            if file_info["filtered"]:
                for kiz in sorted(file_info["filtered"]):
                    logger.report(f"    {kiz}")
            else:
                logger.report("    (нет)")
            logger.report("")
            logger.report("-" * 40)