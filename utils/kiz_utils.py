import re
from typing import List, Optional
from utils.text_utils import TextUtils
from utils.log_system.logger import Logger


class KizUtils:
    """Утилиты для работы с КИЗами.

    Класс ведёт опциональную статистику обработки. Сервис перед началом
    вызывает start_stats(), после — pop_stats() и логирует итог через
    ctx.info(). Это позволяет собрать агрегат без прокидывания счётчиков
    через параметры каждого вызова.

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
    def clean_kiz_full(raw: str, logger: Optional[Logger] = None) -> List[str]:
        """Полная очистка КИЗа.

        Вход:
            raw — исходная строка КИЗа.
            logger — опциональный Logger. Если передан, детальные события
                     (отбрасывание, транслитерация) уходят на уровне DEBUG.

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
            result.append(frag)

        # Успешно обработанные в этой порции.
        if KizUtils._stats_enabled:
            KizUtils._stats["processed"] += len(result)

        return result

    @staticmethod
    def clean_kiz_for_storage(raw: str, logger: Optional[Logger] = None) -> List[str]:
        """Очищает КИЗ и обрезает до 31 символа.

        Вход:
            raw — исходная строка КИЗа.
            logger — опциональный Logger (прокидывается в clean_kiz_full).

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