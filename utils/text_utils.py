import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2

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
    def normalize_for_brand_matching(s: str) -> str:
        """Агрессивная нормализация строки для нечеткого поиска брендов.

        Приводит к нижнему регистру, удаляет ВСЕ знаки пунктуации,
        пробелы и подчеркивания. Оставляет только буквы и цифры.
        """
        if not s:
            return ""
        res = re.sub(r'[^\w]|_', '', s.lower())
        return res

    @staticmethod
    def sanitize_filename(name: str) -> str:
        if not name:
            return "неизвестная_компания"
        safe = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in name)
        return safe.strip() or "неизвестная_компания"

    @staticmethod
    def build_key_mapping(items, key_extractor, log_func=None,
                          logger: "LoggerV2 | None" = None):
        """Строит словарь {нормализованный ключ: объект}.

        Вход:
            items — список объектов (Seller, Brand и т.п.).
            key_extractor — callable(item) -> str | list[str].
                            Возвращает ключ или список ключей.

        Выход:
            dict {нормализованный ключ: первый объект, у которого
            этот ключ встретился}.

        Роль:
            Единая точка построения маппингов «ключ → сущность»
            для продавцов и брендов. Дубликаты не перезаписывают
            первое значение — приоритет у того объекта, который
            раньше в items.
        """
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
                    msg = (
                        f"Ключ '{key}' уже привязан к объекту "
                        f"'{mapping[normalized]}'. Игнорируем "
                        f"дубликат у '{item}'."
                    )
                    # Приоритет: новый логгер, затем legacy-колбэк.
                    if logger is not None:
                        logger.warning(msg)
                    elif log_func is not None:
                        log_func(msg)
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
    def find_seller_by_file_name(file_name_lower: str, sellers) -> list:
        """Находит продавцов по имени файла с двухуровневой проверкой.

        Вход:
            file_name_lower — имя файла в нижнем регистре (без пути,
                              без расширения — вызывающий код приводит сам).
            sellers — список Seller.

        Выход:
            list[Seller].
            Если пусто — никого не нашли.
            Если 1 — однозначное совпадение.
            Если > 1 — конфликт (пользователь должен выбрать).

        Роль:
            Сначала ищет полное совпадение (имя файла == ключ продавца).
            Если таких нет — ищет по вхождению ключа (ключ в имени файла).
            Приоритет по порядку в списке sellers убран.
        """
        # 1. Поиск точного совпадения (имя файла полностью равно ключу)
        exact_matches = []
        for seller in sellers:
            if any(key.lower() == file_name_lower for key in seller.keys):
                if seller not in exact_matches:
                    exact_matches.append(seller)

        if exact_matches:
            return exact_matches

        # 2. Поиск по вхождению (ключ является подстрокой имени файла)
        substring_matches = []
        for seller in sellers:
            if any(key.lower() in file_name_lower for key in seller.keys):
                if seller not in substring_matches:
                    substring_matches.append(seller)

        return substring_matches

    @staticmethod
    def parse_sales_filename(filename: str, sellers) -> tuple | None:
        """Разбирает имя файла продаж в пару продавцов.

        Вход:
            filename — полное имя файла в формате
                       "{from} - {to} _ {inn}.xlsx".
            sellers — список Seller.

        Выход:
            (from_seller, to_seller) — кортеж из двух объектов
            Seller, если имя распознано. None — если ни одна
            пара не подошла.

        Роль:
            Обратный разбор к тому, что делает SalesFileGenerator
            при формировании имени. Формат:
                {sanitize(name_a)} - {sanitize(name_b)} _ {inn_b}.xlsx.
            Перебор пар — надёжнее regex: sanitize_filename
            разрешает пробелы, дефисы и подчёркивания, поэтому
            regex-разделители неоднозначны. N ≤ ~20, файлов
            ≤ ~50 — перебор незаметен.
        """
        for a in sellers:
            for b in sellers:
                if a is b:
                    continue
                expected = (
                    f"{TextUtils.sanitize_filename(a.name)} - "
                    f"{TextUtils.sanitize_filename(b.name)} _ "
                    f"{b.inn}.xlsx"
                )
                if filename == expected:
                    return (a, b)
        return None

    @staticmethod
    def clean_invalid_excel_chars(text: str) -> str:
        """
        Удаляет из строки символы, которые openpyxl не может записать в Excel.
        В основном это управляющие символы (ASCII 0-31), кроме табуляции, перевода строки и возврата каретки.
        """
        if not text:
            return text
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)