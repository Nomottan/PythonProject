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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.subservices.logging import LogManagerV2


class KizFilterDetailsWriter:
    """Пишет детальный лог фильтрации КИЗов при аккумуляции продаж.

    Роль:
        Единая точка записи log_фильтрация_КИЗов.txt. Создаёт
        отдельный LoggerV2 через переданный LogManagerV2 — так
        структура лога совпадает с основным log_аккумуляция.txt
        (те же префиксы [ts] [SEVERITY] [source]). Сохраняет
        заголовки, отступы и порядок сортировки из прежней версии
        SalesAccumulatorService._log_kiz_details.
    """

    @staticmethod
    def write(details: dict, logs_dir, log_manager_v2) -> None:
        """Пишет детальный лог фильтрации КИЗов.

        Вход:
            details — словарь {"kiz_from_fbs": set[str],
                               "files": [{"name": str,
                                          "total": int,
                                          "duplicates": set[str],
                                          "filtered": set[str]}, ...]}.
            logs_dir — папка «Логи» рабочей папки.
            log_manager_v2 — LogManagerV2 для создания логгера.

        Выход: нет.

        Роль:
            Создаёт логгер SalesAccumulatorService.kiz_filter с
            именем log_фильтрация_КИЗов.txt и построчно пишет
            структуру. Пустые строки и разделители сохранены —
            лог читается глазами, как и раньше.
        """
        logger = log_manager_v2.create_logger_v2(
            source="SalesAccumulatorService.kiz_filter",
            domain="sales",
            work_folder=logs_dir,
            log_filename="log_фильтрация_КИЗов.txt",
        )

        logger.report("=== ДЕТАЛИ ФИЛЬТРАЦИИ КИЗОВ ===")
        logger.report("")
        logger.report("КИЗы из ЧЗ_МП (приоритетные):")
        if details["kiz_from_fbs"]:
            for kiz in sorted(details["kiz_from_fbs"]):
                logger.report(f"  {kiz}")
        else:
            logger.report("  (нет)")
        logger.report("")
        logger.report("=" * 60)
        logger.report("")

        for file_info in details["files"]:
            logger.report(f"Файл: {file_info['name']}")
            logger.report(
                f"  Всего КИЗов в файле: {file_info['total']}"
            )
            logger.report(
                f"  Дубликаты (уже есть в ЧЗ_МП): "
                f"{len(file_info['duplicates'])}"
            )
            if file_info["duplicates"]:
                for kiz in sorted(file_info["duplicates"]):
                    logger.report(f"    {kiz}")
            else:
                logger.report("    (нет)")
            logger.report(
                f"  Отфильтрованные (добавлены): "
                f"{len(file_info['filtered'])}"
            )
            if file_info["filtered"]:
                for kiz in sorted(file_info["filtered"]):
                    logger.report(f"    {kiz}")
            else:
                logger.report("    (нет)")
            logger.report("")
            logger.report("-" * 40)