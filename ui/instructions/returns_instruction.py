# ui/instructions/returns_instruction.py
from pathlib import Path
from typing import Tuple

from utils.run_manager import RunManager


class ReturnsInstruction:
    """Инструкции для процесса Возвратов."""

    @staticmethod
    def can_prepare(source_file: str) -> Tuple[bool, str]:
        """Проверяет, выбран ли исходный файл."""
        if not source_file:
            return False, "Файл возвратов не выбран."
        return True, ""

    @staticmethod
    def can_export_kiz(run_manager: RunManager) -> Tuple[bool, str]:
        """Проверяет, что подготовка выполнена (есть файл Возвраты_*.xlsx)."""
        work_folder = run_manager.get_work_folder()
        files = list(work_folder.glob("Возвраты_*.xlsx"))
        if files:
            return True, ""
        return False, "Нет файла Возвраты. Сначала выполните подготовку."

    @staticmethod
    def can_prepare_transfer(run_manager: RunManager) -> Tuple[bool, str]:
        """Проверяет то же самое (подготовка выполнена)."""
        work_folder = run_manager.get_work_folder()
        files = list(work_folder.glob("Возвраты_*.xlsx"))
        if files:
            return True, ""
        return False, "Нет файла Возвраты. Сначала выполните подготовку."