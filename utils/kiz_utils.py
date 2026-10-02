import re
from pathlib import Path
from typing import List, Optional
from utils.text_utils import TextUtils
from dataclasses import dataclass
from datetime import datetime
from services.subservices.logging import LoggerV2
from utils.parsers import DateParser

class KizUtils:
    """Утилиты для работы с КИЗами.

    Класс ведёт опциональную статистику обработки. Сервис перед
    началом вызывает start_stats(), после — pop_stats() и логирует
    итог через logger.info(). Это позволяет собрать агрегат без
    прокидывания счётчиков через параметры каждого вызова.

    Статистика — class-level состояние. Включается явно, поэтому
    случайные вызовы clean_kiz_* вне сессии сбора не засоряют счётчики.
    """

    # Флаг: собираем ли статистику прямо сейчас. Управляется методами
    # start_stats() / pop_stats(). По умолчанию выключен — вызовы
    # clean_kiz_* вне сессии просто не трогают счётчики.
    _stats_enabled: bool = False

    # Счётчики текущей сессии.
    #   dropped_short  — отброшено из-за длины < 31
    #   dropped_no_01  — отброшено, потому что не начинается с «01»
    #                    и внутри нет валидного «01»
    #   transliterated — КИЗ транслитерирован из кириллицы
    #   processed      — успешно обработано (вошло в результат)
    _stats: dict = {}

    @classmethod
    def start_stats(cls) -> None:
        """Начинает сессию сбора статистики.

        Вход: нет.
        Выход: нет.

        Роль: сервис вызывает перед циклом обработки КИЗов. Все
              последующие вызовы clean_kiz_full/clean_kiz_for_storage
              инкрементят счётчики. Предыдущая статистика обнуляется.
        """
        cls._stats_enabled = True
        cls._stats = {
            "dropped_short": 0,
            "dropped_no_01": 0,
            "transliterated": 0,
            "processed": 0,
        }

    @classmethod
    def pop_stats(cls) -> dict:
        """Возвращает накопленную статистику и выключает сбор.

        Вход: нет.
        Выход: dict с ключами dropped_short, dropped_no_01, transliterated,
               processed.

        Роль: сервис вызывает после цикла и логирует итог на уровне INFO.
              После вызова счётчики дальше не инкрементятся.
        """
        result = dict(cls._stats)
        cls._stats_enabled = False
        return result

    @staticmethod
    def clean_kiz_full(raw: str, logger: Optional[LoggerV2] = None) -> List[str]:
        """Полная очистка КИЗа.

        Вход:
            raw — исходная строка КИЗа.
            logger — опциональный LoggerV2. Если передан, детальные
                     события (отбрасывание, транслитерация) уходят
                     на уровне DEBUG.

        Выход: список очищенных полных КИЗов (без обрезания).
               Пустой список, если КИЗ некорректен.

        Роль: подготовительный этап перед clean_kiz_for_storage.
              Детали — в DEBUG, агрегат — накапливается в _stats для INFO.
        """
        if not raw:
            return []
        raw = str(raw).strip()
        if len(raw) < 31:
            # Счётчик и debug-сообщение
            if KizUtils._stats_enabled:
                KizUtils._stats["dropped_short"] += 1
            if logger is not None:
                logger.debug(
                    f"КИЗ отброшен: короче 31 символа ({len(raw)}): {raw[:30]}..."
                )
            return []

        # 1. Удаляем XML-представления управляющих символов.
        cleaned = re.sub(r'_x001[dD]_', '', raw)
        # 2. Удаляем настоящие управляющие символы (код ASCII < 32).
        cleaned = ''.join(ch for ch in cleaned if ord(ch) >= 32)

        # 3. Разделение слипшихся строк (если длина > 100).
        fragments = []
        if len(cleaned) > 100:
            pattern = re.compile(r'01\d{14}')
            match = pattern.search(cleaned, pos=80)
            if match:
                split_pos = match.start()
                if split_pos > 0 and len(cleaned) - split_pos >= 31:
                    fragments.append(cleaned[:split_pos])
                    fragments.append(cleaned[split_pos:])
            if not fragments:
                fragments.append(cleaned)
        else:
            fragments.append(cleaned)

        result = []
        for frag in fragments:
            # Проверка на начало «01» — обязательный признак КИЗа.
            if not frag.startswith("01"):
                pos_01 = frag.find("01")
                if pos_01 != -1 and len(frag) - pos_01 >= 31:
                    # Сдвигаем фрагмент до ближайшего «01» — отсекаем мусор.
                    frag = frag[pos_01:]
                else:
                    if KizUtils._stats_enabled:
                        KizUtils._stats["dropped_no_01"] += 1
                    if logger is not None:
                        logger.debug(
                            f"КИЗ отброшен: не начинается с 01 и нет валидного "
                            f"'01' внутри: {frag[:30]}..."
                        )
                    continue
            if len(frag) < 31:
                if KizUtils._stats_enabled:
                    KizUtils._stats["dropped_short"] += 1
                if logger is not None:
                    logger.debug(f"КИЗ отброшен: фрагмент короче 31: {frag[:30]}...")
                continue
            if TextUtils.is_cyrillic(frag):
                # Транслитерация кириллицы в латиницу для совместимости.
                if KizUtils._stats_enabled:
                    KizUtils._stats["transliterated"] += 1
                if logger is not None:
                    logger.debug(f"КИЗ транслитерирован: {frag[:30]}...")
                frag = TextUtils.keyboard_translit(frag)

            cleaned_frag = ''.join(ch for ch in frag if 32 <= ord(ch) <= 126)
            if len(cleaned_frag) < 31:
                if KizUtils._stats_enabled:
                    KizUtils._stats["dropped_short"] += 1
                if logger is not None:
                    logger.debug(
                        f"КИЗ отброшен после очистки непечатаемых символов: "
                        f"{cleaned_frag[:30]}..."
                    )
                continue
            frag = cleaned_frag

            result.append(frag)

        # Успешно обработанные в этой порции.
        if KizUtils._stats_enabled:
            KizUtils._stats["processed"] += len(result)

        return result

    @staticmethod
    def clean_kiz_for_storage(raw: str, logger: Optional[LoggerV2] = None) -> List[str]:
        """Очищает КИЗ и обрезает до 31 символа.

        Вход:
            raw — исходная строка КИЗа.
            logger — опциональный LoggerV2 (прокидывается в clean_kiz_full).

        Выход: список обрезанных КИЗов.

        Роль: финальная подготовка КИЗа для хранения в used_kiz.json.
              Вся детальная диагностика и счётчики — в clean_kiz_full.
        """
        full_list = KizUtils.clean_kiz_full(raw, logger=logger)
        if not full_list:
            return []
        result = []
        for full_kiz in full_list:
            if len(full_kiz) >= 31:
                result.append(full_kiz[:31])
        return result

    @staticmethod
    def filter_for_removal(kiz_to_brand_data, brand_key_to_brand,
                           logger=None):
        """Отбирает КИЗы, чей бренд помечен requires_saving=False.

        Вход:
            kiz_to_brand_data — dict[str, tuple[str, str]]:
                {kiz: (нормализованный_ключ, сырая_строка_бренда)}.
            brand_key_to_brand — dict[str, Brand]: {normalized_key: Brand}.
            logger — LoggerV2 или None.

        Выход:
            (to_delete, stats, brands_unknown):
                to_delete — set[str]: КИЗы с requires_saving is False.
                stats — dict с ключами total, empty_brand, unknown_brand,
                        recognized, saved, deleted, top_deleted.
                brands_unknown — dict[str, list[str]]:
                        {норм_ключ: [сырая_1, сырая_2, ...]} — только
                        для неизвестных непустых брендов. Порядок
                        ключей и сырых строк — по мере обнаружения,
                        дедуп сырых — по точному совпадению.

        Роль:
            Матчинг — точное совпадение нормализованных строк.
            Пустой brand_key → empty_brand, КИЗ сохраняется.
            Неизвестный brand_key → unknown_brand + сырая строка
            в brands_unknown, КИЗ сохраняется. Известный бренд →
            recognized + развилка saved/deleted. top_deleted —
            топ-10 брендов по количеству удалённых КИЗов.
        """
        to_delete: set = set()
        stats = {
            "total": 0,
            "empty_brand": 0,
            "unknown_brand": 0,
            "recognized": 0,
            "saved": 0,
            "deleted": 0,
            "top_deleted": [],
        }
        top_deleted: dict = {}
        brands_unknown: dict = {}

        for kiz, (brand_key, raw_brand) in kiz_to_brand_data.items():
            if not brand_key:
                stats["empty_brand"] += 1
                if logger is not None:
                    logger.debug(
                        f"КИЗ {kiz} → brand_key '' → пустой бренд"
                    )
                continue

            brand = brand_key_to_brand.get(brand_key)
            if brand is None:
                stats["unknown_brand"] += 1
                bucket = brands_unknown.setdefault(brand_key, [])
                if raw_brand not in bucket:
                    bucket.append(raw_brand)
                if logger is not None:
                    logger.debug(
                        f"КИЗ {kiz} → brand_key '{brand_key}' → "
                        f"Brand не найден (сырое: {raw_brand!r})"
                    )
                continue

            stats["recognized"] += 1

            if brand.requires_saving is False:
                to_delete.add(kiz)
                stats["deleted"] += 1
                top_deleted[brand.name] = (
                        top_deleted.get(brand.name, 0) + 1
                )
                if logger is not None:
                    logger.debug(
                        f"КИЗ {kiz} → brand_key '{brand_key}' → "
                        f"Brand {brand.name} → удалён"
                    )
            else:
                stats["saved"] += 1
                if logger is not None:
                    logger.debug(
                        f"КИЗ {kiz} → brand_key '{brand_key}' → "
                        f"Brand {brand.name} → сохранён"
                    )

        stats["total"] = len(kiz_to_brand_data)
        stats["top_deleted"] = sorted(
            top_deleted.items(), key=lambda x: -x[1],
        )[:10]

        return to_delete, stats, brands_unknown

@dataclass
class ChosenKiz:
    """Выбранное вхождение КИЗа из группы дубликатов.

    Роль:
        Результат выбора «самого позднего» вхождения одного и того
        же storage_kiz из листа «КИЗ» отчёта МП. Возвращается
        методом KizOccurrences.pick_latest и используется
        WBReportReader/OZONReportReader для валидации и записи
        в буфер цен.

    Поля:
        full_kiz — полный КИЗ выбранного вхождения.
        sale_date_str — дата продажи в формате «%H:%M:%S %d.%m.%Y»
                        или None, если дату не удалось получить.
        price — цена из отчёта, если она числовая и положительная;
                иначе None.
        skipped_dup_count — сколько вхождений той же группы были
                            отброшены как дубликаты (len(group) - 1).
    """
    full_kiz: str
    sale_date_str: Optional[str]
    price: Optional[float]
    skipped_dup_count: int

class KizOccurrences:
    """Группировка вхождений КИЗов из отчёта МП.

    Роль:
        Собирает все вхождения одного storage_kiz из листа «КИЗ»
        (WB) или «Отчет» (Ozon). Из группы выбирается одно —
        с самым поздним ключом сортировки. Остальные считаются
        дубликатами.

        Ключ сортировки — полиморфный: для WB это строка task_num
        (дата берётся из отдельного словаря task_to_date), для
        Ozon — уже готовый datetime из ячейки. Логику извлечения
        ключа задаёт вызывающий через key_func в pick_latest.

    Поля:
        _entries — dict[storage_kiz, list[tuple[full_kiz, sort_value, price]]].
                   sort_value: str (WB) или datetime (Ozon).
    """

    def __init__(self) -> None:
        """Конструктор.

        Вход: нет.
        Роль: создаёт пустую структуру — словарь групп.
        """
        self._entries: dict[
            str, List[tuple[str, object, Optional[float]]]
        ] = {}

    def add(self, storage_kiz: str, full_kiz: str,
            sort_value, price_value: Optional[float]) -> None:
        """Добавляет одно вхождение КИЗа.

        Вход:
            storage_kiz — 31-символьный КИЗ, используется как ключ группы.
            full_kiz — полный КИЗ этого вхождения.
            sort_value — ключ сортировки: task_num (str) для WB
                         или datetime для Ozon.
            price_value — цена из отчёта или None.

        Выход: нет.
        Роль: накапливает вхождения. Группа создаётся лениво
              через setdefault.
        """
        self._entries.setdefault(storage_kiz, []).append(
            (full_kiz, sort_value, price_value)
        )

    def pick_latest(self, storage_kiz: str, key_func) -> Optional[ChosenKiz]:
        """Выбирает самое позднее вхождение из группы.

        Вход:
            storage_kiz — ключ группы.
            key_func — Callable[[tuple], Optional[datetime]]. Извлекает
                       ключ сортировки из entry (full_kiz, sort_value,
                       price). Возвращает datetime или None.

        Выход:
            ChosenKiz выбранного вхождения либо None, если группы нет.

        Роль:
            Сортирует вхождения группы по дате в порядке убывания
            и берёт первое. Если key_func вернул None — считается
            datetime.min (самое раннее), чтобы такое вхождение
            ушло в конец. sale_date_str формируется из datetime
            в формате «%H:%M:%S %d.%m.%Y»; если ключ не дал
            datetime — None. skipped_dup_count = len(group) - 1.
            sorted(reverse=True) — stable: при равенстве ключей
            порядок сохраняется («при равенстве — первое»).
        """
        entries = self._entries.get(storage_kiz)
        if not entries:
            return None

        def _sort_key(entry) -> datetime:
            """Ключ сортировки: datetime вхождения; datetime.min при None."""
            dt = key_func(entry)
            return dt or datetime.min

        entries_sorted = sorted(entries, key=_sort_key, reverse=True)
        chosen = entries_sorted[0]
        full_kiz, _sort_value, price_value = chosen

        dt = key_func(chosen)
        sale_date_str = (
            dt.strftime("%H:%M:%S %d.%m.%Y") if dt is not None else None
        )

        return ChosenKiz(
            full_kiz=full_kiz,
            sale_date_str=sale_date_str,
            price=price_value,
            skipped_dup_count=len(entries) - 1,
        )

    def total(self) -> int:
        """Количество уникальных КИЗов.

        Вход: нет.
        Выход: len(self._entries).
        Роль: используется сервисом для итоговой статистики.
        """
        return len(self._entries)

    def items(self):
        """Итератор по парам (storage_kiz, entries).

        Вход: нет.
        Выход: view dict.items().
        Роль: даёт вызывающему коду пройти по всем группам и
              выбрать по каждой через pick_latest.
        """
        return self._entries.items()

class KizDuplicatesFinder:
    """Поиск дублей КИЗов в файлах продаж.

    Роль:
        Единая точка анализа папки «Продажи». Возвращает два
        независимых результата: дубли внутри одного файла и
        КИЗы, встречающиеся в нескольких файлах. Без состояния —
        все методы @staticmethod.
    """

    @staticmethod
    def find(sales_dir, logger) -> tuple:
        """Находит внутрифайловые и межфайловые дубли КИЗов.

        Вход:
            sales_dir — Path к папке «Продажи».
            logger — LoggerV2 или None.

        Выход:
            (intra_file, inter_file):
                intra_file — dict[Path, dict[str, int]]:
                    только файлы, где хотя бы один КИЗ встречается
                    ≥ 2 раз. Значение — {kiz: count}, count > 1.
                inter_file — dict[str, list[Path]]:
                    только КИЗы, встречающиеся в ≥ 2 файлах.
                    Порядок ключей — по первому обнаружению.
                    Порядок путей внутри значения — по обходу файлов.

        Роль:
            Обходит sales_dir.glob("*.xlsx") в отсортированном
            порядке (детерминизм), читает КИЗы каждого файла через
            SalesFileKizReader.read_with_counts. Lazy import —
            разрывает цикл sales_file_generator ↔ kiz_utils.
            Пустая или несуществующая папка — ({}, {}).
        """
        sales_dir = Path(sales_dir)
        if not sales_dir.exists() or not sales_dir.is_dir():
            return {}, {}

        # Lazy import — см. докстринг.
        from utils.sales_file_generator import SalesFileKizReader

        files = sorted(sales_dir.glob("*.xlsx"))
        if not files:
            return {}, {}

        intra_file: dict = {}
        kiz_to_files: dict = {}

        for file_path in files:
            counts = SalesFileKizReader.read_with_counts(file_path)
            if not counts:
                continue

            # Внутрифайловые дубли.
            duplicates = {k: c for k, c in counts.items() if c > 1}
            if duplicates:
                intra_file[file_path] = duplicates
                if logger is not None:
                    logger.debug(
                        f"KizDuplicatesFinder: {file_path.name} — "
                        f"внутрифайловых дублей: "
                        f"{len(duplicates)} КИЗов"
                    )

            # Заполняем межфайловую карту.
            for kiz in counts.keys():
                bucket = kiz_to_files.setdefault(kiz, [])
                bucket.append(file_path)

        # Межфайловые дубли — только где КИЗ в ≥ 2 файлах.
        inter_file: dict = {}
        for kiz, paths in kiz_to_files.items():
            if len(paths) >= 2:
                inter_file[kiz] = paths

        if inter_file and logger is not None:
            for kiz, paths in inter_file.items():
                names = [p.name for p in paths]
                logger.debug(
                    f"KizDuplicatesFinder: {kiz} встречается "
                    f"в {len(paths)} файлах: {names}"
                )

        return intra_file, inter_file