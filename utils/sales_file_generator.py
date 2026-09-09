import random
from pathlib import Path
from typing import List, Dict, Optional
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils
from utils.kiz_utils import KizUtils


class SalesFileGenerator:
    """
    Генератор файлов продаж (Excel) с новой структурой.
    Имя файла: "{от кого} - {кому} : {ИНН}.xlsx"
    Столбцы: Наименование продукта, КИЗ (31 символов), GTIN (с 3 по 16), Цена (случайная 10-20)
    """

    DEFAULT_HEADERS = [
        "Наименование продукта",
        "КИЗ",
        "GTIN",
        "Цена"
    ]

    def __init__(self, work_folder: Path, headers: Optional[List[str]] = None):
        self.work_folder = work_folder
        self.headers = headers or self.DEFAULT_HEADERS
        self.created_files: List[Path] = []
        self._stats: Dict[tuple, int] = {}

    def add_sale_row(self,
                     from_seller_name: str,
                     to_seller_name: str,
                     to_seller_inn: str,
                     product_name: str,
                     raw_kiz: str,
                     brand: Optional[str] = None,
                     owner_company: Optional[str] = None) -> Path:
        """
        Добавляет строку продажи в файл.
        :param from_seller_name: продавец-отправитель (для имени файла)
        :param to_seller_name: продавец-получатель (для имени файла)
        :param to_seller_inn: ИНН получателя (для имени файла)
        :param product_name: наименование продукта (записывается в файл)
        :param raw_kiz: полный КИЗ (из него будет взят сокращённый и GTIN)
        :param brand: бренд (не используется в новой структуре, но передаётся для совместимости)
        :param owner_company: компания-владелец (не используется, передаётся для совместимости)
        :return: путь к файлу
        """
        # Получаем сокращённый КИЗ (31 символ)
        storage_list = KizUtils.clean_kiz_for_storage(raw_kiz)
        if not storage_list:
            raise ValueError(f"Не удалось получить сокращённый КИЗ из {raw_kiz[:30]}...")
        kiz_short = storage_list[0]

        # GTIN – символы с 3 по 16 (индексы 2..15)
        gtin = kiz_short[2:16] if len(kiz_short) >= 16 else ""

        # Случайная цена от 10 до 20
        price = random.randint(10, 20)

        # Имя файла
        safe_from = TextUtils.sanitize_filename(from_seller_name)
        safe_to = TextUtils.sanitize_filename(to_seller_name)
        file_name = f"{safe_from} - {safe_to} : {to_seller_inn}.xlsx"
        file_path = self.work_folder / file_name

        row_data = [
            product_name,
            kiz_short,
            gtin,
            price
        ]

        ExcelHelper.append_row_to_file(file_path, row_data, headers=self.headers)

        if file_path not in self.created_files:
            self.created_files.append(file_path)

        key = (from_seller_name, to_seller_name)
        self._stats[key] = self._stats.get(key, 0) + 1

        return file_path

    def get_created_files(self) -> List[Path]:
        return self.created_files

    def remove_empty_files(self) -> int:
        removed = 0
        for file_path in self.created_files[:]:
            if ExcelHelper.is_file_empty(file_path):
                try:
                    file_path.unlink()
                    removed += 1
                    self.created_files.remove(file_path)
                except Exception:
                    pass
        return removed

    def get_stats(self) -> Dict[tuple, int]:
        return self._stats.copy()