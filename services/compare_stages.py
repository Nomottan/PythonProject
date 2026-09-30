"""
Стадии сравнения поставок: Stage1, Stage2, Stage3.

Роль в программе:
    CompareService.run_stage1/2/3 создают стадии и прогоняют через
    них накопленное состояние. Диалоги с пользователем вынесены
    наружу — стадии не знают про Qt, вызывают callbacks, которые
    CompareWindow передаёт в конструктор CompareService.

Каналы логирования:
    logger.report  — пошаговый журнал стадии в log_сравнение.txt.
    logger.warning — предупреждения (пока не используется).
    Если logger is None — все сообщения молча пропускаются
    (для тестов без логирования).
"""

from typing import Optional

from models.models import SupplyItem, Candidate
from utils.similarity_utils import SimilarityUtils, CandidateIndexBuilder


class Stage1:
    """Жёсткая сверка: кандидат найден по ВСЕМ ключевым словам.

    Роль:
        Точный перенос логики Stage1.run из старого
        services/compare_service.py. Единственное отличие —
        вместо parent_widget и импорта Stage1ReviewDialog
        используется callback reviewer(pairs) -> list[bool].

    Контракт reviewer:
        pairs — список кортежей (SupplyItem, Candidate) — все
                найденные жёсткие пары.
        Возвращает список флагов той же длины: True — оставить пару,
        False — исключить (товар идёт в remaining).
        Если reviewer is None — все пары принимаются.
    """

    def __init__(self, logger=None, reviewer=None):
        """Конструктор.

        Вход:
            logger — LoggerV2 или None.
            reviewer — callable(pairs) -> list[bool] или None.
        """
        self._logger = logger
        self._reviewer = reviewer

    def run(self, items: list, candidates: list) -> tuple:
        """Запускает этап 1.

        Вход:
            items — список SupplyItem.
            candidates — список Candidate.

        Выход:
            (found, remaining, remaining_candidates):
                found — SupplyItem с item.stage == 1.
                remaining — SupplyItem без пары.
                remaining_candidates — исходный список Candidate
                                       (used-флаги обновлены).

        Роль:
            Строит индексы, для каждого товара пересекает индексы
            ключевых слов, фильтрует по count, отсеивает used.
            Если ровно один кандидат — пара, иначе — в remaining.
            Собранные пары отдаёт reviewer, применяет флаги,
            помечает item и candidate.
        """
        if self._logger is not None:
            self._logger.report("=== ЭТАП 1: ЖЁСТКАЯ СВЕРКА ===")

        keyword_index = CandidateIndexBuilder.build_keyword_index(candidates)
        count_index = CandidateIndexBuilder.build_count_index(candidates)

        found_pairs: list = []           # (item, candidate), ещё без used
        remaining: list = []
        remaining_candidates = candidates.copy()

        for item in items:
            if not item.keywords:
                if self._logger is not None:
                    self._logger.report(
                        f"  Товар '{item.name}' не имеет ключевых слов — пропускаем"
                    )
                remaining.append(item)
                continue

            candidate_indices = SimilarityUtils.intersect_candidates(
                item.keywords, keyword_index,
            )
            if not candidate_indices:
                remaining.append(item)
                continue

            candidate_indices = SimilarityUtils.count_filter(
                candidate_indices, count_index, item.count,
            )
            if not candidate_indices:
                remaining.append(item)
                continue

            candidate_indices = {
                idx for idx in candidate_indices
                if not remaining_candidates[idx].used
            }

            if len(candidate_indices) == 1:
                idx = next(iter(candidate_indices))
                found_pairs.append((item, remaining_candidates[idx]))
            else:
                remaining.append(item)

        # Диалог с пользователем — через callback.
        keep_flags: list
        if found_pairs and self._reviewer is not None:
            keep_flags = self._reviewer(found_pairs)
        else:
            keep_flags = [True] * len(found_pairs)

        found: list = []
        for i, (item, candidate) in enumerate(found_pairs):
            if keep_flags[i]:
                candidate.used = True
                item.found = True
                item.matched_candidate = candidate
                item.stage = 1
                found.append(item)
                if self._logger is not None:
                    self._logger.report(
                        f"  Жёсткое совпадение подтверждено: "
                        f"'{item.name}' ↔ '{candidate.name}'"
                    )
            else:
                if self._logger is not None:
                    self._logger.report(
                        f"  Жёсткое совпадение исключено: "
                        f"'{item.name}' ↔ '{candidate.name}'"
                    )
                remaining.append(item)

        if self._logger is not None:
            self._logger.report(f"Найдено жёстких совпадений: {len(found)}")
            self._logger.report(f"Осталось товаров: {len(remaining)}")
        return found, remaining, remaining_candidates


class Stage2:
    """Мягкая сверка: кандидат с Жаккаром >= порога.

    Роль:
        Точный перенос Stage2.run. Вместо parent_widget и
        ConfirmMatchDialog — callback
        confirmer(item, candidate, score, remaining) -> bool.

    Контракт confirmer:
        item — SupplyItem, для которого нашли кандидата.
        candidate — Candidate.
        score — float, схожесть.
        remaining — сколько товаров осталось обработать (включая
                    текущий).
        Возвращает True — подтвердить пару, False — отклонить.
        Если confirmer is None — все пары подтверждаются.
    """

    # Порог схожести. Вынесен из тела метода, чтобы не «магическое число».
    SIMILARITY_THRESHOLD = 0.7

    def __init__(self, logger=None, confirmer=None):
        """Конструктор.

        Вход:
            logger — LoggerV2 или None.
            confirmer — callable(item, cand, score, remaining) -> bool
                        или None.
        """
        self._logger = logger
        self._confirmer = confirmer

    def run(self, items: list, candidates: list) -> tuple:
        """Запускает этап 2.

        Вход:
            items — список SupplyItem.
            candidates — список Candidate.

        Выход:
            (found, remaining, remaining_candidates).
        """
        if self._logger is not None:
            self._logger.report(
                "=== ЭТАП 2: МЯГКАЯ СВЕРКА (ЖАККАР >= 0.7) ==="
            )

        found: list = []
        remaining: list = []
        remaining_candidates = candidates.copy()
        total = len(items)
        processed = 0

        for item in items:
            processed += 1
            if not item.keywords:
                remaining.append(item)
                continue

            scored: list = []
            for idx, cand in enumerate(remaining_candidates):
                if cand.used:
                    continue
                if item.count is not None and cand.count != item.count:
                    continue
                if not cand.keywords:
                    continue
                score = SimilarityUtils.jaccard(item.keywords, cand.keywords)
                if score >= Stage2.SIMILARITY_THRESHOLD:
                    scored.append((idx, score))

            if not scored:
                remaining.append(item)
                continue

            scored.sort(key=lambda x: x[1], reverse=True)
            best_idx, best_score = scored[0]

            if len(scored) > 1 and scored[1][1] >= Stage2.SIMILARITY_THRESHOLD:
                # Есть второй столь же похожий — не рискуем, в следующий этап.
                remaining.append(item)
                continue

            cand = remaining_candidates[best_idx]

            # Диалог — через callback.
            if self._confirmer is not None:
                confirmed = self._confirmer(
                    item, cand, best_score, total - processed + 1,
                )
            else:
                confirmed = True

            if confirmed:
                cand.used = True
                item.found = True
                item.matched_candidate = cand
                item.stage = 2
                found.append(item)
                if self._logger is not None:
                    self._logger.report(
                        f"  Мягкое совпадение подтверждено: "
                        f"'{item.name}' ↔ '{cand.name}' "
                        f"(Жаккар: {best_score:.2f})"
                    )
            else:
                remaining.append(item)

        if self._logger is not None:
            self._logger.report(f"Найдено мягких совпадений: {len(found)}")
            self._logger.report(
                f"Осталось товаров для этапа 3: {len(remaining)}"
            )
        return found, remaining, remaining_candidates


class Stage3:
    """Ручной выбор: пользователь сам сопоставляет оставшихся.

    Роль:
        Точный перенос Stage3.run. Вместо parent_widget и
        ManualMatchDialog — callback
        selector(item, candidates, remaining) -> (Candidate | None, bool).

    Контракт selector:
        item — SupplyItem.
        candidates — список Candidate, ещё доступных (не used).
        remaining — сколько товаров в очереди, включая текущий.
        Возвращает (candidate, skip_all):
            candidate — выбранный Candidate или None.
            skip_all — True, если пользователь нажал «Отложить»
                       (товар вернётся в очередь).
        Если selector is None — товар пропускается (candidate=None,
        skip_all=False).
    """

    def __init__(self, logger=None, selector=None):
        """Конструктор.

        Вход:
            logger — LoggerV2 или None.
            selector — callable(item, candidates, remaining)
                       -> (Candidate | None, bool) или None.
        """
        self._logger = logger
        self._selector = selector

    def run(self, items: list, candidates: list) -> list:
        """Запускает этап 3.

        Вход:
            items — SupplyItem, не сопоставленные ранее.
            candidates — список Candidate.

        Выход:
            list[SupplyItem] — все товары, прошедшие через этап,
            с проставленным found/stage/matched_candidate.

        Роль:
            Очередь current + deferred. Пока что-то есть — берём
            первый товар, вызываем selector. При выборе — фиксируем
            пару, при skip_all — в deferred (вернётся после того,
            как кончится current), иначе — пропуск.
        """
        if self._logger is not None:
            self._logger.report("=== ЭТАП 3: РУЧНОЙ ВЫБОР ===")

        remaining_candidates = [c for c in candidates if not c.used]
        all_items: list = []

        current_items = items.copy()
        deferred_items: list = []

        while current_items or deferred_items:
            if not current_items:
                current_items = deferred_items
                deferred_items = []
                if self._logger is not None:
                    self._logger.report("Переход к отложенным товарам...")
                continue

            item = current_items.pop(0)

            if not remaining_candidates:
                if self._logger is not None:
                    self._logger.report(
                        f"Товар '{item.name}': нет доступных кандидатов, "
                        f"пропускаем."
                    )
                item.found = False
                item.stage = 0
                all_items.append(item)
                continue

            if self._selector is None:
                # Нет callback — пропуск без диалога.
                item.found = False
                item.stage = 0
                all_items.append(item)
                continue

            selected_candidate, skip_all = self._selector(
                item, remaining_candidates,
                len(current_items) + len(deferred_items) + 1,
            )

            if selected_candidate is not None:
                matched_cand: Optional[Candidate] = None
                for c in remaining_candidates:
                    if (c.name == selected_candidate['name']
                            and c.count == selected_candidate.get('count')):
                        matched_cand = c
                        break
                if matched_cand is not None:
                    remaining_candidates.remove(matched_cand)
                    matched_cand.used = True
                    item.found = True
                    item.matched_candidate = matched_cand
                    item.stage = 3
                    if self._logger is not None:
                        self._logger.report(
                            f"  Ручное сопоставление: "
                            f"'{item.name}' ↔ '{matched_cand.name}'"
                        )
                else:
                    item.found = False
                    item.stage = 0
                all_items.append(item)
            else:
                if skip_all:
                    if self._logger is not None:
                        self._logger.report(f"  Товар отложен: '{item.name}'")
                    deferred_items.append(item)
                else:
                    if self._logger is not None:
                        self._logger.report(f"  Товар пропущен: '{item.name}'")
                    item.found = False
                    item.stage = 0
                    all_items.append(item)

        unused = [c for c in remaining_candidates if not c.used]
        if unused and self._logger is not None:
            self._logger.report(
                f"Неиспользованных кандидатов (лишние в поставках): "
                f"{len(unused)}"
            )

        if self._logger is not None:
            self._logger.report("Этап 3 завершён.")
        return all_items