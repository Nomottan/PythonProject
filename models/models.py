from typing import Optional, Set

class Brand:
    """Модель бренда."""
    def __init__(self, name: str, keys: list = None):
        self.name = name
        self.keys = keys if keys is not None else []
        self.sellers: list[Seller] = []          # связанные продавцы (объекты Seller)

    def add_seller(self, seller: 'Seller'):
        """Добавляет продавца и автоматически обновляет его список брендов."""
        if seller not in self.sellers:
            self.sellers.append(seller)
            seller.brands.append(self)           # двусторонняя связь

    def remove_seller(self, seller: 'Seller'):
        """Удаляет продавца и автоматически обновляет его список брендов."""
        if seller in self.sellers:
            self.sellers.remove(seller)
            seller.brands.remove(self)           # двусторонняя связь

    def get_sellers_names(self) -> list[str]:
        """Возвращает список имён продавцов, связанных с брендом."""
        return [s.name for s in self.sellers]

    def to_dict(self) -> dict:
        """Сериализация для сохранения в JSON."""
        return {
            "name": self.name,
            "keys": self.keys
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Brand':
        """Создание объекта из словаря (без восстановления связей)."""
        return cls(data["name"], data.get("keys", []))

    def __repr__(self):
        return f"<Brand: {self.name}>"

class Seller:
    """Модель продавца."""
    def __init__(self, name: str, inn: str = "", keys: list = None, brands: list = None, company: str = ""):
        self.name = name
        self.inn = inn
        self.company = company
        self.keys = keys if keys is not None else []
        self.brands = brands if brands is not None else []   # список объектов Brand

    def add_brand(self, brand: Brand):
        """Добавляет бренд и автоматически обновляет его список продавцов."""
        if brand not in self.brands:
            self.brands.append(brand)
            brand.sellers.append(self)           # двусторонняя связь

    def remove_brand(self, brand: Brand):
        """Удаляет бренд и автоматически обновляет его список продавцов."""
        if brand in self.brands:
            self.brands.remove(brand)
            brand.sellers.remove(self)
            # двусторонняя связь

    def get_brand_keys(self) -> list[str]:
        keys = []
        for brand in self.brands:
            keys.extend(brand.keys)
        return keys

    def has_key(self, key: str) -> bool:
        """Проверяет, является ли переданный ключ одним из вариантов имени продавца."""
        return key in self.keys

    def to_dict(self) -> dict:
        """Сериализация для сохранения в JSON (бренды сохраняются как имена)."""
        return {
            "name": self.name,
            "inn": self.inn,
            "company": self.company,
            "keys": self.keys,
            "brands": [b.name for b in self.brands],
        }

    @classmethod
    def from_dict(cls, data: dict, brands_by_name: dict[str, Brand] = None) -> 'Seller':
        """
        Создание объекта из словаря с возможностью восстановления связей.
        Если передан brands_by_name, то поле brands заполняется объектами Brand.
        """
        seller = cls(name = data["name"],
                     inn = data.get("inn", ""),
                     company=data.get("company", ""),
                     keys = data.get("keys", []))
        if brands_by_name:
            for brand_name in data.get("brands", []):
                brand = brands_by_name.get(brand_name)
                if brand:
                    seller.add_brand(brand)       # устанавливает двустороннюю связь
        return seller

    def __repr__(self):
        return f"<Seller: {self.name}>"

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