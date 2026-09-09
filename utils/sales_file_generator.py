from pathlib import Path
from typing import List, Dict, Optional
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils


import random
from pathlib import Path
from typing import List, Dict, Optional
from utils.excel_helper import ExcelHelper
from utils.text_utils import TextUtils


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
                     kiz_short: str,
                     price: Optional[int] = None) -> Path:
        """
        Добавляет строку продажи в файл.
        :param from_seller_name: продавец, от которого передаётся КИЗ (для имени файла)
        :param to_seller_name: продавец, которому передаётся КИЗ (для имени файла)
        :param to_seller_inn: ИНН принимающего продавца (для имени файла и не используется в данных)
        :param product_name: наименование продукта
        :param kiz_short: сокращённый КИЗ (31 символов)
        :param price: цена (если None, генерируется случайно от 10 до 20)
        :return: путь к созданному/обновлённому файлу
        """
        safe_from = TextUtils.sanitize_filename(from_seller_name)
        safe_to = TextUtils.sanitize_filename(to_seller_name)
        file_name = f"{safe_from} - {safe_to} : {to_seller_inn}.xlsx"
        file_path = self.work_folder / file_name

        if price is None:
            price = random.randint(10, 20)

        # GTIN – символы с 3 по 16 (индексы 2..15) если длина >= 16
        gtin = kiz_short[2:16] if len(kiz_short) >= 16 else ""

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