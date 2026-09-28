"""
Построители индексов кандидатов для сравнения поставок.

Класс CandidateIndexBuilder собирает индексы «ключ → список
индексов кандидатов». Индексы нужны Stage1 для быстрого поиска
пересечений через SimilarityUtils.intersect_candidates.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.models import Candidate


class CandidateIndexBuilder:
    """Строит индексы кандидатов по ключевым словам и количеству.

    Роль:
        Единая точка построения индексов для Stage1. Логика
        перенесена из Stage1.run без изменений — там эти же
        циклы выполнялись inline.

    Контракты:
        - На вход — список Candidate (объекты с .keywords: set[str]
          и .count: int | None).
        - На выход — dict с индексами 0..len(candidates)-1.
        - Исключений не бросает.
    """

    @staticmethod
    def build_keyword_index(candidates: list) -> dict:
        """Строит индекс {keyword: [индексы кандидатов]}.

        Вход:
            candidates — список Candidate.

        Выход:
            dict[str, list[int]]: по каждому ключевому слову —
            список позиций кандидатов в исходном списке,
            у которых это слово встречается.

        Роль:
            Индекс для первого шага Stage1: быстро найти кандидатов,
            покрывающих все ключевые слова товара. Кандидаты с
            пустыми keywords пропускаются молча — их не с чем
            сопоставлять.
        """
        keyword_index: dict[str, list[int]] = {}
        for idx, cand in enumerate(candidates):
            for word in cand.keywords:
                keyword_index.setdefault(word, []).append(idx)
        return keyword_index

    @staticmethod
    def build_count_index(candidates: list) -> dict:
        """Строит индекс {count: [индексы кандидатов]}.

        Вход:
            candidates — список Candidate.

        Выход:
            dict[int, list[int]]: по каждому значению count — список
            позиций кандидатов с этим count.

        Роль:
            Индекс для второго шага Stage1 (фильтр по количеству).
            Кандидаты без count (count is None) пропускаются — их
            нельзя сопоставить по количеству, они остаются только
            в keyword_index.
        """
        count_index: dict[int, list[int]] = {}
        for idx, cand in enumerate(candidates):
            if cand.count is not None:
                count_index.setdefault(cand.count, []).append(idx)
        return count_index