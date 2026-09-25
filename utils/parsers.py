"""
Единый слой парсинга для проекта.

Модуль собирает в одном месте все операции преобразования строк
в типизированные значения: даты, числа, имена файлов, КИЗы.

Использование:
    from utils.parsers import DateParser, NumberParser
    d = DateParser.parse_dotted("25.12.2025")   # date(2025, 12, 25)
    n = NumberParser.to_int("1 234")            # 1234
    bad = DateParser.parse_dotted("abc")        # None
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import re


class BaseParser:
    """База для всех парсеров.

    Роль: держит общий контракт — «на ошибке возвращаем None,
          исключений не бросаем». Наследники реализуют конкретные
          методы разбора. Сейчас класс пустой, но он — место для
          общих хелперов, если они появятся.
    """

    pass


class DateParser(BaseParser):
    """Парсер дат и дат-со-временем.

    Роль: единая точка разбора строк в date/datetime. Все методы
          возвращают None при несоответствии формату.
    """

    @staticmethod
    def parse_dotted(text: str) -> Optional[date]:
        """Разбирает строку в формате "ДД.ММ.ГГГГ".

        Вход: text — строка, например "25.12.2025".
        Выход: date(2025, 12, 25) или None.

        Роль: стандартный формат даты во всём проекте (в JSON,
              в UI, в именах файлов отчётов).
        """
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), "%d.%m.%Y").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_dashed(text: str) -> Optional[date]:
        """Разбирает строку в формате "ГГГГ-ММ-ДД".

        Вход: text — строка, например "2025-12-25".
        Выход: date(2025, 12, 25) или None.

        Роль: альтернативный формат — встречается в отчётах
              маркетплейсов и во внутренних API.
        """
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_datetime(text: str) -> Optional[datetime]:
        """Разбирает строку в формате "ДД.ММ.ГГГГ ЧЧ:ММ".

        Вход: text — строка, например "25.12.2025 14:30".
        Выход: datetime(2025, 12, 25, 14, 30) или None.

        Роль: формат дедлайнов и created_datetime в PlannerTask.
        """
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), "%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            return None

    @staticmethod
    def parse_datetime_with_time_first(text: str) -> Optional[datetime]:
        """Разбирает строку в формате "ЧЧ:ММ ДД.ММ.ГГГГ".

        Вход: text — строка, например "14:30 25.12.2025".
        Выход: datetime(2025, 12, 25, 14, 30) или None.

        Роль: редкий, но встречается в отчётах МП, где время
              идёт перед датой.
        """
        if not text:
            return None
        try:
            return datetime.strptime(text.strip(), "%H:%M %d.%m.%Y")
        except (ValueError, TypeError):
            return None


class NumberParser(BaseParser):
    """Парсер чисел из строк с разделителями.

    Роль: числа из Excel/CSV часто приходят как "1 234,56" или
          "1,234.56" — здесь единая логика их разбора.
    """

    @staticmethod
    def to_int(text) -> Optional[int]:
        """Преобразует строку или число в int.

        Вход: text — строка "1 234" или число.
        Выход: int или None при ошибке.

        Роль: убираем пробелы (включая неразрывные), запятые
              (как разделитель тысяч), пытаемся привести к int.
              Если получается float-строка ("1.5") — округляем
              до int через float, чтобы не терять данные.
        """
        if text is None:
            return None
        if isinstance(text, int):
            return text
        if isinstance(text, float):
            return int(text)
        cleaned = str(text).strip().replace(" ", "").replace("\xa0", "")
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            # Пробуем как float — например, "1234.0" или "1234,5".
            try:
                return int(float(cleaned.replace(",", ".")))
            except (ValueError, TypeError):
                return None

    @staticmethod
    def to_float(text) -> Optional[float]:
        """Преобразует строку или число в float.

        Вход: text — строка "1 234,56" или число.
        Выход: float или None при ошибке.

        Роль: обрабатываем оба вида разделителей (точка и запятая).
              Если в строке есть и точка, и запятая — считаем, что
              запятая — разделитель тысяч, а точка — десятичный.
        """
        if text is None:
            return None
        if isinstance(text, (int, float)):
            return float(text)
        cleaned = str(text).strip().replace(" ", "").replace("\xa0", "")
        if not cleaned:
            return None
        # Случай "1,234.56" — запятая как разделитель тысяч.
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(",", "")
        else:
            # Иначе — запятая как десятичный разделитель.
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def is_numeric(value) -> bool:
        """Проверяет, что значение — число (int, float, Decimal), но не bool.

        Вход:
            value — значение любого типа (обычно — содержимое ячейки Excel).

        Выход:
            True — если value является int, float или Decimal.
            False — для bool, None, str и всего остального.

        Роль:
            Отличает «уже число» от «строки, которую ещё нужно
            распарсить» и от «пустого значения». Используется там,
            где не нужно парсить строку, а нужно только отделить
            числовые ячейки от нечисловых.
        """
        # bool проверяем ПЕРВЫМ: он подкласс int, поэтому обычный
        # isinstance(True, (int, float, Decimal)) дал бы True.
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float, Decimal))

class FilenameParser(BaseParser):
    """Парсер имён файлов.

    Роль: из имени файла отчёта вытаскиваем имя продавца.
          Формат имён нестабилен — берём всё до первого разделителя.
    """

    @staticmethod
    def parse_seller_name(filename: str) -> Optional[str]:
        """Извлекает имя продавца из имени файла.

        Вход: filename — например "ООО Ромашка_отчёт_2025.xlsx".
        Выход: "ООО Ромашка" или None.

        Роль: имя продавца стоит первым, отделено одним из символов
              "_", "-", "." или пробелом перед словом "отчёт".
              Если ничего не нашли — возвращаем имя файла без
              расширения, чтобы вызывающий код мог показать хоть
              что-то.
        """
        if not filename:
            return None
        # Убираем путь, если он есть.
        name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        # Убираем расширение.
        if "." in name:
            name = name.rsplit(".", 1)[0]

        # Пробуем разные разделители.
        for sep in ("_", " - ", "-"):
            if sep in name:
                candidate = name.split(sep, 1)[0].strip()
                if candidate:
                    return candidate
        # Fallback: возвращаем всё, что осталось.
        return name.strip() or None


class KizParser(BaseParser):
    """Парсер и нормализатор КИЗов.

    Роль: единая точка «чистки» кодов маркировки. КИЗы приходят
          из разных источников с разным форматированием — здесь
          приводим их к каноничному виду.
    """

    # Паттерн: оставляем только hex-символы и допустимые разделители.
    _CLEAN_RE = re.compile(r"[^0-9a-fA-F]")

    @staticmethod
    def clean(text) -> Optional[str]:
        """Очищает КИЗ до каноничного вида.

        Вход: text — строка с КИЗом (может содержать пробелы,
              дефисы, невидимые символы).
        Выход: строка только из hex-символов в нижнем регистре
               или None, если после очистки ничего не осталось.

        Роль: КИЗ используется как ключ в хранилище. Все источники
              должны давать одинаковый ключ для одного и того же
              кода — поэтому чистим унифицированно.
        """
        if text is None:
            return None
        cleaned = KizParser._CLEAN_RE.sub("", str(text)).lower()
        return cleaned or None

@dataclass
class PreFinalRow:
    """Одна строка предитогового файла ЧЗ МП.

    Роль:
        Типизированное представление строки листа «предитоговый
        файл продавца». Заменяет набор магических индексов
        row[1] / row[5] / row[6] / row[11] именованными полями.
        Используется GenerateSalesService при построении файлов
        продаж между продавцами.

    Поля:
        kiz — полный КИЗ из столбца B.
        owner_company — компания-владелец КИЗа из столбца L.
        brand — бренд товара из столбца G.
        product_name — наименование продукта из столбца F.
    """
    kiz: str
    owner_company: str
    brand: str
    product_name: str

    @classmethod
    def from_row(cls, row: tuple,
                 min_columns: int = 12) -> "PreFinalRow | None":
        """Создаёт PreFinalRow из строки листа Excel.

        Вход:
            row — кортеж значений строки (как выдаёт openpyxl
                  в режиме values_only=True).
            min_columns — минимальная длина row. Если фактическая
                          длина меньше — строка считается
                          некорректной и метод вернёт None.

        Выход:
            PreFinalRow, если удалось прочитать КИЗ и владельца.
            None — если row короче min_columns, либо КИЗ пустой,
            либо владелец пустой.

        Роль:
            Единственная точка знания о раскладке столбцов
            предитогового файла. Значения приводятся к str и
            очищаются от краевых пробелов; None становится "".
            Если КИЗ или владелец пусты — строка не имеет смысла
            для дальнейшей обработки и отбрасывается здесь.
        """
        if len(row) < min_columns:
            return None

        def _to_str(value) -> str:
            """Приводит значение ячейки к строке без краевых пробелов.

            Вход: value — значение из row.
            Выход: str; пустая строка, если value is None.
            """
            return str(value).strip() if value is not None else ""

        kiz = _to_str(row[1])
        product_name = _to_str(row[5])
        brand = _to_str(row[6])
        owner_company = _to_str(row[11])

        if not kiz or not owner_company:
            return None

        return cls(
            kiz=kiz,
            owner_company=owner_company,
            brand=brand,
            product_name=product_name,
        )
@dataclass
class ReturnsRow:
    """Одна строка файла возвратов.

    Роль:
        Типизированное представление строки файла «Возвраты_{date}.xlsx»
        (тот, что создаётся ReturnsPreparationService). Заменяет набор
        магических индексов row[0] / row[1] / row[2] / row[3] / row[5]
        именованными полями. Используется ReturnsTransferReader при
        подготовке передач КИЗов между продавцами.

    Поля:
        kiz — полный КИЗ из столбца A.
        status — статус операции из столбца B (например, «ВЫБЫЛ»).
        product_name — наименование продукта из столбца C.
        brand — бренд товара из столбца D.
        owner_company — компания-владелец КИЗа из столбца F.

    Примечание:
        Столбец E (индекс row[4]) в файле есть, но в этом dataclass
        намеренно не включается: он не используется ни одним
        сценарием. Оставлен в исходном файле и в списке
        COLUMNS_TO_KEEP — потери данных нет.
    """
    kiz: str
    status: str
    product_name: str
    brand: str
    owner_company: str

    @classmethod
    def from_row(cls, row: tuple,
                 min_columns: int = 6) -> "ReturnsRow | None":
        """Создаёт ReturnsRow из строки файла возвратов.

        Вход:
            row — кортеж значений строки (как выдаёт openpyxl
                  в режиме values_only=True).
            min_columns — минимальная длина row. Если фактическая
                          длина меньше — строка считается
                          некорректной и метод вернёт None.

        Выход:
            ReturnsRow, если удалось прочитать КИЗ.
            None — если row короче min_columns либо КИЗ пустой.

        Роль:
            Единственная точка знания о раскладке столбцов файла
            возвратов. Значения приводятся к str и очищаются от
            краевых пробелов; None становится "". Если КИЗ пуст —
            строка бесполезна для дальнейшей обработки и
            отбрасывается здесь. Пустой brand или owner_company
            не отбрасывается: вызывающий код решает сам.
        """
        if len(row) < min_columns:
            return None

        def _to_str(value) -> str:
            """Приводит значение ячейки к строке без краевых пробелов.

            Вход: value — значение из row.
            Выход: str; пустая строка, если value is None.
            """
            return str(value).strip() if value is not None else ""

        kiz = _to_str(row[0])
        if not kiz:
            return None

        return cls(
            kiz=kiz,
            status=_to_str(row[1]),
            product_name=_to_str(row[2]),
            brand=_to_str(row[3]),
            owner_company=_to_str(row[5]),
        )