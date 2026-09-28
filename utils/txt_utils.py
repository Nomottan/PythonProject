"""
Утилиты записи txt-отчётов сравнения поставок.

Класс CompareReportTxtWriter собирает в одном месте запись
вспомогательных списков: «товары, не найденные в поставках» и
«товары из поставок, которых нет в листе». Формат файлов совпадает
с прежним ReportGenerator.generate — этот модуль переносит ту же
логику без изменений.
"""

from pathlib import Path
from datetime import date


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