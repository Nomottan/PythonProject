"""
Утилиты схожести для сравнения поставок.

Класс SimilarityUtils собирает в одном месте операции над
множествами ключевых слов и индексами кандидатов. Зависимостей
от моделей SupplyItem/Candidate нет — только set и dict, чтобы
модуль был тестируемым в изоляции.
"""
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.models import Candidate

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

class CompareReportTxtWriter:
    """Пишет txt-отчёты сравнения поставок.

    Роль:
        Единая точка записи «Не_найдено_{date}.txt» и
        «Лишние_в_поставках_{date}.txt». Оба метода — статические,
        без состояния. Если список пуст — файл не создаётся,
        возвращается None. Ошибки IO не глотаются: пусть вызывающий
        сам решает, писать в critical или пробросить.

    Формат:
        Заголовок + разделитель (60 знаков '=') + по строке на
        товар в виде «{name} (кол-во: {count})».
    """

    @staticmethod
    def write_not_found(output_dir: Path, items: list,
                        date_str: str) -> Path | None:
        """Пишет файл «Не_найдено_{date}.txt».

        Вход:
            output_dir — папка, куда писать.
            items — список SupplyItem без matched_candidate.
            date_str — дата в формате «Д_М_ГГГГ» (например, «28_9_2026»).

        Выход:
            Path к созданному файлу либо None, если items пуст
            (файл не создаётся).

        Роль:
            Точный перенос блока «2. Список не найденных» из
            ReportGenerator.generate. Формат строки сохранён.
        """
        if not items:
            return None

        output_dir = Path(output_dir)
        path = output_dir / f"Не_найдено_{date_str}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("Товары из листа поставки, не найденные в поставках:\n")
            f.write("=" * 60 + "\n")
            for item in items:
                f.write(f"{item.name} (кол-во: {item.count})\n")
        return path

    @staticmethod
    def write_unused(output_dir: Path, candidates: list,
                     date_str: str) -> Path | None:
        """Пишет файл «Лишние_в_поставках_{date}.txt».

        Вход:
            output_dir — папка, куда писать.
            candidates — список Candidate с used=False.
            date_str — дата в формате «Д_М_ГГГГ».

        Выход:
            Path к созданному файлу либо None, если candidates пуст.

        Роль:
            Точный перенос блока «3. Список лишних в поставках»
            из ReportGenerator.generate.
        """
        if not candidates:
            return None

        output_dir = Path(output_dir)
        path = output_dir / f"Лишние_в_поставках_{date_str}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("Товары из поставок, которых нет в листе (лишние):\n")
            f.write("=" * 60 + "\n")
            for c in candidates:
                f.write(f"{c.name} (кол-во: {c.count})\n")
        return path