"""
Утилиты заполнения цен в предитоговых файлах.

Класс PriceFiller — три этапа проставления цен:
    1. fill_from_report — точное совпадение по КИЗу (цены из отчёта МП).
    2. fill_by_gtin_clusters — распределение числовых цен внутри
       кластеров по GTIN.
    3. fill_by_average — генерация по средней для оставшихся нечисловых.

Класс FillStats — dataclass со статистикой второго этапа.

Роль в программе:
    Используется FinalizePricesService (Порция 15) вместо приватных
    методов _apply_stage1/2/3. Все методы — static: класс не хранит
    состояние и не зависит от TaskContext/LoggerV2.
"""

import random
from dataclasses import dataclass
from typing import Optional

from utils.parsers import NumberParser
from utils.price_utils import PriceUtils





@dataclass
class FillStats:
    """Статистика второго этапа заполнения цен.

    Роль:
        Возвращается методом PriceFiller.fill_by_gtin_clusters
        вместо сырого dict — с именованными полями и без опечаток
        в строковых ключах. Используется сервисом для логирования.

    Поля:
        total_clusters — всего кластеров GTIN, найденных в листе.
        processed — кластеров, в которых цены были распределены.
        skipped_no_numeric — кластеров без единой числовой цены
                             (их обработает этап 3).
        skipped_all_numeric — кластеров, где все цены уже числовые.
        filled_rows — сколько строк получили цену на этом этапе.
    """
    total_clusters: int
    processed: int
    skipped_no_numeric: int
    skipped_all_numeric: int
    filled_rows: int


class PriceFiller:
    """Три этапа заполнения цен в предитоговом файле.

    Роль:
        Каждый static-метод — отдельный этап. Порядок вызовов задаёт
        вызывающий код (FinalizePricesService): сначала этап 1 по
        отчёту, затем этап 2 по кластерам GTIN, затем этап 3 по средней.
        Класс не хранит состояние.

    Атрибуты класса:
        KIZ_COL — номер столбца КИЗ (B), 1-based, как в openpyxl.
        PRICE_COL — номер столбца цены (C), 1-based.
        GTIN_COL — номер столбца GTIN (H), 1-based.
        HEADER_KIZ — значение КИЗ-ячейки в шапке, которое
                     пропускается. Строки данных с таким значением
                     не встречаются.
    """

    KIZ_COL = 2
    PRICE_COL = 3
    GTIN_COL = 8
    HEADER_KIZ = "КИЗ"

    @staticmethod
    def fill_from_report(sheet, price_map: dict) -> int:
        """Этап 1: цены из отчёта по точному совпадению КИЗа.

        Вход:
            sheet — открытый лист openpyxl.
            price_map — dict {kiz: price} из отчёта МП.

        Выход:
            Количество установленных цен.

        Роль:
            Проходит по строкам листа. Пропускает строки без КИЗа
            и строку заголовка (значение == HEADER_KIZ). Если КИЗ
            строки есть в price_map — записывает цену в PRICE_COL.
            Если КИЗа нет — оставляет ячейку как есть (там может
            быть криптохвост от BestMark, его нельзя затирать).
        """
        count = 0
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=PriceFiller.KIZ_COL)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == PriceFiller.HEADER_KIZ:
                continue
            if kiz in price_map:
                sheet.cell(
                    row=row_idx, column=PriceFiller.PRICE_COL
                ).value = price_map[kiz]
                count += 1
        return count

    @staticmethod
    def fill_by_gtin_clusters(sheet,
                              rng: Optional[random.Random] = None) -> FillStats:
        """Этап 2: распределение цен внутри кластеров GTIN.

        Вход:
            sheet — открытый лист openpyxl.
            rng — опциональный random.Random для детерминированного
                  выбора. None — используется модуль random.

        Выход:
            FillStats со статистикой этапа.

        Роль:
            Строит кластеры {gtin: [row_indexes]}. Внутри кластера
            собирает числовые цены и строки с нечисловой ценой.
            Нечисловые строки заполняет случайной числовой ценой
            того же кластера. Кластеры без единой числовой цены
            пропускает — их обработает этап 3. Кластеры, где все
            цены уже числовые, тоже пропускает — делать нечего.
            Строки без GTIN в кластеры не попадают.
        """
        # Шаг 1: строим кластеры по GTIN.
        gtin_clusters: dict[str, list[int]] = {}
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=PriceFiller.KIZ_COL)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == PriceFiller.HEADER_KIZ:
                continue
            gtin_cell = sheet.cell(row=row_idx, column=PriceFiller.GTIN_COL)
            gtin = (
                str(gtin_cell.value).strip()
                if gtin_cell.value is not None else ""
            )
            if not gtin:
                continue
            gtin_clusters.setdefault(gtin, []).append(row_idx)

        # Шаг 2: обрабатываем кластеры.
        stats = FillStats(
            total_clusters=len(gtin_clusters),
            processed=0,
            skipped_no_numeric=0,
            skipped_all_numeric=0,
            filled_rows=0,
        )
        # Источник случайности. rng=None → модуль random.
        rng_obj = rng or random

        for _gtin, row_indexes in gtin_clusters.items():
            numeric_values = []
            non_numeric_rows = []
            for row_idx in row_indexes:
                price_cell = sheet.cell(
                    row=row_idx, column=PriceFiller.PRICE_COL
                )
                if NumberParser.is_numeric(price_cell.value):
                    numeric_values.append(price_cell.value)
                else:
                    non_numeric_rows.append(row_idx)

            # Нет числовых — распределять нечего, ждём этапа 3.
            if not numeric_values:
                stats.skipped_no_numeric += 1
                continue
            # Всё уже числовое — кластер готов.
            if not non_numeric_rows:
                stats.skipped_all_numeric += 1
                continue

            # Заполняем нечисловые строки случайной числовой ценой.
            for row_idx in non_numeric_rows:
                sheet.cell(
                    row=row_idx, column=PriceFiller.PRICE_COL
                ).value = rng_obj.choice(numeric_values)
                stats.filled_rows += 1
            stats.processed += 1

        return stats

    @staticmethod
    def fill_by_average(sheet, average_price: int,
                        rng: Optional[random.Random] = None) -> int:
        """Этап 3: генерация цен по средней для оставшихся нечисловых.

        Вход:
            sheet — открытый лист openpyxl.
            average_price — средняя цена для генерации.
            rng — опциональный random.Random для детерминированной
                  генерации. None — используется модуль random.

        Выход:
            Количество сгенерированных цен.

        Роль:
            Проходит по строкам. Пропускает строки без КИЗа и
            заголовок. Если цена нечисловая — генерирует по средней
            через PriceUtils.generate_varied_price. Сюда попадают
            строки без GTIN и кластеры, где числовых цен не было.
        """
        count = 0
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(row=row_idx, column=PriceFiller.KIZ_COL)
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == PriceFiller.HEADER_KIZ:
                continue
            price_cell = sheet.cell(
                row=row_idx, column=PriceFiller.PRICE_COL
            )
            if not NumberParser.is_numeric(price_cell.value):
                price_cell.value = PriceUtils.generate_varied_price(
                    average_price, rng=rng
                )
                count += 1
        return count