from pathlib import Path
from datetime import datetime
from typing import Any

from pathlib import Path
from datetime import datetime
from typing import Any, Optional, Dict, List, Tuple


class LogTemplates:
    """
    Шаблоны для структурированного логирования.
    Все методы статические, принимают логгер и необходимые параметры.
    """

    # ============================================================
    # БАЗОВЫЕ ШАБЛОНЫ (универсальные)
    # ============================================================

    @staticmethod
    def task_start(logger, task_name: str, source_file: str = "", work_folder: str = ""):
        """Начало задачи: возвраты, ЧЗ МП, сравнение."""
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        logger.info(f"=== {task_name} начата {now} ===")
        if source_file:
            logger.info(f"Исходный файл: {source_file}")
        if work_folder:
            logger.info(f"Рабочая папка: {work_folder}")

    @staticmethod
    def task_end(logger, task_name: str):
        """Завершение задачи."""
        logger.info(f"=== {task_name} завершена ===")

    @staticmethod
    def section(logger, title: str, char: str = "=", length: int = 60):
        """Разделитель с заголовком."""
        logger.info(char * length)
        logger.info(f"{char} {title} {char}")
        logger.info(char * length)

    @staticmethod
    def error(logger, msg: str):
        """Вывод ошибки."""
        logger.error(f"Ошибка: {msg}")

    @staticmethod
    def warning(logger, msg: str):
        """Вывод предупреждения."""
        logger.warning(msg)

    @staticmethod
    def log_statistics(logger, title: str, data: dict, sort_keys: bool = True):
        """Универсальный вывод статистики из словаря."""
        if not data:
            logger.info(f"{title}: Нет данных")
            return
        logger.info(title)
        keys = sorted(data.keys(), key=lambda x: str(x).lower()) if sort_keys else data.keys()
        for key in keys:
            logger.info(f"  {key}: {data[key]}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ ОТЧЁТОВ О РЕЗУЛЬТАТАХ ОБРАБОТКИ
    # ============================================================

    @staticmethod
    def report_results(
        logger,
        rows_copied: int,
        rows_skipped: int,
        file_type: str = "",
        filename: str = "",
        extra: str = "",
        log_file_info: bool = True
    ):
        """
        Универсальный отчёт о результатах обработки.
        Если указан file_type и filename — выводит информацию о созданном файле.
        """
        if file_type and filename and log_file_info:
            logger.info(f"Создан файл с {file_type}: {filename}")

        logger.report(f"Скопировано строк: {rows_copied}")
        logger.report(f"Пропущено строк: {rows_skipped}")

        if extra:
            logger.report(extra)

    # Обёртки для обратной совместимости
    @staticmethod
    def report_processing_result(logger, rows_copied: int, rows_skipped: int, extra: str = ""):
        """Отчёт о количестве обработанных строк (обёртка)."""
        LogTemplates.report_results(logger, rows_copied, rows_skipped, extra=extra, log_file_info=False)

    @staticmethod
    def report_file_created(logger, file_type: str, filename: str, rows_copied: int, rows_skipped: int):
        """Создан файл с результатами (обёртка)."""
        LogTemplates.report_results(logger, rows_copied, rows_skipped, file_type, filename)

    # ============================================================
    # ШАБЛОНЫ ДЛЯ СТАТИСТИКИ ПРОДАЖ
    # ============================================================

    @staticmethod
    def sales_statistics(
        logger,
        stats: Dict[Tuple[str, str], int],
        files_created: int,
        title: str = "СТАТИСТИКА ПРОДАЖ",
        label: str = "КИЗов"
    ):
        """
        Универсальный вывод статистики продаж.
        stats — словарь вида {(от_кого, кому): количество}.
        """
        logger.info(f"\n--- {title} ---")
        if stats:
            for (from_seller, to_seller), count in sorted(stats.items()):
                logger.info(f"  {from_seller} → {to_seller}: {count} {label}")
        else:
            logger.info("  Нет строк для передачи между продавцами")
        logger.info(f"Создано файлов продаж: {files_created}")

    # Обёртка для обратной совместимости
    @staticmethod
    def transfer_preparation_result(logger, sales_stats: dict, files_created: int):
        """Результат подготовки передач КИЗов (обёртка)."""
        LogTemplates.sales_statistics(logger, sales_stats, files_created, title="СТАТИСТИКА ПРОДАЖ")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ ОБРАБОТКИ ФАЙЛОВ
    # ============================================================

    @staticmethod
    def processing_item(logger, item_type: str, filename: str, seller_name: str = None, count: int = None):
        """
        Универсальный шаблон обработки элемента (файла, листа).
        item_type — "ЧЗ_МП", "отчёт МП", "лист" и т.п.
        """
        logger.info(f"\nОбработка {item_type}: {filename}")
        if seller_name and count is not None:
            if item_type.lower() == "чз_мп":
                logger.info(f"  Лист '{filename}' → продавец '{seller_name}': добавлено {count} КИЗов")
            else:
                logger.info(f"  Добавлено {count} КИЗов для продавца '{seller_name}'")

    # Обёртки для обратной совместимости
    @staticmethod
    def processing_chz_file(logger, filename: str, seller_name: str = None, count: int = None):
        """Обработка файла ЧЗ МП (обёртка)."""
        LogTemplates.processing_item(logger, "ЧЗ_МП", filename, seller_name, count)

    @staticmethod
    def processing_mp_report(logger, filename: str, seller_name: str = None, count: int = None):
        """Обработка отчёта МП (обёртка)."""
        LogTemplates.processing_item(logger, "отчёт МП", filename, seller_name, count)

    @staticmethod
    def processing_seller_sheet(logger, seller_name: str, sheet_name: str, count: int, action: str = "Лист"):
        """Обработка листа продавца (ЧЗ МП)."""
        logger.info(f"  {action} '{sheet_name}' → продавец '{seller_name}': добавлено {count} КИЗов")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ СОХРАНЕНИЯ ФАЙЛОВ
    # ============================================================

    @staticmethod
    def save_summary(
        logger,
        what: str,
        count: int,
        filename: str = "",
        corrupted: int = 0,
        show_filename: bool = True
    ):
        """
        Универсальный вывод информации о сохранении.
        what — "КИЗов", "товаров", "строк" и т.п.
        """
        if corrupted > 0:
            logger.info(f"  {what}: сохранено {count} (пропущено {corrupted} некорректных)")
        elif filename and show_filename:
            logger.info(f"  {what}: сохранено {count} в {filename}")
        else:
            logger.info(f"  {what}: сохранено {count}")

    # Обёртки для обратной совместимости
    @staticmethod
    def saved_kiz_file(logger, seller_name: str, count: int, filename: str):
        """Сохранён текстовый файл с КИЗами (обёртка)."""
        LogTemplates.save_summary(logger, f"{seller_name} КИЗов", count, filename)

    @staticmethod
    def saved_count(logger, what: str, count: int, filename: str = ""):
        """Вывод количества сохранённых записей (обёртка)."""
        LogTemplates.save_summary(logger, what, count, filename)

    @staticmethod
    def loaded_count(logger, what: str, count: int):
        """Вывод количества загруженных записей."""
        logger.info(f"Загружено {what}: {count}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ ЭТАПОВ СРАВНЕНИЯ
    # ============================================================

    @staticmethod
    def stage_result(logger, stage_num: int, stage_name: str, found: int, remaining: int):
        """Результат этапа сравнения."""
        logger.info(f"Найдено {stage_name} совпадений: {found}")
        logger.info(f"Осталось товаров для следующих этапов: {remaining}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ РАБОТЫ С ФАЙЛАМИ (копирование, пропуск)
    # ============================================================

    @staticmethod
    def file_copied(logger, source: str, target: str, extra: str = ""):
        """Файл скопирован."""
        logger.info(f"Скопирован {source} → {target}")
        if extra:
            logger.info(extra)

    @staticmethod
    def file_skipped(logger, filename: str, reason: str):
        """Файл пропущен."""
        logger.info(f"  Пропущен {filename}: {reason}")

    @staticmethod
    def accumulation_result(logger, copied: int, skipped: int, merged: int):
        """Результат аккумуляции продаж."""
        logger.report(f"Скопировано файлов: {copied}")
        logger.report(f"Пропущено файлов: {skipped}")
        logger.report(f"Объединено файлов: {merged}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ НЕИЗВЕСТНЫХ СУЩНОСТЕЙ
    # ============================================================

    @staticmethod
    def unknown_entities(logger, unknown_dict, log_path, title, ctx):
        """Логирование неизвестных сущностей (компании, бренды)."""
        if not unknown_dict:
            return
        sorted_unknown = sorted(unknown_dict.keys(), key=str.lower)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(title + "\n")
            f.write("=" * 50 + "\n")
            for entity in sorted_unknown:
                f.write(f"{entity}: {unknown_dict[entity]}\n")
        logger.info(f"Список неизвестных сущностей сохранён в {log_path.name}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ ФИЛЬТРАЦИИ И ЦЕН
    # ============================================================

    @staticmethod
    def filtering_file(logger, filename: str, total_rows: int, kept_rows: int,
                       status_stats: dict = None, owner_stats: dict = None):
        """Статистика фильтрации файла."""
        logger.info(f"\nОбработка файла: {filename}")
        logger.info(f"  Всего строк: {total_rows}")
        if status_stats:
            logger.info("  Удалено по статусу:")
            for status, count in sorted(status_stats.items(), key=lambda x: x[0].lower()):
                logger.info(f"    Статус '{status}': {count} строк")
        if owner_stats:
            logger.info("  Удалено по владельцу:")
            for owner, count in sorted(owner_stats.items(), key=lambda x: x[0].lower()):
                logger.info(f"    Владелец '{owner}': {count} строк")
        logger.info(f"  Сохранено: {kept_rows} строк")

    @staticmethod
    def price_finalization(logger, seller_name: str, from_report: int, generated: int, avg_price: int):
        """Статистика установки цен."""
        logger.info(f"\nОбработка файла для продавца '{seller_name}'")
        logger.info(f"  Установлено цен из отчёта: {from_report}")
        logger.info(f"  Сгенерировано цен по средней: {generated}")
        logger.info(f"  Средняя цена: {avg_price}")

    # ============================================================
    # ШАБЛОНЫ ДЛЯ УПРАВЛЕНИЯ СОСТОЯНИЯМИ И ПРОГОНАМИ
    # ============================================================

    @staticmethod
    def run_archived(logger, run_number: int, archive_path: Path):
        """Архивация прогона."""
        logger.info(f"Архивация прогона #{run_number} в {archive_path}")

    @staticmethod
    def state_changed(logger, step_id: str, old_state: str, new_state: str):
        """Изменение состояния кнопки."""
        logger.debug(f"Состояние кнопки '{step_id}': {old_state} → {new_state}")

    @staticmethod
    def condition_failed(logger, step_id: str, reason: str):
        """Условие не выполнено."""
        logger.warning(f"Условие для '{step_id}' не выполнено: {reason}")

    @staticmethod
    def service_started(logger, step_id: str):
        """Запуск сервиса."""
        logger.info(f"Запуск сервиса для шага: {step_id}")

    @staticmethod
    def service_finished(logger, step_id: str, success: bool, error: str = ""):
        """Завершение сервиса."""
        if success:
            logger.info(f"Сервис для шага '{step_id}' успешно завершён")
        else:
            logger.error(f"Сервис для шага '{step_id}' завершился с ошибкой: {error}")

    @staticmethod
    def state_restored(logger, step_id: str):
        """Восстановление состояния."""
        logger.info(f"Восстановлено состояние для шага: {step_id}")

    @staticmethod
    def process_reset(logger, process_name: str):
        """Сброс процесса."""
        logger.info(f"Процесс '{process_name}' сброшен")
