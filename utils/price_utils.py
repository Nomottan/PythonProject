import random
from dataclasses import dataclass
from typing import Optional, List

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