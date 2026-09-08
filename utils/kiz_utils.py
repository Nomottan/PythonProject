import re
from typing import List
from utils.text_utils import TextUtils


class KizUtils:
    """Утилиты для работы с КИЗами."""

    @staticmethod
    def clean_kiz(raw: str) -> List[str]:
        """
        Очищает КИЗ от управляющих символов, разделяет слипшиеся строки,
        транслитерирует кириллицу.
        Возвращает список очищенных КИЗов (может быть несколько из-за слипания).
        """
        if not raw:
            return []
        raw = str(raw).strip()
        if len(raw) <= 31:
            return []

        # 1. Базовая очистка от управляющих символов (через существующий метод)
        cleaned = TextUtils.clean_invalid_excel_chars(raw)

        # 2. Разделение слипшихся строк (если длина > 100)
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

        # 3. Обработка каждого фрагмента: проверка на "01", транслитерация
        result = []
        for frag in fragments:
            if not frag.startswith("01"):
                pos_01 = frag.find("01")
                if pos_01 != -1 and len(frag) - pos_01 >= 31:
                    frag = frag[pos_01:]
                else:
                    continue
            if len(frag) <= 31:
                continue
            if TextUtils.is_cyrillic(frag):
                frag = TextUtils.keyboard_translit(frag)
            result.append(frag)
        return result