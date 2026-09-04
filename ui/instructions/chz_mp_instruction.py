from typing import List, Tuple

from utils.run_manager import RunManager


class ChzMPInstruction:
    """Инструкции для процесса ЧЗ МП."""

    @staticmethod
    def can_prepare(run_manager: RunManager, fbs_files: list, mp_files: list) -> Tuple[bool, str]:
        if not fbs_files and not mp_files:
            return False, "Выберите файлы ЧЗ МП или отчёты МП."
        return True, ""

    @staticmethod
    def can_export_kiz(run_manager: RunManager) -> Tuple[bool, str]:
        work_folder = run_manager.get_work_folder()
        files = list(work_folder.glob("ЧЗ_МП_*.xlsx"))
        if files:
            return True, ""
        return False, "Нет файлов ЧЗ МП. Сначала выполните подготовку."

    @staticmethod
    def can_filter_prefinal(run_manager: RunManager, sellers: List) -> Tuple[bool, str]:
        if not sellers:
            return False, "Нет продавцов в конфигурации."
        work_folder = run_manager.get_work_folder()
        for seller in sellers:
            if not any(work_folder.glob(f"{seller.name}.xlsx")):
                return False, f"Нет файла {seller.name}.xlsx. Сначала создайте его из текстового файла."
        return True, ""

    @staticmethod
    def can_generate_sales(run_manager: RunManager, sellers: List) -> Tuple[bool, str]:
        if not sellers:
            return False, "Нет продавцов в конфигурации."
        work_folder = run_manager.get_work_folder()
        for seller in sellers:
            if not any(work_folder.glob(f"{seller.name}.xlsx")):
                return False, f"Нет файла {seller.name}.xlsx. Сначала выполните сбор данных."
        return True, ""

    @staticmethod
    def can_finalize_prices(run_manager: RunManager, sellers: List) -> Tuple[bool, str]:
        if not sellers:
            return False, "Нет продавцов в конфигурации."
        work_folder = run_manager.get_work_folder()
        for seller in sellers:
            if not any(work_folder.glob(f"{seller.name}.xlsx")):
                return False, f"Нет файла {seller.name}.xlsx. Сначала выполните сбор данных."
        return True, ""