from pathlib import Path
from typing import Tuple, List, Optional

from utils.run_manager import RunManager
from utils.logger import ILogger
from utils.text_utils import TextUtils


class ConditionChecker:
    """
    Содержит методы проверки условий для каждого процесса.
    Возвращает кортеж (bool, str) — успешно и причина.
    """

    def __init__(
        self,
        run_manager: RunManager,
        config_manager,
        process_type: str,
        logger: ILogger
    ):
        self.run_manager = run_manager
        self.config_manager = config_manager
        self.process_type = process_type  # "chz", "returns", "compare"
        self.logger = logger
        self.work_folder = run_manager.get_work_folder()

    # ------------------------------------------------------------
    # Общие проверки
    # ------------------------------------------------------------
    def _folder_has_files(self, pattern: str) -> bool:
        """Проверяет, есть ли в рабочей папке файлы по шаблону."""
        return any(self.work_folder.glob(pattern))

    def _folder_has_files_for_sellers(self, sellers, pattern_template: str) -> bool:
        """Проверяет, есть ли для каждого продавца файл по шаблону."""
        for seller in sellers:
            pattern = pattern_template.format(seller.name)
            if not any(self.work_folder.glob(pattern)):
                return False
        return True

    # ------------------------------------------------------------
    # ЧЗ МП
    # ------------------------------------------------------------
    def can_export_kiz_chz(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Выгрузка для обработки'."""
        if self._folder_has_files("ЧЗ_МП_*.xlsx"):
            return True, ""
        return False, "Нет файлов ЧЗ МП в рабочей папке. Сначала выполните подготовку."

    def can_filter_prefinal_chz(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Сбор данных'."""
        if self._folder_has_files("ОТЧЁТ МП ПО *.xlsx"):
            return True, ""
        return False, "Нет файлов отчётов МП в рабочей папке. Сначала выполните выгрузку."

    def can_generate_sales_chz(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Продажи'."""
        sellers = self.config_manager.get_sellers_objects()
        if not sellers:
            return False, "Нет продавцов в конфигурации"
        # Проверяем наличие файлов {seller}.xlsx после фильтрации
        if self._folder_has_files_for_sellers(sellers, "{}*.xlsx"):
            return True, ""
        return False, "Нет файлов продавцов для обработки. Сначала выполните сбор данных."

    def can_finalize_prices_chz(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Установка цен'."""
        if self._folder_has_files("ИТОГ *.xlsx"):
            return True, ""
        return False, "Нет итоговых файлов. Сначала выполните формирование продаж."

    # ------------------------------------------------------------
    # Возвраты
    # ------------------------------------------------------------
    def can_export_kiz_returns(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Выгрузить КИЗы для возврата'."""
        if self._folder_has_files("Возвраты_*.xlsx"):
            return True, ""
        return False, "Нет файла Возвраты в рабочей папке. Сначала выполните подготовку."

    def can_prepare_transfer_returns(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Подготовить КИЗы для передачи'."""
        # Проверяем наличие текстовых файлов с КИЗами (создаются после выгрузки)
        if self._folder_has_files("*.txt"):
            return True, ""
        return False, "Нет файлов с КИЗами. Сначала выполните выгрузку."

    # ------------------------------------------------------------
    # Сравнение
    # ------------------------------------------------------------
    def can_stage1_compare(self) -> Tuple[bool, str]:
        """Проверка для этапа 1 (после подготовки)."""
        if self._folder_has_files("Лист_поставки_копия_*.xlsx") and \
           self._folder_has_files("Сборный_поставок_*.xlsx"):
            return True, ""
        return False, "Нет подготовленных файлов. Сначала выполните подготовку."

    def can_stage2_compare(self) -> Tuple[bool, str]:
        """Проверка для этапа 2 (после этапа 1)."""
        # Проверяем, что есть файл отчёта этапа 1 (или его можно определить по наличию)
        # Для простоты проверяем наличие любого файла отчёта
        if self._folder_has_files("Отчёт_сравнения_*.xlsx"):
            return True, ""
        return False, "Нет отчёта этапа 1. Сначала выполните этап 1."

    def can_stage3_compare(self) -> Tuple[bool, str]:
        """Проверка для этапа 3 (после этапа 2)."""
        # Аналогично, проверяем наличие отчёта
        if self._folder_has_files("Отчёт_сравнения_*.xlsx"):
            return True, ""
        return False, "Нет отчёта этапа 2. Сначала выполните этап 2."

    def can_report_compare(self) -> Tuple[bool, str]:
        """Проверка для кнопки 'Сформировать отчёт'."""
        if self._folder_has_files("Лист_поставки_копия_*.xlsx") and \
           self._folder_has_files("Сборный_поставок_*.xlsx"):
            return True, ""
        return False, "Нет подготовленных файлов. Сначала выполните подготовку."