""" Утилиты для валидации ввода данных"""


class CPValid:
    """валидации для ввода данных юр лиц"""

    @staticmethod
    def detect_type(text: str) -> tuple[str, str]:
        """Определяет тип контрагента и префикс полной формы."""
        if not text:
            return "", ""
        tokens = text.strip().split()
        if not tokens:
            return "", ""

        first_token = tokens[0]
        if len(first_token) > 4:
            if len(tokens) >= 3:
                t1, t2, t3 = tokens[0].lower(), tokens[1].lower(), tokens[2].lower()
                if t1.startswith("индивидуальный") and t2.startswith("предприниматель"):
                    return "ИП", "Индивидуальный предприниматель"
                if t1.startswith("общество") and t2.startswith("с") and t3.startswith("ограниченной"):
                    return "ООО", "Общество с ограниченной ответственностью"
        else:
            if first_token.upper() == "ИП":
                return "ИП", "ИП"
            if first_token.upper() == "ООО":
                return "ООО", "ООО"

        return "", ""

    @staticmethod
    def parse_full_name(text: str) -> tuple[str, str, str]:
        """Разбирает ФИО на фамилию, имя и отчество."""
        if not text:
            return "", "", ""
        tokens = text.strip().split()
        last = tokens[0] if len(tokens) > 0 else ""
        first = tokens[1] if len(tokens) > 1 else ""
        middle = tokens[2] if len(tokens) > 2 else ""
        return last, first, middle

    @staticmethod
    def format_address(address) -> str:
        """Форматирует адрес в строку.

        Вход: address — объект с атрибутами index, region_name, city,
              settlement, street, house, building.
        Выход: строка адреса или "Не заполнен".
        """
        parts = []

        index = getattr(address, "index", "").strip()
        if index:
            parts.append(index)

        region = getattr(address, "region_name", "").strip()
        if region:
            parts.append(region)

        city = getattr(address, "city", "").strip()
        if city:
            parts.append(city)

        settlement = getattr(address, "settlement", "").strip()
        if settlement:
            parts.append(settlement)

        street = getattr(address, "street", "").strip()
        if street:
            parts.append(street)

        house = getattr(address, "house", "").strip()
        if house:
            parts.append(f"д. {house}")

        building = getattr(address, "building", "").strip()
        if building:
            parts.append(f"корп. {building}")

        if not parts:
            return "Не заполнен"

        return ", ".join(parts)

    @staticmethod
    def validate_address(address) -> dict[str, str]:
        """Валидирует адрес.

        Вход: address — объект с атрибутами index, region_code, region_name.
        Выход: dict с ошибками (пустой, если ошибок нет).
        """
        errors = {}

        index = getattr(address, "index", "").strip()
        if not index.isdigit() or len(index) != 6:
            errors["index"] = "Индекс — 6 цифр"

        code = getattr(address, "region_code", "").strip()
        if not code.isdigit() or len(code) != 2:
            errors["region_code"] = "Код региона — 2 цифры"

        name = getattr(address, "region_name", "").strip()
        if not name:
            errors["region_name"] = "Укажите регион"

        return errors

    @staticmethod
    def validate_kpp(kpp: str) -> str | None:
        """Валидирует КПП."""
        kpp = (kpp or "").strip()
        if len(kpp) != 9 or not kpp.isdigit():
            return "КПП должен быть 9 цифр"
        return None
