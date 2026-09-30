import random
from dataclasses import dataclass
from typing import Optional, List
from utils.parsers import NumberParser

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
        сигнал «нужен диалог». Порядок источников фиксирован
        и повторяет текущее поведение FinalizePricesService.
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
        calculate_average — средняя с учётом сохранённой цены.
        generate_varied_price — случайная цена в коридоре ±10%
        от базовой, округлённая до кратного 9.

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