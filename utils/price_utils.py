import random
from dataclasses import dataclass
from typing import Optional, List
from utils.parsers import NumberParser
from utils.kiz_utils import KizUtils

@dataclass
class PriceDecision:
    """Решение о средней цене для продавца.

    Роль:
        Возвращается AveragePriceResolver.resolve. Заменяет
        пару «значение + неявный флаг» возвратом одного объекта
        с явным флагом need_dialog.

    Поля:
        price — выбранная средняя цена или None, если нужно
                спросить пользователя.
        need_dialog — True, если ни один источник цены не подошёл
                      и сервис должен открыть диалог ввода.
    """
    price: Optional[int]
    need_dialog: bool


class AveragePriceResolver:
    """Выбор средней цены для продавца из доступных источников.

    Роль:
        Инкапсулирует if/elif-лестницу определения средней.
        Возвращает PriceDecision — либо конкретную цену, либо
        сигнал «нужен диалог». Порядок источников фиксирован:
        цены из отчёта → сохранённая цена текущего продавца →
        случайная средняя с другого → диалог.
    """

    @staticmethod
    def resolve(saved_prices: dict, seller_name: str,
                prices_list: List[int]) -> PriceDecision:
        """Определяет среднюю цену для продавца.

        Вход:
            saved_prices — dict {seller_name: средняя цена},
                           ранее сохранённые значения.
            seller_name — имя текущего продавца.
            prices_list — список цен из отчёта МП для текущего
                          продавца. Может быть пустым.

        Выход:
            PriceDecision. need_dialog=True только в случае, когда
            ни цен из отчёта, ни сохранённых цен вообще нет.

        Роль:
            Четыре ветки:
            1. Есть цены из отчёта → считаем среднюю через
               PriceUtils.calculate_average с учётом сохранённой.
            2. Цен из отчёта нет, но есть сохранённая у текущего
               продавца → берём её.
            3. Ничего нет у текущего, но есть сохранённые у других
               → случайная из их значений.
            4. Совсем пусто → need_dialog=True.
        """
        # Ветка 1: есть цены из отчёта.
        if prices_list:
            avg = PriceUtils.calculate_average(
                saved_prices.get(seller_name), prices_list
            )
            return PriceDecision(price=avg, need_dialog=False)

        # Ветка 2: сохранённая цена текущего продавца.
        saved = saved_prices.get(seller_name)
        if saved:
            return PriceDecision(price=saved, need_dialog=False)

        # Ветка 3: случайная средняя с другого продавца.
        if saved_prices:
            other = random.choice(list(saved_prices.values()))
            return PriceDecision(price=other, need_dialog=False)

        # Ветка 4: спросить пользователя.
        return PriceDecision(price=None, need_dialog=True)


class PriceUtils:
    """Утилиты расчёта и генерации цен.

    Роль:
        Каждый static-метод — отдельный этап. Порядок вызовов задаёт
        вызывающий код: этапы 1 (по отчёту), 2 (по кластерам GTIN),
        3 (по средней) выполняются последовательно. Метод
        apply_price_from_map — отдельная точка для установки цены
        по точному совпадению КИЗа в строке (values) без открытия sheet.
        Класс не хранит состояние.

    Атрибуты класса:
        SAVED_PRICE_WEIGHT — вес сохранённой цены при расчёте средней.
                             Смысл: сохранённая пользователем цена
                             «увереннее» одной строки из отчёта,
                             поэтому в формуле она учитывается как
                             это число виртуальных наблюдений.
    """

    SAVED_PRICE_WEIGHT = 500

    @staticmethod
    def calculate_average(saved_price: Optional[int],
                          prices_list: List[int]) -> Optional[int]:
        """Считает среднюю цену с учётом сохранённой.

        Вход:
            saved_price — сохранённая цена продавца или None.
            prices_list — список цен из отчёта. Непустой
                          (проверку делает вызывающий код).

        Выход:
            int — средняя. None, если prices_list пуст.

        Роль:
            Если сохранённая цена задана и положительна — она
            учитывается с весом SAVED_PRICE_WEIGHT. Иначе — простая
            средняя по prices_list. Нулевая или отрицательная
            сохранённая цена игнорируется: такие значения —
            следствие ошибочного ввода, а не валидная цена.
        """
        if not prices_list:
            return None
        if saved_price is not None and saved_price > 0:
            weight = PriceUtils.SAVED_PRICE_WEIGHT
            new_avg = (
                saved_price * weight + sum(prices_list)
            ) / (weight + len(prices_list))
        else:
            new_avg = sum(prices_list) / len(prices_list)
        return int(new_avg)

    @staticmethod
    def generate_varied_price(base_price: int,
                              rng: Optional[random.Random] = None) -> int:
        """Генерирует цену в коридоре ±10% от базовой.

        Вход:
            base_price — базовая цена.
            rng — опциональный random.Random для детерминированного
                  выбора. None — используется модуль random.

        Выход:
            int — сгенерированная цена, кратная 9.

        Роль:
            Коридор [0.9 * base, 1.1 * base]. Результат округляется
            вверх до ближайшего кратного 9. Если коридор вырожден
            (низ >= верх) — берётся сама base.
        """
        low = max(1, int(base_price * 0.9))
        high = int(base_price * 1.1) + 1
        if low >= high:
            raw = max(1, int(base_price))
        else:
            raw = (rng or random).randint(low, high)
        return ((raw + 9) // 9) * 9

@dataclass
class FillStats:
    """Статистика второго этапа заполнения цен (по GTIN из price_map).

    Поля:
        total_gtins_in_prices — уникальных GTIN в price_map (для
                                которых удалось извлечь из КИЗа).
        filled_rows — строк получили цену на этом этапе.
        unique_gtins_filled — уникальных GTIN, для которых этап 2
                              поставил хотя бы одну цену (не считая
                              строк, у которых цена уже стояла).
        skipped_already_priced — строк с ценой до этапа 2.
        skipped_no_gtin — строк без цены и без GTIN.
        skipped_not_in_prices — строк без цены, чей GTIN отсутствует
                                в price_map.
        unique_gtins_not_in_prices — уникальных GTIN среди
                                     skipped_not_in_prices.
    """
    total_gtins_in_prices: int
    filled_rows: int
    unique_gtins_filled: int
    skipped_already_priced: int
    skipped_no_gtin: int
    skipped_not_in_prices: int
    unique_gtins_not_in_prices: int


# NEW: перенесено из utils/price_filler.py — PriceFiller.
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
    def apply_price_from_map(values: list, price_map: dict) -> bool:
        """Устанавливает цену по точному совпадению КИЗа без открытия sheet.

        Вход:
            values    — список значений строки openpyxl.
            price_map — dict {kiz: price} из отчёта МП.

        Выход:
            bool — True, если цена была установлена (мутирует values in-place).

        Роль:
            Выполняет проверки на наличие КИЗа в строке, его валидность и
            наличие в price_map. В случае успеха расширяет строку до
            нужной длины (при необходимости) и записывает цену.
        """
        if len(values) < PriceFiller.KIZ_COL:
            return False

        raw_kiz = values[PriceFiller.KIZ_COL - 1]
        kiz = str(raw_kiz).strip() if raw_kiz is not None else ""

        if not kiz or kiz == PriceFiller.HEADER_KIZ:
            return False

        if kiz not in price_map:
            return False

        if len(values) < PriceFiller.PRICE_COL:
            values.extend([None] * (PriceFiller.PRICE_COL - len(values)))

        values[PriceFiller.PRICE_COL - 1] = price_map[kiz]
        return True

    @staticmethod
    def fill_by_gtin_clusters(sheet, price_map: dict,
                              rng: Optional[random.Random] = None,
                              *, logger=None) -> FillStats:
        """Этап 2: распределение цен по GTIN из price_map.

        Вход:
            sheet — открытый лист openpyxl.
            price_map — dict {kiz: price} из отчёта МП. Источник цен.
            rng — опциональный random.Random. None → модуль random.
            logger — LoggerV2 или None. Keyword-only. Используется
                     для warning при пропущенных коротких КИЗах.

        Выход:
            FillStats со статистикой этапа.

        Роль:
            Строит gtin_to_prices {gtin: [prices]} из price_map через
            KizUtils.extract_gtin. Проходит по строкам файла. Строки
            без цены и с GTIN, которого нет в price_map, — в
            skipped_not_in_prices. Строки без цены и с GTIN в
            price_map — получают случайную цену из gtin_to_prices
            (или единственную, если она одна). Строки с уже стоящей
            ценой — skipped_already_priced. Строки без GTIN —
            skipped_no_gtin.

            Этап 3 (fill_by_average) после этого метода добьёт
            оставшиеся нечисловые: и skipped_no_gtin, и
            skipped_not_in_prices.
        """
        # Шаг 1. Построение gtin_to_prices.
        gtin_to_prices: dict = {}
        short_kiz_count = 0
        for kiz, price in price_map.items():
            gtin = KizUtils.extract_gtin(kiz)
            if not gtin:
                short_kiz_count += 1
                continue
            gtin_to_prices.setdefault(gtin, []).append(price)

        if short_kiz_count > 0 and logger is not None:
            logger.warning(
                f"price_map: {short_kiz_count} КИЗов короче 16 символов, "
                f"GTIN не извлечён, пропущены"
            )

        # Шаг 2. Инициализация.
        stats = FillStats(
            total_gtins_in_prices=len(gtin_to_prices),
            filled_rows=0,
            unique_gtins_filled=0,
            skipped_already_priced=0,
            skipped_no_gtin=0,
            skipped_not_in_prices=0,
            unique_gtins_not_in_prices=0,
        )
        gtins_filled: set = set()
        gtins_not_in_prices: set = set()
        rng_obj = rng or random

        # Шаг 3. Проход по строкам.
        for row_idx in range(2, sheet.max_row + 1):
            kiz_cell = sheet.cell(
                row=row_idx, column=PriceFiller.KIZ_COL,
            )
            kiz = (
                str(kiz_cell.value).strip()
                if kiz_cell.value is not None else ""
            )
            if not kiz or kiz == PriceFiller.HEADER_KIZ:
                continue

            price_cell = sheet.cell(
                row=row_idx, column=PriceFiller.PRICE_COL,
            )
            if NumberParser.is_numeric(price_cell.value):
                stats.skipped_already_priced += 1
                continue

            gtin_cell = sheet.cell(
                row=row_idx, column=PriceFiller.GTIN_COL,
            )
            gtin = (
                str(gtin_cell.value).strip()
                if gtin_cell.value is not None else ""
            )
            if not gtin:
                stats.skipped_no_gtin += 1
                continue

            if gtin not in gtin_to_prices:
                stats.skipped_not_in_prices += 1
                gtins_not_in_prices.add(gtin)
                continue

            price_cell.value = rng_obj.choice(gtin_to_prices[gtin])
            stats.filled_rows += 1
            gtins_filled.add(gtin)

        # Шаг 4. Финализация и возврат.
        stats.unique_gtins_filled = len(gtins_filled)
        stats.unique_gtins_not_in_prices = len(gtins_not_in_prices)
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