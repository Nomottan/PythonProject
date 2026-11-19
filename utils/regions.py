"""Справочник регионов РФ."""

import difflib
from pathlib import Path

from utils.path_manager import PathManager


class Regions:
    """Утилиты для работы со справочником регионов.

    Роль: хранит кэш регионов, умеет загружать его из файла,
    нормализовать названия и искать регион по коду или названию.
    """

    _cache: dict[str, str] | None = None
    _norm_cache: dict[str, tuple[str, str]] | None = None

    _STOPWORDS: set[str] = {
        "г", "гор", "город", "обл", "область", "респ", "республика",
        "край", "ао", "автономный", "автономная", "автономное", "округ",
    }

    _DEFAULT_REGIONS: dict[str, str] = {
        "01": "Республика Адыгея (Адыгея)",
        "02": "Республика Башкортостан",
        "03": "Республика Бурятия",
        "04": "Республика Алтай",
        "05": "Республика Дагестан",
        "06": "Республика Ингушетия",
        "07": "Кабардино-Балкарская Республика",
        "08": "Республика Калмыкия",
        "09": "Карачаево-Черкесская Республика",
        "10": "Республика Карелия",
        "11": "Республика Коми",
        "12": "Республика Марий Эл",
        "13": "Республика Мордовия",
        "14": "Республика Саха (Якутия)",
        "15": "Республика Северная Осетия - Алания",
        "16": "Республика Татарстан (Татарстан)",
        "17": "Республика Тыва",
        "18": "Удмуртская Республика",
        "19": "Республика Хакасия",
        "20": "Чеченская Республика",
        "21": "Чувашская Республика - Чувашия",
        "22": "Алтайский край",
        "23": "Краснодарский край",
        "24": "Красноярский край",
        "25": "Приморский край",
        "26": "Ставропольский край",
        "27": "Хабаровский край",
        "28": "Амурская область",
        "29": "Архангельская область",
        "30": "Астраханская область",
        "31": "Белгородская область",
        "32": "Брянская область",
        "33": "Владимирская область",
        "34": "Волгоградская область",
        "35": "Вологодская область",
        "36": "Воронежская область",
        "37": "Ивановская область",
        "38": "Иркутская область",
        "39": "Калининградская область",
        "40": "Калужская область",
        "41": "Камчатский край",
        "42": "Кемеровская область - Кузбасс",
        "43": "Кировская область",
        "44": "Костромская область",
        "45": "Курганская область",
        "46": "Курская область",
        "47": "Ленинградская область",
        "48": "Липецкая область",
        "49": "Магаданская область",
        "50": "Московская область",
        "51": "Мурманская область",
        "52": "Нижегородская область",
        "53": "Новгородская область",
        "54": "Новосибирская область",
        "55": "Омская область",
        "56": "Оренбургская область",
        "57": "Орловская область",
        "58": "Пензенская область",
        "59": "Пермский край",
        "60": "Псковская область",
        "61": "Ростовская область",
        "62": "Рязанская область",
        "63": "Самарская область",
        "64": "Саратовская область",
        "65": "Сахалинская область",
        "66": "Свердловская область",
        "67": "Смоленская область",
        "68": "Тамбовская область",
        "69": "Тверская область",
        "70": "Томская область",
        "71": "Тульская область",
        "72": "Тюменская область",
        "73": "Ульяновская область",
        "74": "Челябинская область",
        "75": "Забайкальский край",
        "76": "Ярославская область",
        "77": "г. Москва",
        "78": "г. Санкт-Петербург",
        "79": "Еврейская автономная область",
        "83": "Ненецкий автономный округ",
        "86": "Ханты-Мансийский автономный округ - Югра",
        "87": "Чукотский автономный округ",
        "89": "Ямало-Ненецкий автономный округ",
        "90": "Запорожская область",
        "91": "Республика Крым",
        "92": "г. Севастополь",
        "93": "Донецкая Народная Республика",
        "94": "Луганская Народная Республика",
        "95": "Херсонская область",
        "99": "Иные территории, включая город и космодром Байконур"
    }

    @staticmethod
    def file_path() -> Path:
        return PathManager().get_data_file("Регионы.txt")

    @staticmethod
    def _ensure_file() -> None:
        """Создаёт файл справочника при отсутствии."""
        path = Regions.file_path()
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Код | Название\n")
                for code in sorted(Regions._DEFAULT_REGIONS.keys()):
                    f.write(f"{code} | {Regions._DEFAULT_REGIONS[code]}\n")

    @staticmethod
    def reload() -> None:
        """Перечитывает справочник из файла."""
        Regions._ensure_file()
        Regions._cache = {}
        Regions._norm_cache = {}

        path = Regions.file_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("|", 1)
                    if len(parts) != 2:
                        continue
                    code = parts[0].strip()
                    name = parts[1].strip()
                    if code and name:
                        Regions._cache[code] = name
        except Exception:
            pass

        if not Regions._cache:
            Regions._cache = dict(Regions._DEFAULT_REGIONS)

        for code, name in Regions._cache.items():
            norm = Regions.normalize_region_name(name)
            Regions._norm_cache[norm] = (code, name)

    @staticmethod
    def _ensure_cache() -> None:
        """Гарантирует, что кэш загружен."""
        if Regions._cache is None:
            Regions.reload()

    @staticmethod
    def get_all() -> dict[str, str]:
        """Возвращает копию словаря регионов."""
        Regions._ensure_cache()
        return dict(Regions._cache)

    @staticmethod
    def get_region_name(code: str) -> str:
        """Возвращает название региона по коду."""
        Regions._ensure_cache()
        return Regions._cache.get(code.strip(), "")

    @staticmethod
    def normalize_region_name(text: str) -> str:
        """Нормализует название региона для поиска."""
        if not text:
            return ""
        t = text.lower().strip().replace("ё", "е")
        t = t.replace(".", " ").replace(",", " ")
        tokens = t.split()

        while tokens and tokens[-1] in Regions._STOPWORDS:
            tokens.pop()

        return " ".join(tokens)

    @staticmethod
    def find_region(text: str) -> tuple[str, str] | None:
        """Ищет регион по названию или коду."""
        Regions._ensure_cache()
        norm = Regions.normalize_region_name(text)
        if not norm:
            return None

        if Regions._norm_cache is not None and norm in Regions._norm_cache:
            return Regions._norm_cache[norm]

        code = text.strip()
        if code in Regions._cache:
            return code, Regions._cache[code]

        if Regions._norm_cache:
            close = difflib.get_close_matches(norm, list(Regions._norm_cache.keys()), n=1, cutoff=0.6)
            if close:
                return Regions._norm_cache[close[0]]

        return None