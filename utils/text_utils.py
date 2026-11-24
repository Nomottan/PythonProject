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
    _KEYBOARD_MAP_REVERSE = dict(
        zip(_KEYBOARD_MAP.values(), _KEYBOARD_MAP.keys())
    )
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
    def is_latinic(text: str) -> bool:
        """Проверяет, есть ли в строке латинские буквы.

        Вход: text — любая строка.
        Выход: True, если найден хотя бы один латинский символ
               (a–z, A–Z); иначе False. Не-строки → False.

        Роль: зеркало is_cyrillic. Нужен, чтобы отличить
              «набрано в английской раскладке» от «набрано
              по-русски» и включить автоперевод раскладки.
        """
        if not isinstance(text, str):
            return False
        latin_chars = set('abcdefghijklmnopqrstuvwxyz')
        return any(char.lower() in latin_chars for char in text)

    @staticmethod
    def to_cyrillic(text: str) -> str:
        """Переводит символы английской раскладки в кириллицу.

        Вход: text — строка, набранная в английской раскладке
              («ghbdtn» вместо «привет»).
        Выход: строка, где символы, совпавшие с обратной картой
               клавиатуры, заменены кириллицей; остальные
               (цифры, пробелы, знаки вне карты) — как есть.

        Роль: обратное к keyboard_translit. Нужен для сценария
              «пользователь забыл переключить раскладку»:
              латиница → кириллица по физическим клавишам.
              Карта _KEYBOARD_MAP_REVERSE собирается в конце
              модуля (в теле класса dict-comprehension не видит
              _KEYBOARD_MAP из-за области видимости).
        """
        if not isinstance(text, str):
            return text
        return ''.join(
            TextUtils._KEYBOARD_MAP_REVERSE.get(ch, ch) for ch in text
        )

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
    def clean_invalid_excel_chars(text: str) -> str:
        """
        Удаляет из строки символы, которые openpyxl не может записать в Excel.
        В основном это управляющие символы (ASCII 0-31), кроме табуляции, перевода строки и возврата каретки.
        """
        if not text:
            return text
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    @staticmethod
    def split_fio(text: str) -> list[str]:
        """Делит ФИО на слова.

        Вход: text — строка вида «  Иванов   Иван  Иванович ».
        Выход: список слов без пустых элементов. Пустая строка
               или None → [].

        Роль: единая точка разбора ФИО для валидации (подсчёт
              слов) и для санитайзинга. Множественные пробелы
              схлопываются.
        """
        if not text:
            return []
        return str(text).split()

    @staticmethod
    def sanitize_fio(text: str) -> str:
        """Приводит ФИО к формату «Первая заглавная, остальные строчные».

        Вход: text — ФИО одной строкой.
        Выход: нормализованная строка: каждое слово обработано
               sanitize_fio_part (капитализация, дефисы,
               апострофы), склейка через один пробел.

        Роль: вызывается перед сохранением Signer, чтобы в
              config.json попадал единый формат независимо от
              того, как пользователь набрал текст.
        """
        parts = TextUtils.split_fio(text)
        return " ".join(TextUtils.sanitize_fio_part(p) for p in parts)

    @staticmethod
    def sanitize_fio_part(text: str) -> str:
        """Приводит часть ФИО к формату с заглавной буквы."""
        if not text:
            return ""
        text = " ".join(text.strip().split())
        words = text.split("-")
        res = []
        for w in words:
            w = w.strip()
            parts = w.split("'")
            parts[0] = parts[0].capitalize()
            res.append("'".join(parts))
        return "-".join(res)

    @staticmethod
    def strip_quotes(text: str) -> str:
        """Снимает обрамляющие парные кавычки."""
        if not text:
            return ""
        t = text.strip()
        if len(t) >= 2:
            if (t.startswith('"') and t.endswith('"')) or \
                    (t.startswith('«') and t.endswith('»')) or \
                    (t.startswith("'") and t.endswith("'")):
                return t[1:-1].strip()
        return t

