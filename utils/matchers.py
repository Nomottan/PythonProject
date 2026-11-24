"""
Утилита сопоставления значений со справочником.

Содержит Matcher — универсальные операции над парой
«коллекция объектов + атрибут поиска»: найти первое совпадение,
все совпадения, собрать множество ключей.

Роль в программе:
    Единая точка сверки значения с коллекцией. Не привязана
    к сущности: продавцы, бренды, контрагенты — всё, у чего
    есть атрибут-строка или атрибут-список строк.

Стратегии:
    first  — только точное совпадение .
    many   — сначала точное, затем вхождение ключа в значение.
    keys   — множество нормализованных значений атрибута).

Нормализация — TextParser.normalize (strip + lower).
"""

from utils.text_utils import TextUtils

class Matcher:
    """Сопоставление значения со справочником.

    Контракт методов:
        items — список объектов (атрибуты читаются через getattr).
        attribute — имя атрибута (str). Значение атрибута может
                    быть строкой, числом, None или
                    списком/кортежем/множеством строк.
        value — искомое значение (приводится к строке).

    Публичный API:
        first, many, keys.
    """

    @staticmethod
    def _keys_of(item, attribute, transform=None) -> list:
        """Возвращает нормализованные ключи объекта по атрибуту.

        Вход:
            item — объект.
            attribute — имя атрибута.

        Выход: список нормализованных непустых ключей.

        Роль: единая точка чтения ключей. Списочные атрибуты
              (например, Seller.keys) разворачиваются поэлементно.
        """
        raw = getattr(item, attribute, None)
        if raw is None:
            return []

        if isinstance(raw, (list, tuple, set)):
            values = raw
        else:
            values = (raw,)

        keys = []
        for value in values:
            if transform is not None:
                value = transform(value)
            normalized = TextUtils.normalize(value)
            if normalized:
                keys.append(normalized)
        return keys

    @staticmethod
    def first(items, attribute, value, transform=None):
        """Возвращает первый объект с точным совпадением.

        Вход:
            items — список объектов.
            attribute — имя атрибута поиска.
            value — искомое значение.

        Выход: объект или None.

        Роль: Совпадение только точное — вхождения не учитываются,
              иначе владелец из Excel мог бы «прилипнуть» к чужому продавцу
              по частичному имени.
        """
        if transform is not None:
            value = transform(value)
        needle = TextUtils.normalize(value)
        if not needle or not items:
            return None

        for item in items:
            if needle in Matcher._keys_of(item, attribute):
                return item
        return None

    @staticmethod
    def many(items, attribute, value, transform=None) -> list:
        """Возвращает все объекты, совпавшие со значением.

        Вход:
            items — список объектов.
            attribute — имя атрибута поиска.
            value — искомое значение.

        Выход: list найденных объектов. Сначала точные совпадения;
               если их нет — по вхождению ключа в значение.
               Дубликаты по идентичности отбрасываются,
               порядок — как в items.

        Роль: Имя файла содержит
              лишний текст вокруг ключа, поэтому нужен второй
              проход по вхождению.
        """
        if transform is not None:
            value = transform(value)
        needle = TextUtils.normalize(value)
        if not needle or not items:
            return []

        exact = []
        seen = set()
        for item in items:
            if id(item) in seen:
                continue
            if needle in Matcher._keys_of(item, attribute):
                seen.add(id(item))
                exact.append(item)
        if exact:
            return exact

        partial = []
        for item in items:
            if id(item) in seen:
                continue
            for key in Matcher._keys_of(item, attribute):
                if key in needle:
                    seen.add(id(item))
                    partial.append(item)
                    break

        return partial

    @staticmethod
    def keys(items, attribute, transform=None) -> set:
        """Собирает множество нормализованных значений атрибута.

        Вход:
            items — список объектов.
            attribute — имя атрибута.

        Выход: set[str] — нормализованные значения, без пустых.

        Роль: Результат — набор,
              с которым сравнивают входящие данные
              (например, «владелец из числа продавцов»).
        """
        result = set()
        for item in items or ():
            for key in Matcher._keys_of(item, attribute):
                result.add(key)
        return result