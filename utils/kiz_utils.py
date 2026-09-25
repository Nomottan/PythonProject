import re
from typing import List, Optional
from utils.text_utils import TextUtils
from dataclasses import dataclass
from datetime import datetime
from services.subservices.logging import LoggerV2


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

@dataclass
class ChosenKiz:
    """Выбранное вхождение КИЗа из группы дубликатов.

    Роль:
        Результат выбора «самого позднего» вхождения одного и того
        же storage_kiz из листа «КИЗ» отчёта МП. Возвращается
        методом KizOccurrences.pick_latest и используется
        MpReportReader для валидации и записи в буфер цен.

    Поля:
        full_kiz — полный КИЗ выбранного вхождения.
        task_num — номер сборочного задания выбранного вхождения.
        price — цена из отчёта, если она числовая и положительная;
                иначе None.
        sale_date_str — дата продажи из листа «Сборочные задания»
                        для выбранного task_num; None, если задания
                        в словаре нет.
        skipped_dup_count — сколько вхождений той же группы были
                            отброшены как дубликаты (len(group) - 1).
    """
    full_kiz: str
    task_num: str
    price: Optional[float]
    sale_date_str: Optional[str]
    skipped_dup_count: int


class KizOccurrences:
    """Группировка вхождений КИЗов из отчёта МП.

    Роль:
        Собирает все вхождения одного storage_kiz из листа «КИЗ».
        Из группы выбирается одно — с самой поздней датой
        сборочного задания. Остальные считаются дубликатами.
        Заменяет ручной словарь occurrences из ExportKizService.

    Поля:
        _entries — dict[storage_kiz, list[tuple[full_kiz, task_num, price]]].
                   Каждое значение — список вхождений одного КИЗа
                   в том порядке, в котором они встречались в отчёте.
    """

    def __init__(self) -> None:
        """Конструктор.

        Вход: нет.
        Роль: создаёт пустую структуру — словарь групп.
        """
        self._entries: dict[str, List[tuple[str, str, Optional[float]]]] = {}

    def add(self, storage_kiz: str, full_kiz: str, task_num: str,
            price_value: Optional[float]) -> None:
        """Добавляет одно вхождение КИЗа.

        Вход:
            storage_kiz — 31-символьный КИЗ, используется как ключ группы.
            full_kiz — полный КИЗ этого вхождения.
            task_num — номер сборочного задания.
            price_value — цена из отчёта или None.

        Выход: нет.
        Роль: накапливает вхождения. Группа создаётся лениво
              через setdefault.
        """
        self._entries.setdefault(storage_kiz, []).append(
            (full_kiz, task_num, price_value)
        )

    def pick_latest(self, storage_kiz: str,
                    task_to_date: dict) -> Optional[ChosenKiz]:
        """Выбирает самое позднее вхождение из группы.

        Вход:
            storage_kiz — ключ группы.
            task_to_date — dict {task_num: sale_date_str}. Значения —
                           строки дат в одном из форматов KizValidator.

        Выход:
            ChosenKiz выбранного вхождения либо None, если группы нет.

        Роль:
            Сортирует вхождения группы по дате из task_to_date в
            порядке убывания и берёт первое. Если дата вхождения
            не парсится или задания нет в словаре — считается
            datetime.min (самое раннее), чтобы такое вхождение
            ушло в конец. skipped_dup_count = len(group) - 1.
        """
        entries = self._entries.get(storage_kiz)
        if not entries:
            return None

        # Локальный импорт: KizValidator тянет KizStorage; чтобы
        # не создавать циклический импорт на уровне модуля,
        # импортируем внутри метода.
        from services.kiz_validator import KizValidator

        def _sort_key(entry) -> datetime:
            """Ключ сортировки: дата вхождения; datetime.min при ошибке."""
            task_num = entry[1]
            date_str = task_to_date.get(task_num)
            dt = KizValidator._parse_date(date_str)
            return dt or datetime.min

        entries_sorted = sorted(entries, key=_sort_key, reverse=True)
        chosen = entries_sorted[0]
        full_kiz, task_num, price_value = chosen

        return ChosenKiz(
            full_kiz=full_kiz,
            task_num=task_num,
            price=price_value,
            sale_date_str=task_to_date.get(task_num),
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