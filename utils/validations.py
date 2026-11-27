"""
Утилиты валидации пользовательского ввода.

Содержит Validations — единую точку проверок полей перед
сохранением. Валидация вынесена из UI и из моделей: диалог
только спрашивает «валидно / нет» и показывает состояние,
а сами правила живут здесь.
"""

import re

from utils.text_utils import TextUtils

class Validations:
    """Правила валидации пользовательского ввода.

    Назначение:
        Единая точка проверок полей, которые заполняет
        пользователь: ФИО подписанта, юридическое наименование,
        части ФИО контрагента.

    Роль в программе:
        Вызывается из StaffAddDialog на editingFinished и перед
        accept(). Возвращает bool + текст причины: UI показывает
        красную рамку и блокирует кнопку «Готово», а причина
        уходит в лог/подсказку.

    Правила для ФИО:
        - не пусто;
        - от 2 до 4 слов (фамилия + имя, опционально отчество);
        - каждое слово — только кириллица; допускаются дефис
          и апостроф внутри слова (Иванова-Петрова, О'Брайен);
        - цифры, латиница, прочая пунктуация — запрещены.
        Латинский ввод здесь не «исправляется» — его переводит
        TextUtils.to_cyrillic в диалоге до вызова валидации.

    Публичный API:
        is_valid_fio — bool-проверка ФИО.
        fio_error — текст причины ("" если всё ок).
        detect_org_type — "ООО" / "ИП" / "".
        legal_name_error — проверка поля «Компания».
        fio_parts_error — проверка Фамилия/Имя/Отчество.
        phone_error — проверка телефона по маскам.
    """

    _FIO_WORD_RE = re.compile(r"^[А-Яа-яЁё]+(?:[-'][А-Яа-яЁё]+)*$")
    _LEGAL_NAME_WORD_RE = re.compile(
        r"^[А-Яа-яЁё0-9]+(?:[-'][А-Яа-яЁё0-9]+)*$"
    )
    _FIO_MIN_WORDS = 2
    _FIO_MAX_WORDS = 4
    _FIO_PART_MIN_LENGTH = 2
    _PHONE_PATTERNS = (
        re.compile(r"^8\d{10}$"),
        re.compile(r"^\+7\d{10}$"),
        re.compile(r"^8\(\d{3}\)\d{3}-\d{2}-\d{2}$"),
        re.compile(r"^\+7\(\d{3}\)\d{3}-\d{2}-\d{2}$"),
    )
    _PHONE_ERROR = (
        "Телефон в формате 8**********, +7**********, "
        "8(***)***-**-** или +7(***)***-**-**"
    )
    _ORG_TYPE_TRIGGERS = {
        "ООО": (
            {"ооо"},
            {"ограниченной", "ответственностью"},
            {"ограниченной", "ответственности"},
        ),
        "ИП": (
            {"ип"},
            {"индивидуальный", "предприниматель"},
            {"индивидуальное", "предпринимательство"},
            {"индивидуальный"},
            {"предприниматель"},
            {"индивидуальное"},
            {"предпринимательство"},
        ),
    }
    @staticmethod
    def fio_error(text: str) -> str:
        """Возвращает причину невалидности ФИО.

        Вход: text — ФИО одной строкой.
        Выход: "" если валидно; иначе текст причины.

        Роль: единственная точка правил. is_valid_fio —
              обёртка над этим методом, чтобы не дублировать
              проверки.
        """
        if not isinstance(text, str) or not text.strip():
            return "Введите ФИО"

        words = TextUtils.split_fio(text)

        if len(words) < Validations._FIO_MIN_WORDS:
            return "ФИО — от 2 до 4 слов"
        if len(words) > Validations._FIO_MAX_WORDS:
            return "ФИО — от 2 до 4 слов"

        for word in words:
            if not Validations._FIO_WORD_RE.match(word):
                return "Только кириллица, без цифр и латиницы"

        return ""

    @staticmethod
    def is_valid_fio(text: str) -> bool:
        """..."""
        return Validations.fio_error(text) == ""

    @staticmethod
    def detect_org_type(tokens: list[str]) -> str:
        """Определяет тип организации по токенам наименования.

        Вход:
            tokens — токены в исходном регистре.

        Выход:
            "ООО", "ИП" или "" (не опознан / неоднозначно).

        Роль:
            Единая точка определения типа. Если сработали и ООО,
            и ИП — возвращает "", чтобы диалог заблокировал
            «Готово»: неоднозначный ввод не сохраняем.
        """
        if not tokens:
            return ""
        lowered = {token.lower() for token in tokens}
        is_ooo = any(
            trigger <= lowered
            for trigger in Validations._ORG_TYPE_TRIGGERS["ООО"]
        )
        is_ip = any(
            trigger <= lowered
            for trigger in Validations._ORG_TYPE_TRIGGERS["ИП"]
        )
        if is_ooo and is_ip:
            return ""
        if is_ooo:
            return "ООО"
        if is_ip:
            return "ИП"
        return ""

    @staticmethod
    def legal_name_error(text: str) -> str:
        """Проверяет поле «Компания» целиком.

        Вход:
            text — строка, введённая в «Компания».

        Выход:
            "" если валидно; иначе текст первой причины.

        Роль:
            Токенизирует, определяет тип, убирает тип-токены и
            проверяет остаток: для ООО — наименование, для ИП —
            фамилию, имя и отчество. Латиница перед проверкой
            переводится в кириллицу.
        """
        if not isinstance(text, str) or not text.strip():
            return "Введите компанию"
        if TextUtils.is_latinic(text):
            text = TextUtils.to_cyrillic(text)
        tokens = TextUtils.tokenize_legal_name(text)
        if not tokens:
            return "Введите компанию"

        org_type = Validations.detect_org_type(tokens)
        if not org_type:
            return "Не удалось определить тип организации"

        name_tokens = TextUtils.strip_org_type_tokens(tokens, org_type)
        if org_type == "ООО":
            if not name_tokens:
                return "Введите наименование"
            for token in name_tokens:
                if not Validations._LEGAL_NAME_WORD_RE.match(token):
                    return "Наименование содержит недопустимые символы"
            return ""

        if not name_tokens:
            return "Введите фамилию"
        surname = name_tokens[0]
        given_name = name_tokens[1] if len(name_tokens) > 1 else ""
        patronymic_words = name_tokens[2:] if len(name_tokens) > 2 else []
        if not surname:
            return "Введите фамилию"
        if not given_name:
            return "Введите имя"
        if (len(surname) < Validations._FIO_PART_MIN_LENGTH
                or len(given_name) < Validations._FIO_PART_MIN_LENGTH):
            return "Фамилия и имя должны быть длиннее одного символа"
        for part in [surname, given_name] + patronymic_words:
            if not Validations._FIO_WORD_RE.match(part):
                return "Только буквы, без цифр"
        for word in patronymic_words:
            if len(word) < Validations._FIO_PART_MIN_LENGTH:
                return "Отчество должно быть длиннее одного символа"
        return ""

    @staticmethod
    def fio_part_error(value: str, part: str) -> str:
        """Проверяет одну часть ФИО.

        Вход:
            value — значение поля.
            part — "surname", "given_name" или "patronymic".

        Выход:
            "" если валидно; иначе текст причины.

        Роль:
            Единая проверка одной части ФИО для подсветки
            конкретного поля в диалоге контрагента. Латиница
            переводится в кириллицу до проверки.
        """
        if TextUtils.is_latinic(value or ""):
            value = TextUtils.to_cyrillic(value)
        value = (value or "").strip()

        if part == "surname":
            if not value:
                return "Введите фамилию"
            if len(value) < Validations._FIO_PART_MIN_LENGTH:
                return "Фамилия и имя должны быть длиннее одного символа"
        elif part == "given_name":
            if not value:
                return "Введите имя"
            if len(value) < Validations._FIO_PART_MIN_LENGTH:
                return "Фамилия и имя должны быть длиннее одного символа"
        elif part == "patronymic":
            if not value:
                return ""
            if len(value) < Validations._FIO_PART_MIN_LENGTH:
                return "Отчество должно быть длиннее одного символа"
        else:
            return ""

        if not Validations._FIO_WORD_RE.match(value):
            return "Только буквы, без цифр"
        return ""

    @staticmethod
    def fio_parts_error(surname: str, given_name: str,
                        patronymic: str = "") -> str:
        """Проверяет части ФИО контрагента по отдельности.

        Вход:
            surname — фамилия.
            given_name — имя.
            patronymic — отчество (может быть пустым).

        Выход:
            "" если валидно; иначе текст первой причины.

        Роль:
            Используется в динамических полях ИП, где фамилия,
            имя и отчество редактируются отдельно. Латиница
            переводится в кириллицу до проверки.
        """
        if TextUtils.is_latinic(surname or ""):
            surname = TextUtils.to_cyrillic(surname)
        if TextUtils.is_latinic(given_name or ""):
            given_name = TextUtils.to_cyrillic(given_name)
        if TextUtils.is_latinic(patronymic or ""):
            patronymic = TextUtils.to_cyrillic(patronymic)

        surname = (surname or "").strip()
        given_name = (given_name or "").strip()
        patronymic = (patronymic or "").strip()

        if not surname:
            return "Введите фамилию"
        if not given_name:
            return "Введите имя"
        if (len(surname) < Validations._FIO_PART_MIN_LENGTH
                or len(given_name) < Validations._FIO_PART_MIN_LENGTH):
            return "Фамилия и имя должны быть длиннее одного символа"

        patronymic_words = (
            TextUtils.split_fio(patronymic) if patronymic else []
        )
        parts = [surname, given_name] + patronymic_words
        for part in parts:
            if not Validations._FIO_WORD_RE.match(part):
                return "Только буквы, без цифр"
        for word in patronymic_words:
            if len(word) < Validations._FIO_PART_MIN_LENGTH:
                return "Отчество должно быть длиннее одного символа"
        return ""

    @staticmethod
    def phone_error(value: str) -> str:
        """Проверяет телефон по маскам.

        Вход:
            value — телефон.

        Выход:
            "" если пусто или соответствует одной из масок;
            иначе текст причины.

        Роль:
            Единая точка проверки телефона для окна реквизитов.
            Допустимые маски:
                8**********;
                +7**********;
                8(***)***-**-**;
                +7(***)***-**-**.
            Пустое значение допустимо: телефон не обязателен.
        """
        text = (value or "").strip()
        if not text:
            return ""
        for pattern in Validations._PHONE_PATTERNS:
            if pattern.match(text):
                return ""
        return Validations._PHONE_ERROR