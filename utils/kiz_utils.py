import re
from typing import List
from utils.text_utils import TextUtils


class KizUtils:
    """Утилиты для работы с КИЗами."""

    @staticmethod
    def clean_kiz_full(raw: str) -> List[str]:
        """
        Полная очистка КИЗа: удаляет управляющие символы, транслитерирует,
        разделяет слипшиеся строки.
        Возвращает список полных очищенных строк (без обрезания).
        Если КИЗ некорректен (пустой или короче 31), возвращает пустой список.
        """
        if not raw:
            return []
        raw = str(raw).strip()
        if len(raw) < 31:
            return []

        # 1. Удаляем XML-представления управляющих символов
        cleaned = re.sub(r'_x001[dD]_', '', raw)
        # 2. Удаляем настоящие управляющие символы (код ASCII < 32)
        cleaned = ''.join(ch for ch in cleaned if ord(ch) >= 32)

        # 3. Разделение слипшихся строк (если длина > 100)
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
            if not frag.startswith("01"):
                pos_01 = frag.find("01")
                if pos_01 != -1 and len(frag) - pos_01 >= 31:
                    frag = frag[pos_01:]
                else:
                    continue
            if len(frag) < 31:
                continue
            if TextUtils.is_cyrillic(frag):
                frag = TextUtils.keyboard_translit(frag)
            result.append(frag)
        return result

    @staticmethod
    def clean_kiz_for_storage(raw: str) -> List[str]:
        """
        Очищает КИЗ и обрезает до 31 символа.
        Возвращает список с обрезанными КИЗами (каждый из фрагментов обрезается до 31 символа).
        """
        full_list = KizUtils.clean_kiz_full(raw)
        if not full_list:
            return []
        result = []
        for full_kiz in full_list:
            if len(full_kiz) >= 31:
                result.append(full_kiz[:31])
        return result