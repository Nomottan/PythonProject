"""
Ядро фильтрации: FieldDef и FilterCore.

Чистая логика — без Qt, без логгера, без побочных эффектов.
UI-слой (FilterPanel / FilterCategory) собирает предикаты и
передаёт их сюда через apply.

Роль в программе:
    Единая точка построения предикатов, применения фильтра и
    сбора значений для чекбоксов. Один FieldDef описывает поле
    фильтра, FilterCore — как из набора FieldDef собрать
    отфильтрованный список объектов.
"""

from dataclasses import dataclass
from typing import Callable

@dataclass
class FieldDef:
    """Описание одного поля фильтра.

    Поля:
        name — идентификатор поля (используется как ключ в selected).
        label — подпись в UI.
        extractor — Callable[[T], Any]. Возвращает скаляр или
                    список/кортеж/set.
        values_provider — Callable[[list[T]], list] | None.
                          Возвращает список значений для чекбоксов.
                          None → ядро соберёт через extractor.
        custom_predicate — Callable[[T, set], bool] | None.
                           Зарезервировано на будущее. В текущей
                           версии не используется.
    """
    name: str
    label: str
    extractor: Callable
    values_provider: Callable | None = None
    custom_predicate: Callable | None = None

class FilterCore:
    """Статические методы ядра фильтрации.

    Роль:
        Собирает предикат одной категории (OR внутри), применяет
        набор предикатов к списку объектов (AND между), собирает
        уникальные значения поля для UI-чекбоксов.

    Контракты:
        Все методы — static. Исключений не бросают: на невалидном
        входе возвращают нейтральный результат.
    """

    @staticmethod
    def build_predicate(field_def: FieldDef,
                        selected: set) -> Callable:
        """Строит предикат одной категории.

        Вход:
            field_def — FieldDef.
            selected — множество выбранных значений в этой категории.

        Выход:
            Callable[[T], bool]. Если selected пусто — предикат
            всегда возвращает True (категория не активна).
            Иначе — объект проходит, если его значение (или хотя
            бы один элемент, если значение — список/кортеж/set)
            входит в selected.

        Роль:
            OR внутри одной категории. AND между категориями
            обеспечивает apply.
        """
        if not selected:
            return lambda obj: True

        def _predicate(obj):
            value = field_def.extractor(obj)
            if isinstance(value, (list, tuple, set)):
                return any(v in selected for v in value)
            return value in selected

        return _predicate

    @staticmethod
    def apply(objects: list, predicates: list) -> list:
        """Применяет список предикатов к списку объектов.

        Вход:
            objects — исходный список.
            predicates — список Callable[[T], bool].

        Выход:
            list — объекты, для которых все предикаты вернули True.
            При пустом predicates — копия исходного списка.

        Роль:
            AND между предикатами. Порядок сохраняется как в
            исходном списке.
        """
        if not predicates:
            return list(objects)
        return [obj for obj in objects if all(p(obj) for p in predicates)]

    @staticmethod
    def collect_values(objects: list, field_def: FieldDef) -> list:
        """Собирает уникальные значения поля для UI-чекбоксов.

        Вход:
            objects — список объектов для обхода.
            field_def — FieldDef.

        Выход:
            list — уникальные значения в порядке первого появления,
            отсортированные. При несравнимых типах — сортировка
            по str.

        Роль:
            Если задан values_provider — берёт значения из него.
            Иначе проходит по объектам через extractor и разворачивает
            списки/кортежи/set в скаляры. Дедуп по значению —
            сохраняет порядок первого появления, потом сортирует.
        """
        if field_def.values_provider is not None:
            raw = field_def.values_provider(objects)
        else:
            raw = []
            for obj in objects:
                v = field_def.extractor(obj)
                if isinstance(v, (list, tuple, set)):
                    raw.extend(v)
                else:
                    raw.append(v)

        unique = []
        seen = set()
        for v in raw:
            if v in seen:
                continue
            seen.add(v)
            unique.append(v)

        try:
            return sorted(unique)
        except TypeError:
            return sorted(unique, key=str)