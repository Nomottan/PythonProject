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
    _ORG_TYPE_TOKENS = {
        "ООО": {
            "ооо", "общество", "с", "ограниченной",
            "ответственностью", "ответственности",
        },
        "ИП": {
            "ип", "индивидуальный", "предприниматель",
            "индивидуальное", "предпринимательство",
        },
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

    @staticmethod
    def tokenize_legal_name(text: str) -> list[str]:
        """Разбивает юридическое наименование на токены.

        Вход:
            text — строка вида 'ООО "Интернет-решения"'.

        Выход:
            list[str] — токены в исходном регистре, без пустых.
            Кавычки, точки, запятые и прочая пунктуация (кроме
            дефиса и апострофа) заменяются пробелами; дефисы и
            апострофы сохраняются. Латиница не переводится —
            это делает вызывающий код до валидации.

        Роль:
            Единая точка токенизации для определения типа
            организации, разбора наименования ООО и ФИО ИП.
        """
        if not text:
            return []
        cleaned = re.sub(r"[^\w\s\-']", " ", str(text), flags=re.UNICODE)
        cleaned = cleaned.replace("_", " ")
        return [part for part in cleaned.split() if part]

    @staticmethod
    def strip_org_type_tokens(tokens: list[str],
                              org_type: str) -> list[str]:
        """Убирает из токенов слова, относящиеся к типу организации.

        Вход:
            tokens — токены в исходном регистре.
            org_type — "ООО", "ИП" или "".

        Выход:
            list[str] — токены без слов типа организации, порядок
            сохраняется. Для ООО предлог "с" удаляется только
            внутри фразы типа, чтобы не потерять название "С".

        Роль:
            После определения типа организации из наименования
            нужно оставить только смысловую часть: название ООО
            или ФИО ИП.
        """
        if not tokens:
            return []
        remove = TextUtils._ORG_TYPE_TOKENS.get(org_type, set())
        if not remove:
            return list(tokens)
        result = []
        for index, token in enumerate(tokens):
            lowered = token.lower()
            if lowered not in remove:
                result.append(token)
                continue
            if lowered == "с":
                prev_lower = tokens[index - 1].lower() if index > 0 else ""
                next_lower = (
                    tokens[index + 1].lower()
                    if index + 1 < len(tokens) else ""
                )
                if prev_lower != "общество" and next_lower != "ограниченной":
                    result.append(token)
        return result

    @staticmethod
    def compose_legal_name(org_type: str, parts: dict) -> str:
        """Собирает каноническое наименование юрлица.

        Вход:
            org_type — "ООО", "ИП" или "".
            parts — для ООО: {"name": "..."};
                    для ИП: {"surname": "...", "given_name": "...",
                             "patronymic": "..."}.

        Выход:
            "ООО «...»" или "ИП Фамилия Имя Отчество".
            Пустая строка, если нет обязательных частей.

        Роль:
            Единая точка сборки name для модели и для обратной
            связи в диалоге. Для ООО кавычки всегда «ёлочки»,
            внешние кавычки снимаются. Регистр наименования ООО
            сохраняется, ФИО капитализируется.
        """
        if org_type == "ООО":
            name = (parts or {}).get("name", "")
            name = TextUtils.strip_quotes(str(name)).strip()
            name = " ".join(name.split())
            if not name:
                return ""
            return f"ООО «{name}»"
        if org_type == "ИП":
            surname = TextUtils.sanitize_fio_part(
                (parts or {}).get("surname", "")
            )
            given_name = TextUtils.sanitize_fio_part(
                (parts or {}).get("given_name", "")
            )
            patronymic = TextUtils.sanitize_fio_part(
                (parts or {}).get("patronymic", "")
            )
            fio = " ".join(
                part for part in (surname, given_name, patronymic)
                if part
            )
            if not fio:
                return ""
            return f"ИП {fio}"
        return ""

    @staticmethod
    def format_short_legal_name(name: str, org_type: str) -> str:
        """Возвращает сокращённое отображение юрлица для списка.

        Вход:
            name — полное наименование из модели.
            org_type — "ООО", "ИП" или "".

        Выход:
            Для ООО — name как есть.
            Для ИП — "ИП Фамилия И.О." (отчество при наличии).
            Иначе — name.

        Роль:
            Кликабельный лейбл в списке контрагентов показывает
            ИП с инициалами, а в модели хранится полное ФИО.
        """
        if org_type != "ИП" or not name:
            return name
        text = name.strip()
        if text.startswith("ИП "):
            text = text[3:].strip()
        words = TextUtils.split_fio(text)
        if not words:
            return name
        surname = TextUtils.sanitize_fio_part(words[0])
        initials = []
        for word in words[1:3]:
            part = TextUtils.sanitize_fio_part(word)
            if part:
                initials.append(part[0].upper() + ".")
        if not initials:
            return f"ИП {surname}"
        return f"ИП {surname} {' '.join(initials)}"

