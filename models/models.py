from typing import Optional, Set
from dataclasses import dataclass, field

@dataclass
class AddressModel:
    index: str = ""
    region_code: str = ""
    region_name: str = ""
    city: str = ""
    settlement: str = ""
    street: str = ""
    house: str = ""
    building: str = ""

    def __str__(self) -> str:
        parts = [self.index, self.region_name, self.city,
                 self.settlement, self.street, self.house, self.building]
        return ", ".join(p for p in parts if p)

    def is_empty(self) -> bool:
        """Проверяет, пусты ли все поля адреса."""
        return not any([
            self.index, self.region_code, self.region_name,
            self.city, self.settlement, self.street,
            self.house, self.building
        ])

    def to_dict(self) -> dict:
        """Сериализует модель в словарь для JSON (только непустые поля)."""
        data = {}
        if self.index: data["index"] = self.index
        if self.region_code: data["region_code"] = self.region_code
        if self.region_name: data["region_name"] = self.region_name
        if self.city: data["city"] = self.city
        if self.settlement: data["settlement"] = self.settlement
        if self.street: data["street"] = self.street
        if self.house: data["house"] = self.house
        if self.building: data["building"] = self.building
        return data

    @classmethod
    def from_dict(cls, raw: dict) -> "AddressModel":
        """Десериализует модель из словаря JSON."""
        raw = raw or {}
        return cls(
            index=raw.get("index", ""),
            region_code=raw.get("region_code", ""),
            region_name=raw.get("region_name", ""),
            city=raw.get("city", ""),
            settlement=raw.get("settlement", ""),
            street=raw.get("street", ""),
            house=raw.get("house", ""),
            building=raw.get("building", ""),
        )

class Brand:
    """Модель бренда."""
    def __init__(self, name: str, keys: list = None,
                 requires_saving: bool = True):
        self.name = name
        self.keys = keys if keys is not None else []
        self.sellers: list[Seller] = []          # связанные продавцы (объекты Seller)
        self.requires_saving = requires_saving

    def add_seller(self, seller: 'Seller'):
        """Добавляет продавца и синхронизирует обратную сторону.

        Идемпотентен: повторный вызов не создаёт дублей ни в одной
        из сторон связи. Две стороны правятся независимо — если
        в одной уже есть запись, вторая всё равно получит свою.
        """
        if seller not in self.sellers:
            self.sellers.append(seller)
        if self not in seller.brands:
            seller.brands.append(self)           # двусторонняя связь

    def remove_seller(self, seller: 'Seller'):
        """Удаляет продавца и синхронизирует обратную сторону.

        Идемпотентен: при рассинхроне (запись есть только в одной
        стороне) не падает, а чистит то, что найдено. Две стороны
        правятся независимо.
        """
        if seller in self.sellers:
            self.sellers.remove(seller)
        if self in seller.brands:
            seller.brands.remove(self)           # двусторонняя связь

    def get_sellers_names(self) -> list[str]:
        """Возвращает список имён продавцов, связанных с брендом."""
        return [s.name for s in self.sellers]

    def get_all_keys(self) -> list[str]:
        """Возвращает все ключи бренда для распознавания.

        Вход: нет.
        Выход: новый список: self.keys + self.name (name последним).

        Роль:
            Единая точка для маппинга «ключ → Brand» в
            TextUtils.build_key_mapping. Возвращает новый список,
            чтобы вызывающий код не мог случайно мутировать
            self.keys. Порядок keys → name детерминирован —
            повторяемость маппинга. Нормализация (lower/strip) —
            на стороне build_key_mapping.
        """
        return list(self.keys) + [self.name]

    def to_dict(self) -> dict:
        """Сериализация для сохранения в JSON."""
        return {
            "name": self.name,
            "keys": self.keys,
            "requires_saving": self.requires_saving,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Brand':
        """Создание объекта из словаря (без восстановления связей).

        Поле requires_saving читается через `is not False` — только
        строгий False даёт False; None, 0, "false", отсутствие ключа
        и любые другие значения дают True. Это защищает от случайно
        повреждённого JSON и от старых записей без ключа.
        """
        return cls(
            data["name"],
            data.get("keys", []),
            data.get("requires_saving", True) is not False,
        )

    def __repr__(self):
        return f"<Brand: {self.name}>"


class Seller:
    """Модель продавца.

    Поля:
        name — имя продавца.
        inn — ИНН.
        keys — ключи для распознавания.
        brands — связанные объекты Brand.
        company — юр. лицо.
        tax - налоговая ставка
        phone, mail, edo_id, ogrn, kpp, director - текстовые реквизиты
        address - адрес в виде объекта
        priority — приоритет при разрешении конфликтов КИЗов:
                   1 — низкий, 2 — средний (дефолт), 3 — высокий.
                   Существующие записи без priority получают 2.
    """

    @staticmethod
    def _safe_priority(value) -> int:
        """Приводит priority к int в [1, 3] с fallback 2.

        Вход: value — любое значение из JSON (int, str, None, ...).
        Выход: int 1, 2 или 3. Дефолт 2 — при любом невалидном входе.

        Роль:
            Защита от битого JSON по аналогии с Brand.from_dict
            (там — через `is not False`). Здесь: try int, затем
            clamp [1, 3]; любой сбой или выход за диапазон → 2.
        """
        try:
            p = int(value)
        except (TypeError, ValueError):
            return 2
        if p < 1 or p > 3:
            return 2
        return p

    def __init__(self, name: str, inn: str = "", keys: list = None,
                 brands: list = None, company: str = "", tax: int = 5,
                 priority: int = 2, phone: str = "", mail: str = "",
                 address: AddressModel = None, edo_id: str = "",
                 ogrn: str = "", kpp: str = "", director: str = "",):
        self.name = name
        self.inn = inn
        self.company = company
        self.tax = tax
        self.keys = keys if keys is not None else []
        self.brands = brands if brands is not None else []
        self.priority = priority
        self.phone = phone
        self.mail = mail
        self.address = address if address is not None else AddressModel()
        self.edo_id = edo_id
        self.ogrn = ogrn
        self.kpp = kpp
        self.director = director


    def add_brand(self, brand: Brand):
        """Добавляет бренд и синхронизирует обратную сторону.

        Идемпотентен: повторный вызов не создаёт дублей ни в одной
        из сторон связи. Две стороны правятся независимо.
        """
        if brand not in self.brands:
            self.brands.append(brand)
        if self not in brand.sellers:
            brand.sellers.append(self)           # двусторонняя связь

    def remove_brand(self, brand: Brand):
        """Удаляет бренд и синхронизирует обратную сторону.

        Идемпотентен: при рассинхроне (запись есть только в одной
        стороне) не падает, а чистит то, что найдено. Две стороны
        правятся независимо.
        """
        if brand in self.brands:
            self.brands.remove(brand)
        if self in brand.sellers:
            brand.sellers.remove(self)           # двусторонняя связь

    def get_brand_keys(self) -> list[str]:
        keys = []
        for brand in self.brands:
            keys.extend(brand.get_all_keys())
        return keys

    def has_key(self, key: str) -> bool:
        """Проверяет, является ли переданный ключ одним из вариантов имени продавца."""
        return key in self.keys

    def to_dict(self) -> dict:
        """Сериализация для JSON.

        Правило:
          - name — всегда (обязательное);
          - пустые строки/коллекции/адрес — опускаем (нет данных);
          - tax, priority — всегда (бизнес-числа, дефолт может эволюционировать);
          - keys/brands — копии, не ссылки.
        """
        data = {"name": self.name}

        # Опциональные строковые идентификаторы: только непустые
        for key in ("inn", "company", "phone", "mail",
                    "edo_id", "ogrn", "kpp", "director"):
            value = getattr(self, key, "")
            if value and value.strip():
                data[key] = value

        if self.tax != 5:
            data["tax"] = self.tax
        if self.priority !=2 :
            data["priority"] = self.priority

        # Коллекции: только непустые, копии
        if self.keys:
            data["keys"] = list(self.keys)
        if self.brands:
            data["brands"] = [b.name for b in self.brands]

        # Адрес: только непустой, как dict
        if self.address is not None and not self.address.is_empty():
            data["address"] = self.address.to_dict()

        return data

    @classmethod
    def from_dict(cls, data: dict, brands_by_name: dict[str, Brand] = None) -> 'Seller':
        data = data or {}
        seller = cls(
            name=data["name"],
            inn=data.get("inn", ""),
            company=data.get("company", ""),
            tax=data.get("tax", 5),
            keys=data.get("keys", []),
            priority=cls._safe_priority(data.get("priority", 2)),
            phone=data.get("phone", ""),
            mail=data.get("mail", ""),
            address=AddressModel.from_dict(data.get("address") or {}),
            edo_id=data.get("edo_id", ""),
            ogrn=data.get("ogrn", ""),
            kpp=data.get("kpp", ""),
            director=data.get("director", ""),
        )
        if brands_by_name:
            for brand_name in data.get("brands", []):
                brand = brands_by_name.get(brand_name)
                if brand:
                    seller.add_brand(brand)
        return seller

class SupplyItem:
    """Товар из листа поставки."""
    def __init__(self, row_num: int, article: str, name: str, count: Optional[int],
                 keywords: Set[str], brand: Optional[str] = None):
        self.row_num = row_num
        self.article = article
        self.name = name
        self.count = count
        self.keywords = keywords
        self.brand = brand
        self.found = False
        self.matched_candidate = None  # Candidate object
        self.stage = 0  # 0 - не найдено, 1, 2, 3

class Candidate:
    def __init__(self, name: str, count: Optional[int], serial: Optional[str],
                 source_file: str, keywords: Set[str], brand: Optional[str] = None,
                 shk: Optional[str] = None):  # новое поле
        self.name = name
        self.count = count
        self.serial = serial
        self.source_file = source_file
        self.keywords = keywords
        self.brand = brand
        self.shk = shk
        self.used = False