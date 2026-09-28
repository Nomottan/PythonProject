"""
Утилиты схожести для сравнения поставок.

Класс SimilarityUtils собирает в одном месте операции над
множествами ключевых слов и индексами кандидатов. Зависимостей
от моделей SupplyItem/Candidate нет — только set и dict, чтобы
модуль был тестируемым в изоляции.
"""


class SimilarityUtils:
    """Статические операции схожести и фильтрации индексов.

    Роль:
        Единая точка для арифметики сравнения. Stage1 (жёсткая
        сверка) использует intersect_candidates + count_filter,
        Stage2 — jaccard. Всё — чистые функции без состояния.

    Контракты:
        - Все методы принимают примитивы (set, dict, int).
        - Исключений не бросают: на некорректных данных возвращают
          безопасный результат (пустое множество или 0.0).
    """

    @staticmethod
    def jaccard(set1: set, set2: set) -> float:
        """Считает коэффициент Жаккара для двух множеств.

        Вход:
            set1, set2 — множества ключевых слов.

        Выход:
            float: |A ∩ B| / |A ∪ B|.
            Если объединение пустое — 0.0.

        Роль:
            Мера схожести в Stage2. Порог 0.7 задаётся вызывающим
            (Stage2.SIMILARITY_THRESHOLD), здесь только арифметика.
        """
        union = len(set1 | set2)
        if union == 0:
            return 0.0
        return len(set1 & set2) / union

    @staticmethod
    def intersect_candidates(item_keywords: set,
                             keyword_index: dict) -> set:
        """Возвращает индексы кандидатов, у которых есть ВСЕ ключевые слова.

        Вход:
            item_keywords — множество ключевых слов товара.
            keyword_index — dict {keyword: [idx, ...]}.

        Выход:
            set[int] — пересечение списков индексов по каждому
            ключевому слову. Пустое множество, если хотя бы одного
            слова нет в индексе.

        Роль:
            Первый шаг Stage1: сузить пул кандидатов до тех, кто
            покрывает все ключевые слова товара. Точный перенос
            цикла пересечения из Stage1.run.
        """
        if not item_keywords:
            return set()

        result = None
        for word in item_keywords:
            indices = keyword_index.get(word, [])
            if not indices:
                return set()
            if result is None:
                result = set(indices)
            else:
                result.intersection_update(indices)
        return result if result is not None else set()

    @staticmethod
    def count_filter(candidate_indices: set,
                     count_index: dict,
                     item_count: int | None) -> set:
        """Оставляет только кандидатов с совпадающим count.

        Вход:
            candidate_indices — множество индексов кандидатов.
            count_index — dict {count: [idx, ...]}.
            item_count — количество у товара или None.

        Выход:
            set[int] — подмножество candidate_indices, индексы
            которых присутствуют в count_index[item_count].
            Если item_count is None — возвращается вход без
            фильтрации (фильтр по количеству не применяется).

        Роль:
            Второй шаг Stage1: отсеять кандидатов с другим
            количеством упаковки. Точный перенос блока
            «Фильтр по количеству» из Stage1.run.
        """
        if item_count is None:
            return set(candidate_indices)
        allowed = set(count_index.get(item_count, []))
        return set(candidate_indices) & allowed