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
        _logger: LoggerV2 или None.

    Публичный API: get_sellers_objects, set_sellers_objects,
    get_sellers_with_brands, get_brands_objects, set_brands_objects,
    get_brands_dict.
    """

    def __init__(self, main_config: MainConfig,
                 log_manager_v2=None) -> None:
        """Конструктор.

        Вход:
            main_config — хранилище конфига.
            log_manager_v2 — LogManagerV2 или None. При None —
                             self._logger тоже None, все вызовы
                             logger.* молча пропускаются.

        Роль: сохраняет ссылки, создаёт логгер для сообщений
              о работе с моделями и записями в config.json.
        """
        self._config: MainConfig = main_config
        self._log_manager_v2 = log_manager_v2
        self._logger = None
        if log_manager_v2 is not None:
            self._logger = log_manager_v2.create_logger_v2(
                source="SellersBrandsService",
                domain="sellers_brands",
            )

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

        Логирование:
            warning — если корень «sellers» не список или элемент
                      не dict (битый конфиг).
            debug — количество прочитанных продавцов.
        """
        raw_list = self._config.get("sellers", [])
        if not isinstance(raw_list, list):
            if self._logger is not None:
                self._logger.warning(
                    "config.json: ключ 'sellers' должен быть списком, "
                    f"получен {type(raw_list).__name__}. Возвращаю []."
                )
            return []

        sellers = []
        for item in raw_list:
            if not isinstance(item, dict):
                if self._logger is not None:
                    self._logger.warning(
                        "config.json: элемент списка 'sellers' не "
                        f"является словарём ({type(item).__name__}), "
                        "пропущен."
                    )
                continue
            # Дедупликация брендов в копии — не мутируем storage.
            item_copy = dict(item)
            if "brands" in item_copy and isinstance(item_copy["brands"], list):
                item_copy["brands"] = list(dict.fromkeys(item_copy["brands"]))
            sellers.append(Seller.from_dict(item_copy, brands_dict))

        if self._logger is not None:
            self._logger.debug(
                f"get_sellers_objects: прочитано {len(sellers)} продавцов"
            )
        return sellers

    def get_sellers_with_brands(self) -> list:
        """Возвращает список Seller с восстановленными связями.

        Выход: list[Seller] с заполненным .brands.

        Роль: удобный метод — читает brands и sellers, связывает
              их через brands_dict. Логирование — в вызываемых
              get_brands_dict / get_sellers_objects.
        """
        brands_dict = self.get_brands_dict()
        return self.get_sellers_objects(brands_dict)

    def set_sellers_objects(self, sellers: list) -> None:
        """Сохраняет список Seller в конфиг.

        Вход: sellers — list[Seller].

        Выход: нет.

        Роль: сериализует в dict через to_dict, записывает в MainConfig.
              MainConfig сам вызывает save().

        Логирование:
            debug — количество сохранённых продавцов.
            critical — если сериализация или запись упали.
        """
        try:
            serialized = [s.to_dict() for s in sellers]
            self._config.set("sellers", serialized)
            if self._logger is not None:
                self._logger.debug(
                    f"set_sellers_objects: сохранено {len(serialized)} "
                    f"продавцов"
                )
        except Exception as e:
            if self._logger is not None:
                self._logger.critical(
                    f"Ошибка сохранения продавцов: {e}",
                    can_influence=False,
                )

    # ---------- Brands ----------

    def get_brands_objects(self) -> list:
        """Возвращает список Brand.

        Выход: list[Brand].

        Роль: читает список dict-ов из конфига, конвертирует.
              Связи Brand.sellers не восстанавливаются — они
              появились как побочный эффект get_sellers_with_brands.

        Логирование:
            warning — если корень «brands» не список или элемент
                      не dict.
            debug — количество прочитанных брендов.
        """
        raw_list = self._config.get("brands", [])
        if not isinstance(raw_list, list):
            if self._logger is not None:
                self._logger.warning(
                    "config.json: ключ 'brands' должен быть списком, "
                    f"получен {type(raw_list).__name__}. Возвращаю []."
                )
            return []

        brands = []
        for item in raw_list:
            if not isinstance(item, dict):
                if self._logger is not None:
                    self._logger.warning(
                        "config.json: элемент списка 'brands' не "
                        f"является словарём ({type(item).__name__}), "
                        "пропущен."
                    )
                continue
            brands.append(Brand.from_dict(item))

        if self._logger is not None:
            self._logger.debug(
                f"get_brands_objects: прочитано {len(brands)} брендов"
            )
        return brands

    def set_brands_objects(self, brands: list) -> None:
        """Сохраняет список Brand в конфиг.

        Вход: brands — list[Brand].

        Выход: нет.

        Роль: сериализует через to_dict, пишет в MainConfig.

        Логирование:
            debug — количество сохранённых брендов.
            critical — если сериализация или запись упали.
        """
        try:
            serialized = [b.to_dict() for b in brands]
            self._config.set("brands", serialized)
            if self._logger is not None:
                self._logger.debug(
                    f"set_brands_objects: сохранено {len(serialized)} "
                    f"брендов"
                )
        except Exception as e:
            if self._logger is not None:
                self._logger.critical(
                    f"Ошибка сохранения брендов: {e}",
                    can_influence=False,
                )

    def get_brands_dict(self) -> dict:
        """Возвращает {name: Brand} для восстановления связей.

        Выход: dict[str, Brand].
        Роль: короткий хелпер, чтобы не дублировать построение
              словаря в вызывающем коде.
        """
        return {b.name: b for b in self.get_brands_objects()}