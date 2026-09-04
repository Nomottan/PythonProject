# ui/instructions/compare_instruction.py
from pathlib import Path
from typing import Tuple

from utils.run_manager import RunManager
from services.compare_service import CompareService


class CompareInstruction:
    """Инструкции для процесса Сравнения поставок."""

    @staticmethod
    def can_prepare(run_manager: RunManager, supply_file: str, supply_files: list) -> Tuple[bool, str]:
        """Подготовка активна только если выбран лист поставки и хотя бы один файл поставки."""
        if not supply_file:
            return False, "Файл листа поставки не выбран."
        if not supply_files:
            return False, "Не добавлены файлы поставок."
        return True, ""

    @staticmethod
    def can_stage1(service: CompareService) -> Tuple[bool, str]:
        """
        Этап 1 активен если данные загружены (supply_items и candidates не пусты).
        Блокируется если хоть один из словарей пуст.
        """
        if not service.supply_items:
            return False, "Нет товаров для сверки. Сначала выполните подготовку."
        if not service.candidates:
            return False, "Нет кандидатов для сверки. Сначала выполните подготовку."
        return True, ""

    @staticmethod
    def can_stage2(service: CompareService) -> Tuple[bool, str]:
        """
        Этап 2 активен если пройден этап 1 (found_stage1 не пуст) и есть остаток товаров/кандидатов.
        Блокируется если хоть один из словарей пуст.
        """
        if not service.supply_items:
            return False, "Нет товаров для мягкой сверки. Все товары уже найдены."
        if not service.candidates:
            return False, "Нет кандидатов для мягкой сверки."
        if not service.found_stage1:
            # Если этап 1 не был запущен или ничего не нашёл, но товары есть — всё равно пускаем?
            # По логике: если found_stage1 пуст, но товары есть — значит этап1 не дал совпадений, но это не блокирует этап2.
            # Поэтому проверяем только наличие словарей.
            pass
        return True, ""

    @staticmethod
    def can_stage3(service: CompareService) -> Tuple[bool, str]:
        """
        Этап 3 активен если либо пройден этап 2 (found_stage2 не пуст), либо этап2 пропущен из-за отсутствия мягких сверок,
        и при этом есть остаток товаров/кандидатов. Не блокируется для повторного прохождения.
        Блокируется только если словари пусты.
        """
        if not service.supply_items:
            return False, "Нет товаров для ручного выбора."
        if not service.candidates:
            return False, "Нет кандидатов для ручного выбора."
        # Если этап2 не выполнен, но товары есть — разрешаем, т.к. этап2 мог пропустить из-за отсутствия совпадений.
        return True, ""

    @staticmethod
    def can_report(service: CompareService) -> Tuple[bool, str]:
        """
        Отчёт активен если пройден этап 3 (final_items не пуст) ИЛИ все товары уже найдены (supply_items пуст).
        """
        if service.final_items:
            return True, ""
        if not service.supply_items:
            # Все товары найдены на предыдущих этапах
            return True, ""
        return False, "Нет данных для отчёта. Сначала выполните все этапы."