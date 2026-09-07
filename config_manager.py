import json, logging, os
from pathlib import Path
from models.models import Seller, Brand

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(__file__).parent / "data" / "config.json"
        self.data = {}
        self._sellers_cache: list[dict] | None = None
        self._brands_cache: list[dict] | None = None
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.data = {}
        else:
            self.data = {}
        self._sellers_cache = self.data.get("sellers", [])
        self._brands_cache = self.data.get("brands", [])

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def get_list(self, key):
        return self.data.get(key, [])

    def get_sellers_objects(self, brands_dict: dict[str, Brand] = None) -> list[Seller]:
        sellers_list = self._sellers_cache if self._sellers_cache is not None else []
        sellers = []
        for item in sellers_list:
            if not isinstance(item, dict):
                continue
            if "brands" in item and isinstance(item["brands"], list):
                item["brands"] = list(dict.fromkeys(item["brands"]))
            seller = Seller.from_dict(item, brands_dict)
            sellers.append(seller)
        return sellers

    def get_sellers_with_brands(self) -> list[Seller]:
        brands = self.get_brands_objects()
        brands_dict = {b.name: b for b in brands}
        return self.get_sellers_objects(brands_dict)

    def set_sellers_objects(self, sellers: list[Seller]):
        sellers_list = [s.to_dict() for s in sellers]
        self.data["sellers"] = sellers_list
        self._sellers_cache = sellers_list
        self.save()

    def get_brands_objects(self) -> list[Brand]:
        brands_list = self._brands_cache if self._brands_cache is not None else []
        return [Brand.from_dict(item) for item in brands_list if isinstance(item, dict)]

    def set_brands_objects(self, brands: list[Brand]):
        brands_list = [b.to_dict() for b in brands]
        self.data["brands"] = brands_list
        self._brands_cache = brands_list
        self.save()

    def get_brands_dict(self) -> dict[str, Brand]:
        brands = self.get_brands_objects()
        return {b.name: b for b in brands}


