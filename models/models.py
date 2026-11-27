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

class Counterparty:
    """Базовая модель юрлица.

    Поля:
        name — свободный лейбл. Может быть пустым: тогда UI
               показывает краткое юр. наименование.
        company — юр. наименование: "ИП Гаак Наталья Сергеевна"
                  или "ООО «РВБ»".
        org_type — "ООО" или "ИП". По умолчанию "ООО".
        director — директор. Для ИП — ФИО, для ООО — отдельно.
        inn, phone, mail, edo_id, ogrn, kpp, oktmo — реквизиты.
        address — AddressModel.
        keys — ключи для распознавания.

    Роль:
        Базовая модель для Counterparty и Seller. Чистые данные.
        Читается/пишется через CounterpartiesService по ключу
        "counterparties". Сериализация ленивая: company и name
        пишутся только непустыми, пустые строки опускаются.
    """

    @staticmethod
    def _safe_org_type(value) -> str:
        """Приводит org_type к "ООО" или "ИП".

        Вход: value — любое значение из JSON.
        Выход: "ИП" если value == "ИП", иначе "ООО".

        Роль: защита от битого JSON и от попадания UI-состояния
              "Не опознан" в модель. В модели только два типа.
        """
        if isinstance(value, str) and value.strip() == "ИП":
            return "ИП"
        return "ООО"

    def __init__(self, name: str = "", company: str = "",
                 org_type: str = "ООО", director: str = "",
                 inn: str = "", address: AddressModel = None,
                 phone: str = "", mail: str = "", edo_id: str = "",
                 ogrn: str = "", kpp: str = "", oktmo: str = "",
                 keys: list = None):
        self.name = name or ""
        self.company = company or ""
        self.org_type = self._safe_org_type(org_type)
        self.director = director or ""
        self.inn = inn or ""
        self.address = address if address is not None else AddressModel()
        self.phone = phone or ""
        self.mail = mail or ""
        self.edo_id = edo_id or ""
        self.ogrn = ogrn or ""
        self.kpp = kpp or ""
        self.oktmo = oktmo or ""
        self.keys = keys if keys is not None else []

    def has_key(self, key: str) -> bool:
        """Проверяет, является ли ключ одним из вариантов."""
        return key in self.keys

    def to_dict(self) -> dict:
        """Сериализация для JSON.

        Правило:
          - company — только непустой;
          - name — только непустой;
          - org_type — только "ИП" (ООО — дефолт);
          - пустые строки — опускаем;
          - keys — только непустые;
          - address — только непустой.
        """
        data = {}
        if self.company and self.company.strip():
            data["company"] = self.company
        if self.name and self.name.strip():
            data["name"] = self.name
        if self.org_type == "ИП":
            data["org_type"] = self.org_type
        for key in ("director", "inn", "phone", "mail",
                    "edo_id", "ogrn", "kpp", "oktmo"):
            value = getattr(self, key, "")
            if value and value.strip():
                data[key] = value
        if self.keys:
            data["keys"] = list(self.keys)
        if self.address is not None and not self.address.is_empty():
            data["address"] = self.address.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Counterparty":
        """Десериализация из JSON.

        Миграция:
            если нет company, а есть name — старый Counterparty,
            где name был юр. наименованием. Переносим name в
            company, name оставляем для текущего окна до его
            перевода на company.
        """
        data = data or {}
        company = data.get("company", "")
        name = data.get("name", "")
        if not company and name:
            company = name
        return cls(
            name=name if isinstance(name, str) else "",
            company=company if isinstance(company, str) else "",
            org_type=cls._safe_org_type(data.get("org_type", "ООО")),
            director=data.get("director", ""),
            inn=data.get("inn", ""),
            address=AddressModel.from_dict(data.get("address") or {}),
            phone=data.get("phone", ""),
            mail=data.get("mail", ""),
            edo_id=data.get("edo_id", ""),
            ogrn=data.get("ogrn", ""),
            kpp=data.get("kpp", ""),
            oktmo=data.get("oktmo", ""),
            keys=data.get("keys", []),
        )

    def __repr__(self) -> str:
        """Отладочное представление."""
        return (
            f"Counterparty(name={self.name!r}, "
            f"company={self.company!r}, org_type={self.org_type!r})"
        )

class Seller(Counterparty):
    """Модель продавца — расширение Counterparty.

    Добавляет:
        brands — связанные Brand.
        tax — налоговая ставка.
        priority — приоритет 1..3, дефолт 2.
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

    def __init__(self, name: str = "", company: str = "",
                 org_type: str = "ООО", director: str = "",
                 inn: str = "", address: AddressModel = None,
                 phone: str = "", mail: str = "", edo_id: str = "",
                 ogrn: str = "", kpp: str = "", oktmo: str = "",
                 keys: list = None, brands: list = None,
                 tax: int = 5, priority: int = 2):
        super().__init__(
            name=name, company=company, org_type=org_type,
            director=director, inn=inn, address=address,
            phone=phone, mail=mail, edo_id=edo_id,
            ogrn=ogrn, kpp=kpp, oktmo=oktmo, keys=keys,
        )
        self.brands = brands if brands is not None else []
        self.tax = tax
        self.priority = priority

    def add_brand(self, brand: Brand):
        """Добавляет бренд и синхронизирует обратную сторону.

        Идемпотентен: повторный вызов не создаёт дублей ни в одной
        из сторон связи. Две стороны правятся независимо.
        """
        if brand not in self.brands:
            self.brands.append(brand)
        if self not in brand.sellers:
            brand.sellers.append(self)

    def remove_brand(self, brand: Brand):
        """Удаляет бренд и синхронизирует обратную сторону.

        Идемпотентен: при рассинхроне (запись есть только в одной
        стороне) не падает, а чистит то, что найдено. Две стороны
        правятся независимо.
        """
        if brand in self.brands:
            self.brands.remove(brand)
        if self in brand.sellers:
            brand.sellers.remove(self)

    def get_brand_keys(self) -> list[str]:
        """Возвращает ключи всех брендов продавца."""
        keys = []
        for brand in self.brands:
            keys.extend(brand.get_all_keys())
        return keys

    def to_dict(self) -> dict:
        """Сериализация Seller: общие поля + бренды/налог/приоритет."""
        data = super().to_dict()
        if self.tax != 5:
            data["tax"] = self.tax
        if self.priority != 2:
            data["priority"] = self.priority
        if self.brands:
            data["brands"] = [b.name for b in self.brands]
        return data

    @classmethod
    def from_dict(cls, data: dict,
                  brands_by_name: dict[str, Brand] = None) -> "Seller":
        """Десериализация Seller: общие поля + бренды/налог/приоритет."""
        data = data or {}
        seller = super().from_dict(data)
        seller.tax = data.get("tax", 5)
        seller.priority = cls._safe_priority(data.get("priority", 2))
        if brands_by_name:
            for brand_name in data.get("brands", []):
                brand = brands_by_name.get(brand_name)
                if brand:
                    seller.add_brand(brand)
        return seller

    def __repr__(self) -> str:
        """Отладочное представление."""
        return (
            f"Seller(name={self.name!r}, company={self.company!r}, "
            f"org_type={self.org_type!r})"
        )
class Signer:
    """Модель подписанта (сотрудника).

    Назначение:
        Хранит данные сотрудника, который может подписывать
        документы (УПД): ФИО одной строкой и должность.

    Роль в программе:
        Чистая модель данных. Читается/пишется через
        SellersBrandsService (get_signers_objects /
        set_signers_objects) по ключу "signers" в config.json.
        Разбиение ФИО на Фамилия/Имя/Отчество и приведение
        регистра — задача утилит (TextUtils) на стороне
        генератора УПД, а не модели.

    Поля:
        name — ФИО одной строкой («Иванов Иван Иванович»).
        role — должность. По умолчанию «Сотрудник».

    Публичный API:
        DEFAULT_ROLE — дефолтная должность.
        to_dict / from_dict — сериализация для JSON.
    """

    DEFAULT_ROLE = "Сотрудник"

    def __init__(self, name: str = "", role: str = DEFAULT_ROLE) -> None:
        """Конструктор.

        Вход:
            name — ФИО одной строкой. Пустая строка допустима:
                   запись может быть создана до заполнения.
            role — должность. Пустая строка или None → DEFAULT_ROLE.

        Роль: сохраняет поля как есть. Нормализация регистра
              и состава ФИО — в утилитах, не в модели.
        """
        self.name = name or ""
        self.role = role or self.DEFAULT_ROLE

    def to_dict(self) -> dict:
        """Сериализация для JSON.

        Выход: {"name": ..., "role": ...}.

        Роль: пишет оба поля всегда. role имеет семантический
              дефолт («Сотрудник»), поэтому правило «опускать
              пустое», как у Seller, здесь не нужно.
        """
        return {"name": self.name, "role": self.role}

    @classmethod
    def from_dict(cls, data: dict) -> "Signer":
        """Десериализация из JSON.

        Вход: data — dict из config.json или None.
        Выход: Signer.

        Роль: защита от битого JSON. Отсутствующий или
              нестроковый name → ""; отсутствующий, пустой или
              нестроковый role → DEFAULT_ROLE. Запись не
              пропускается даже при пустых полях — пользователь
              поправит вручную.
        """
        data = data or {}
        name = data.get("name", "")
        role = data.get("role", cls.DEFAULT_ROLE)
        return cls(
            name=name if isinstance(name, str) else "",
            role=role if isinstance(role, str) else cls.DEFAULT_ROLE,
        )

    def __repr__(self) -> str:
        """Отладочное представление."""
        return f"Signer(name={self.name!r}, role={self.role!r})"

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