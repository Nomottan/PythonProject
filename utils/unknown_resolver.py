"""
Маршрутизация решений по неизвестным именам (брендам и продавцам).

Содержит:
    ResolverAction           — dataclass одного действия в резолвере.
    ResolverRouter           — статические методы применения решений.
    build_brand_actions      — actions для разрешения брендов.
    build_seller_actions     — actions для разрешения продавцов.
    build_decisions_from_result — маппинг result → decisions.

Роль в программе:
    Единая точка "что делать с решением пользователя". Окно
    UnknownResolverDialog собирает result, ResolverRouter
    применяет его к моделям через сервис. Никакой UI-логики здесь нет.
"""

from dataclasses import dataclass
from typing import Any, Callable

from utils.text_utils import TextUtils


@dataclass
class ResolverAction:
    """Одно действие, доступное пользователю в резолвере.

    Поля:
        key — идентификатор действия ("match", "add_key", "existing",
              "new").
        label — текст кнопки в диалоге.
        handler — Callable[[norm_key, raws], Any]. Возвращает value
                  для последующего apply. Если вернуть нельзя —
                  бросает ValueError, окно покажет уведомление и
                  останется на текущем объекте.
        apply — Callable[[value, norm_key, raws], bool]. Применяет
                value к модели. True — успех, False — не удалось.
    """
    key: str
    label: str
    handler: Callable[[str, list], Any]
    apply: Callable[[Any, str, list], bool]


class ResolverRouter:
    """Маршрутизация решений по actions.

    Роль:
        apply_result — обход result и применение action.apply к
        каждому значению. group_by_normalized — сборка items из
        списка сырых строк для передачи в диалог.
    """

    @staticmethod
    def apply_result(result, actions, items, logger=None) -> dict:
        """Применяет result через actions.

        Вход:
            result — dict[action_key, dict[norm_key, value]].
            actions — list[ResolverAction].
            items — dict[norm_key, list[str]] — нужен для
                    action.apply(value, norm_key, raws).
            logger — LoggerV2 | None.

        Выход:
            dict {"total", "resolved", "skipped"}.

        Роль:
            Для каждого action в result находит ResolverAction по key
            и вызывает action.apply(value, norm_key, raws). Если
            action_key нет в actions — все решения этого ключа
            считаются skipped, в лог — warning.
        """
        total = len(items)
        resolved = 0
        skipped = 0
        action_by_key = {a.key: a for a in actions}

        for action_key, decisions in result.items():
            action = action_by_key.get(action_key)
            if action is None:
                if logger is not None:
                    logger.warning(
                        f"apply_result: неизвестный action "
                        f"'{action_key}' — пропущено {len(decisions)}"
                    )
                skipped += len(decisions)
                continue

            for norm_key, value in decisions.items():
                raws = items.get(norm_key, [])
                ok = action.apply(value, norm_key, raws)
                if ok:
                    resolved += 1
                else:
                    skipped += 1

        return {"total": total, "resolved": resolved, "skipped": skipped}

    @staticmethod
    def group_by_normalized(raws) -> dict:
        """Группирует сырые строки по нормализованному ключу.

        Вход:
            raws — итерируемое сырых строк.

        Выход:
            dict {norm_key: [raw, ...]}. Если несколько raw дают
            один нормализованный ключ — все попадают в список.

        Роль:
            Утилита для сборки items перед созданием диалога.
            Нормализация — через TextUtils.normalize.
        """
        result: dict = {}
        for raw in raws:
            norm = TextUtils.normalize(raw)
            result.setdefault(norm, []).append(raw)
        return result

    @staticmethod
    def build_brand_actions(service, pick_brand_cb, edit_brand_cb) -> list:
        """Собирает actions для разрешения брендов.

        Вход:
            service — SellersBrandsService.
            pick_brand_cb — handler для «Существующий»: возвращает Brand.
            edit_brand_cb — handler для «Новый»: возвращает Brand.

        Выход:
            list[ResolverAction] с двумя действиями.

        Роль:
            «Существующий» — привязывает сырой ключ к выбранному бренду
            через add_key_to_brand. «Новый» — создаёт бренд через
            create_brand с ключами и флагом requires_saving.
        """
        return [
            ResolverAction(
                key="existing",
                label="Существующий",
                handler=pick_brand_cb,
                apply=lambda brand, nk, raws: service.add_key_to_brand(
                    brand.name, raws[0],
                ),
            ),
            ResolverAction(
                key="new",
                label="Новый",
                handler=edit_brand_cb,
                apply=lambda brand, nk, raws: service.create_brand(
                    brand.name, brand.keys, brand.requires_saving,
                ),
            ),
        ]

    @staticmethod
    def build_seller_actions(service, pick_seller_with_special_cb,
                             pick_seller_no_special_cb) -> list:
        """Собирает actions для разрешения продавцов.

        Вход:
            service — SellersBrandsService.
            pick_seller_with_special_cb — handler для «Соотнести».
            pick_seller_no_special_cb — handler для «Добавить ключ».

        Выход:
            list[ResolverAction] с двумя действиями.

        Роль:
            «match» — value ∈ {seller.name, "garbage", "unknown",
            "returns"}. Решение всегда валидное (True), запись в
            decisions идёт через build_decisions_from_result.
            «add_key» — value = seller.name без спец. Ключ пишется
            через service.add_key_to_seller; спец-значения запрещены
            (False).
        """
        _SPECIAL = {"garbage", "unknown", "returns"}

        def _apply_match(value, nk, raws):
            return True

        def _apply_add_key(value, nk, raws):
            if value in _SPECIAL:
                return False
            return service.add_key_to_seller(value, raws[0])

        return [
            ResolverAction(
                key="match",
                label="Соотнести",
                handler=pick_seller_with_special_cb,
                apply=_apply_match,
            ),
            ResolverAction(
                key="add_key",
                label="Добавить ключ",
                handler=pick_seller_no_special_cb,
                apply=_apply_add_key,
            ),
        ]

    @staticmethod
    def build_decisions_from_result(result, context_map) -> dict:
        """Собирает {norm_key: (kind, target)} из result.

        Вход:
            result — dict[action_key, dict[norm_key, value]].
            context_map — dict[norm_key, set[str]] — множество
                          контекстов {"mp", "wh"}. В логике не
                          используется; нужен вызывающему для
                          группировки и get_label.

        Выход:
            dict {norm_key: (kind, target)},
            kind ∈ {"seller", "garbage", "unknown", "returns"},
            target — имя продавца или None.

        Роль:
            Преобразует пользовательские решения в формат, который
            понимает PreparationService._copy_wb_file /
            _copy_ozon_file / WarehouseReportWriter.write.
        """
        decisions = {}
        for action_key, items in result.items():
            for norm_key, value in items.items():
                if action_key == "match":
                    if value in ("garbage", "unknown", "returns"):
                        decisions[norm_key] = (value, None)
                    else:
                        decisions[norm_key] = ("seller", value)
                elif action_key == "add_key":
                    decisions[norm_key] = ("seller", value)
        return decisions