"""
Сервис высокоуровневых операций над Seller/Brand.

MainConfig — это просто хранилище словаря. Модели Seller и Brand
требуют восстановления двусторонних связей (Seller.brands ↔
Brand.sellers), дедупликации — это и делает сервис.

Разделение:
    MainConfig — знает только про JSON.
    SellersBrandsService — знает про Seller и Brand.
"""

from models.models import Seller, Brand
from storage.main_config import MainConfig


class SellersBrandsService:
    """Высокоуровневые операции над Seller и Brand.

    Роль: между UI и MainConfig. UI не должен сам конвертировать
          dict ↔ Seller — это работа сервиса.

    Поля:
        _config: MainConfig — хранилище config.json.

    Публичный API: get_sellers_objects, set_sellers_objects,
    get_sellers_with_brands, get_brands_objects, set_brands_objects,
    get_brands_dict.
    """

    def __init__(self, main_config: MainConfig) -> None:
        """Конструктор.

        Вход: main_config — хранилище конфига.
        Роль: сохраняем ссылку, дальше используем только её.
        """
        self._config: MainConfig = main_config

    # ---------- Sellers ----------

    def get_sellers_objects(
        self, brands_dict: dict = None,
    ) -> list:
        """Возвращает список Seller.

        Вход:
            brands_dict — {name: Brand} для восстановления связей.
                          Если None, seller.brands останется пустым.

        Выход: list[Seller].

        Роль: читает список dict-ов из конфига, дедуплицирует бренды
              у каждого продавца (в локальной копии — не мутируя
              storage), конвертирует в Seller.from_dict.
        """
        raw_list = self._config.get("sellers", [])
        if not isinstance(raw_list, list):
            return []

        sellers = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            # Дедупликация брендов в копии — не мутируем storage.
            item_copy = dict(item)
            if "brands" in item_copy and isinstance(item_copy["brands"], list):
                item_copy["brands"] = list(dict.fromkeys(item_copy["brands"]))
            sellers.append(Seller.from_dict(item_copy, brands_dict))
        return sellers

    def get_sellers_with_brands(self) -> list:
        """Возвращает список Seller с восстановленными связями.

        Выход: list[Seller] с заполненным .brands.

        Роль: удобный метод — читает brands и sellers, связывает
              их через brands_dict. Раньше был на ConfigManager.
        """
        brands_dict = self.get_brands_dict()
        return self.get_sellers_objects(brands_dict)

    def set_sellers_objects(self, sellers: list) -> None:
        """Сохраняет список Seller в конфиг.

        Вход: sellers — list[Seller].
        Роль: сериализует в dict через to_dict, записывает в MainConfig.
              MainConfig сам вызывает save().
        """
        self._config.set("sellers", [s.to_dict() for s in sellers])

    # ---------- Brands ----------

    def get_brands_objects(self) -> list:
        """Возвращает список Brand.

        Выход: list[Brand].
        Роль: читает список dict-ов из конфига, конвертирует.
              Связи Brand.sellers не восстанавливаются — они
              появились как побочный эффект get_sellers_with_brands.
        """
        raw_list = self._config.get("brands", [])
        if not isinstance(raw_list, list):
            return []
        return [
            Brand.from_dict(item)
            for item in raw_list
            if isinstance(item, dict)
        ]

    def set_brands_objects(self, brands: list) -> None:
        """Сохраняет список Brand в конфиг.

        Вход: brands — list[Brand].
        Роль: сериализует через to_dict, пишет в MainConfig.
        """
        self._config.set("brands", [b.to_dict() for b in brands])

    def get_brands_dict(self) -> dict:
        """Возвращает {name: Brand} для восстановления связей.

        Выход: dict[str, Brand].
        Роль: короткий хелпер, чтобы не дублировать построение
              словаря в вызывающем коде.
        """
        return {b.name: b for b in self.get_brands_objects()}