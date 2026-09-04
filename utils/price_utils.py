import random
from typing import Optional, List


class PriceUtils:
    @staticmethod
    def calculate_average(saved_price: Optional[int], prices_list: List[int]) -> Optional[int]:
        if not prices_list:
            return None
        if saved_price is not None:
            new_avg = (saved_price * 100 + sum(prices_list)) / (100 + len(prices_list))
        else:
            new_avg = sum(prices_list) / len(prices_list)
        return int(new_avg)

    @staticmethod
    def generate_varied_price(base_price: int) -> int:
        low = max(1, int(base_price * 0.9))
        high = int(base_price * 1.1) + 1
        if low >= high:
            raw = max(1, int(base_price))
        else:
            raw = random.randint(low, high)
        return ((raw + 9) // 9) * 9