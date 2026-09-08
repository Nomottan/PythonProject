import re

class TextUtils:
    _KEYBOARD_MAP = {
        'а': 'f', 'б': ',', 'в': 'd', 'г': 'u', 'д': 'l', 'е': 't', 'ё': '`',
        'ж': ';', 'з': 'p', 'и': 'b', 'й': 'q', 'к': 'r', 'л': 'k', 'м': 'v',
        'н': 'y', 'о': 'j', 'п': 'g', 'р': 'h', 'с': 'c', 'т': 'n', 'у': 'e',
        'ф': 'a', 'х': '[', 'ц': 'w', 'ч': 'x', 'ш': 'i', 'щ': 'o', 'ъ': ']',
        'ы': 's', 'ь': 'm', 'э': "'", 'ю': '.', 'я': 'z',
        'А': 'F', 'Б': '<', 'В': 'D', 'Г': 'U', 'Д': 'L', 'Е': 'T', 'Ё': '~',
        'Ж': ':', 'З': 'P', 'И': 'B', 'Й': 'Q', 'К': 'R', 'Л': 'K', 'М': 'V',
        'Н': 'Y', 'О': 'J', 'П': 'G', 'Р': 'H', 'С': 'C', 'Т': 'N', 'У': 'E',
        'Ф': 'A', 'Х': '{', 'Ц': 'W', 'Ч': 'X', 'Ш': 'I', 'Щ': 'O', 'Ъ': '}',
        'Ы': 'S', 'Ь': 'M', 'Э': '"', 'Ю': '>', 'Я': 'Z',
        '.': '/', ',': '?', '/': '|',
        '"': '@', '№': '#', ';': '$', '?': '&', ':': '^'
    }

    @staticmethod
    def is_cyrillic(text: str) -> bool:
        if not isinstance(text, str):
            return False
        cyrillic_chars = set('абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
        return any(char.lower() in cyrillic_chars for char in text)

    @staticmethod
    def keyboard_translit(text: str) -> str:
        result = []
        for ch in text:
            result.append(TextUtils._KEYBOARD_MAP.get(ch, ch))
        return ''.join(result)

    @staticmethod
    def trim_to_31(value) -> str:
        if value is None:
            return ""
        return str(value)[:31]

    @staticmethod
    def normalize(s: str) -> str:
        return (s or "").strip().lower()

    @staticmethod
    def sanitize_filename(name: str) -> str:
        if not name:
            return "неизвестная_компания"
        safe = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in name)
        return safe.strip() or "неизвестная_компания"

    @staticmethod
    def build_key_mapping(items, key_extractor, log_func=None):
        mapping = {}
        for item in items:
            keys = key_extractor(item)
            if isinstance(keys, str):
                keys = [keys]
            for key in keys:
                if key is None:
                    continue
                normalized = TextUtils.normalize(key)
                if not normalized:
                    continue
                if normalized not in mapping:
                    mapping[normalized] = item
                else:
                    if log_func:
                        log_func(
                            f"⚠️ Ключ '{key}' уже привязан к объекту '{mapping[normalized]}'. "
                            f"Игнорируем дубликат у '{item}'."
                        )
        return mapping

    @staticmethod
    def get_allowed_companies(sellers):
        allowed = set()
        if sellers:
            for s in sellers:
                comp = TextUtils.normalize(s.company)
                if comp:
                    allowed.add(comp)
        return allowed

    @staticmethod
    def find_seller_by_company(company, sellers):
        norm_company = TextUtils.normalize(company)
        if not norm_company:
            return None
        for seller in sellers:
            if TextUtils.normalize(seller.company) == norm_company:
                return seller
        return None

    @staticmethod
    def log_unknown_entities(unknown_dict, log_path, title, ctx):
        if not unknown_dict:
            return
        sorted_unknown = sorted(unknown_dict.keys(), key=str.lower)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(title + "\n")
            f.write("=" * 50 + "\n")
            for entity in sorted_unknown:
                f.write(f"{entity}: {unknown_dict[entity]}\n")
        ctx.log(f"Список неизвестных сущностей сохранён в {log_path.name}")

    @staticmethod
    def clean_invalid_excel_chars(text: str) -> str:
        """
        Удаляет из строки символы, которые openpyxl не может записать в Excel.
        В основном это управляющие символы (ASCII 0-31), кроме табуляции, перевода строки и возврата каретки.
        """
        if not text:
            return text
        # Оставляем только печатаемые символы: табуляция (9), перевод строки (10), возврат каретки (13),
        # и все символы от 32 до 126 (печатаемые ASCII) и выше (Unicode)
        # Удаляем все управляющие символы, кроме \t, \n, \r
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    def clean_kiz(raw: str) -> list[str]:
        """Очищает КИЗ: удаляет управляющие символы, разделяет слипшиеся, транслитерирует."""
        if not raw:
            return []
        raw = str(raw).strip()
        if len(raw) <= 31:
            return []

        # 1. Базовая очистка от управляющих символов (используем существующий метод)
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