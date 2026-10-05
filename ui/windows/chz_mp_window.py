"""
Окно «Списание проданных КИЗов» (ЧЗ МП).

Назначение:
    Пайплайн из пяти шагов: подготовка файлов, выгрузка КИЗов,
    фильтрация предитоговых файлов, формирование продаж, установка
    цен и финализация. Плюс операция аккумуляции продаж — в базовом
    классе.

Роль в программе:
    Открывается из MainWindow. Наследник BaseServiceWindow:
    set_status/set_info/_precheck_target_dir/closeEvent/
    on_accumulate_sales — унаследованы. Окно отвечает за раскладку,
    обработчики шагов и специфику ввода средней цены.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout,
)

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
    ListWidgetFactory,
)
from ui.styles import ColorCalculator
from ui.widgets.path_selector import PathSelector
from ui.windows.shared_dialogs import (
    PricesEditWindow, AveragePriceInputDialog, BrandsUnknownDialog,
    SaleDuplicatePickerDialog,
)
from services.sells_fbs_service import (
    PreparationService, ExportKizService,
    FilterPreFinalService, GenerateSalesService, FinalizePricesService,
)
from utils.log_tools.decorators import log_button_action


class ChzMPWindow(BaseServiceWindow):
    """Окно пайплайна ЧЗ МП.

    Роль:
        Объединяет шаги обработки КИЗов. Каждый шаг — отдельный
        сервис, запускается в фоновом потоке через
        BaseServiceWindow._run_async_step. Логи шагов идут в
        status_log; короткие подсказки — в status_label.
    """

    LOGGER_SOURCE = "ChzMPWindow.chz_mp_window"
    LOGGER_DOMAIN = "chz_mp"

    # BG_COLOR: r, g+g//5, 2b-b//5 от (50,50,50) → (50, 60, 90).
    BG_COLOR = ColorCalculator.derive(
        (50, 50, 50),
        r_fn=lambda r: r,
        g_fn=lambda g: g + g // 5,
        b_fn=lambda b: 2 * b - b // 5,
    )

    PIPELINE_BUTTONS = (
        "btn_prepare",
        "btn_export_kiz",
        "btn_filter_prefinal",
        "btn_generate_sales",
        "btn_finalize_prices",
        "btn_fbs",
        "btn_reports",
    )

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: строит раскладку и подключает сигналы.
        """
        super().__init__(
            parent,
            title="Списание проданных КИЗов",
            log_manager_v2=log_manager_v2,
        )

        # Специфичное состояние для диалога средней цены.
        self._price_response: int | None = None

        # ---------- КНОПКИ-ИНДИКАТОРЫ ----------
        _indicator_configs = [
            ("btn_fbs", "Отчёты с FBS", (30, 20, 35, 0.3)),
            ("btn_reports", "Отчёты с МП", (30, 20, 35, 0.3)),
        ]
        ButtonFactory.create_buttons_from_config(self, _indicator_configs)

        # ---------- СПИСКИ ФАЙЛОВ (с крестиками) ----------
        self.list_fbs = ListWidgetFactory.create_file_list_widget(
            self,
            fixed_width=105,
            bg_color=(30, 20, 35, 0.3),
            text_color=None,
            font_size=10,
        )
        self.list_reports = ListWidgetFactory.create_file_list_widget(
            self,
            fixed_width=105,
            bg_color=(30, 20, 35, 0.3),
            text_color=None,
            font_size=10,
        )

        # ---------- ОПИСАНИЕ ----------
        self.desc_label = LabelFactory.create_label(
            self,
            text=(
                "Подготовка отчётов по продавцам для вывода КИЗов из оборота\n"
                "Загрузи файлы и отчёты выше\n"
                "Шаг 1: Нажми Подготовка. Файлы будут скопированы в рабочую директорию, оригиналы будут нетронуты\n"
                "Шаг 2: Нажми Выгрузка для обработки. Будут созданы текстовые файлы\n"
                "Проведи все файлы через BestMark в Excell файлы сохранив названия\n"
                "Шаг 3: Нажми Сбор данных. Файлы будут очищены от некорректных статусов и владельцев\n"
                "Шаг 4: Нажми Продажи. Будут собраны файлы для продаж продавцам не их КИЗов\n"
                "Проведи продажи через ЭДО\n"
                "Шаг 5: Нажми установка Цен.\n"
                "Будут использованы цены из Отчётов МП, а остальные заполняться случайным ценами от средней\n"
                "После выводи их из оборота"
            ),
            bg_color=(0, 0, 0, 0),
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )

        # ---------- ВЫБОР ПАПКИ ----------
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку",
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        # ---------- КНОПКИ ДЕЙСТВИЙ ----------
        _action_configs = [
            ("btn_prepare",         "Подготовка",             (80, 90, 120),  "8px 16px", (180, 35)),
            ("btn_export_kiz",      "Выгрузка для обработки", (70, 100, 120), "8px 16px", (180, 35)),
            ("btn_filter_prefinal", "Сбор данных",            (60, 110, 120), "8px 16px", (180, 35)),
            ("btn_generate_sales",  "Продажи",                (50, 120, 120), "8px 16px", (180, 35)),
            ("btn_finalize_prices", "Установка цен",          (40, 130, 120), "8px 16px", (180, 35)),
            ("btn_prices",          "Цены",                   (40, 40, 40),   "2px 2px",  (35, 20)),
        ]
        _action_handlers = {
            "btn_prepare":          "on_prepare",
            "btn_export_kiz":       "on_export_kiz",
            "btn_filter_prefinal":  "on_filter_prefinal",
            "btn_generate_sales":   "on_generate_sales",
            "btn_finalize_prices":  "on_finalize_prices",
            "btn_prices":           "on_open_prices_window",
        }
        ButtonFactory.create_buttons_from_config(
            self, _action_configs, _action_handlers,
        )

        # Все кнопки шагов изначально отключены, кроме подготовки.
        self.btn_export_kiz.setEnabled(False)
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)

        # ---------- МАКЕТ ----------
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        headers_container = LayoutFactory.create_row(
            self, self.btn_fbs, self.btn_reports, fixed_width=365,
        )
        center_layout.addWidget(headers_container, alignment=Qt.AlignCenter)

        lists_container = LayoutFactory.create_row(
            self, self.list_fbs, self.list_reports, fixed_width=365,
        )
        center_layout.addWidget(lists_container, alignment=Qt.AlignCenter)

        center_layout.addWidget(self.desc_label)
        center_layout.addWidget(self.path_selector)
        center_layout.addWidget(self.status_label)

        row1 = LayoutFactory.create_row(
            self, self.btn_prepare, self.btn_export_kiz,
            self.btn_filter_prefinal, spacing=8,
        )
        center_layout.addWidget(row1)

        row2 = LayoutFactory.create_row(
            self, self.btn_generate_sales, self.btn_finalize_prices,
            self.btn_prices, spacing=8,
        )
        center_layout.addWidget(row2)

        center_layout.addWidget(self.status_log)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35),
        )
        # on_accumulate_sales унаследован от BaseServiceWindow.
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)

        center_layout.addStretch(1)
        self.main_layout.addLayout(center_layout)

        # Подключение индикаторов к выбору файлов.
        self.btn_fbs.clicked.connect(self.select_fbs_files)
        self.btn_reports.clicked.connect(self.select_report_files)

        if self.logger:
            self.logger.debug("ChzMPWindow.__init__: окно инициализировано")

    # ============================================================
    # ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _on_target_dir_changed_hook(self) -> None:
        """Сброс кнопок шагов 2–5 при смене папки.

        Вход: нет.
        Выход: нет.
        Роль: базовый _on_target_dir_changed уже очистил status_log
              и обновил target_dir; здесь — только сброс кнопок.
        """
        self.btn_export_kiz.setEnabled(False)
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)

    def _current_sellers(self) -> list:
        """Возвращает продавцов с восстановленными связями Brand.

        Вход: нет.
        Выход: list[Seller] с заполненным .brands.

        Роль:
            Override базового _current_sellers. Для шага
            «Сбор данных» нужны продавцы с полной информацией
            о брендах — иначе filter_files не соберёт маппинг
            «ключ бренда → Brand».
        """
        return (
            self.main_window.sellers_brands_service
            .get_sellers_with_brands()
        )

    def cleanup(self) -> None:
        """Сброс списков файлов при закрытии окна."""
        self.list_fbs.clear_files()
        self.list_reports.clear_files()

    # ============================================================
    # ВЫБОР ФАЙЛОВ
    # ============================================================

    @log_button_action("btn_fbs", "Ошибка при выборе файлов ЧЗ МП: {e}")
    def select_fbs_files(self) -> None:
        """Открывает диалог выбора файлов ЧЗ МП.

        Роль: тонкая обёртка над _select_multiple_files. Файлы
              добавляются в list_fbs через FileListWidget.add_file.
        """
        self._select_multiple_files(
            config_key="last_fbs_dir",
            title="Выберите файлы ЧЗ МП",
            filter="Excel (*.xlsx *.xls)",
            list_widget=self.list_fbs,
            on_success=lambda added: self.set_info(
                f"Добавлено {len(added)} файлов ЧЗ МП"
            ),
        )

    @log_button_action("btn_reports", "Ошибка при выборе отчётов МП: {e}")
    def select_report_files(self) -> None:
        """Открывает диалог выбора отчётов МП.

        Роль: тонкая обёртка над _select_multiple_files. Файлы
              добавляются в list_reports через FileListWidget.add_file.
        """
        self._select_multiple_files(
            config_key="last_mp_dir",
            title="Выберите файлы отчётов МП",
            filter="Excel (*.xlsx *.xls)",
            list_widget=self.list_reports,
            on_success=lambda added: self.set_info(
                f"Добавлено {len(added)} отчётов МП"
            ),
        )

    # ============================================================
    # ОБРАБОТЧИКИ ПАЙПЛАЙНА
    # ============================================================

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
        """Шаг 1: подготовка — копирование файлов в рабочую папку."""
        if not self._precheck_target_dir():
            return
        if not self.list_fbs.get_files() and not self.list_reports.get_files():
            self.set_info("Как насчёт добавить хоть один отчётик?")
            return

        service = PreparationService(
            self.main_window.kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_prepare: PreparationService создан")

        self._run_async_step(
            service=service,
            target_method=service.prepare,
            kwargs={
                "fbs_files": self.list_fbs.get_files(),
                "mp_files": self.list_reports.get_files(),
            },
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_export_kiz,
        )

    @log_button_action("btn_export_kiz", "Ошибка в on_export_kiz: {e}")
    def on_export_kiz(self) -> None:
        """Шаг 2: выгрузка КИЗов из ЧЗ_МП и отчётов МП."""
        if not self._precheck_target_dir():
            return

        service = ExportKizService(
            self.main_window.kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_export_kiz: ExportKizService создан")

        self._run_async_step(
            service=service,
            target_method=service.export,
            kwargs={},
            start_message="Выгрузка КИЗов для обработки...",
            finish_message="Выгрузка завершена.",
            step_name="on_export_kiz",
            enable_after=self.btn_filter_prefinal,
        )

    @log_button_action("btn_filter_prefinal", "Ошибка в on_filter_prefinal: {e}")
    def on_filter_prefinal(self) -> None:
        """Шаг 3: фильтрация предитоговых файлов."""
        if not self._precheck_target_dir():
            return

        service = FilterPreFinalService(
            self.main_window.kiz_validator, self.log_manager_v2,
            brand_unknown_resolver=self._brand_request_unknown_decision,
        )
        if self.logger:
            self.logger.debug(
                "on_filter_prefinal: FilterPreFinalService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.filter_files,
            kwargs={},
            start_message="Фильтрация предитоговых файлов...",
            finish_message="Сбор данных завершён.",
            step_name="on_filter_prefinal",
            enable_after=self.btn_generate_sales,
        )

    @log_button_action("btn_generate_sales", "Ошибка в on_generate_sales: {e}")
    def on_generate_sales(self) -> None:
        """Шаг 4: формирование файлов продаж между продавцами."""
        if not self._precheck_target_dir():
            return

        service = GenerateSalesService(
            self.log_manager_v2,
            duplicate_keeper_resolver=self._duplicate_sale_request_keeper,
        )
        if self.logger:
            self.logger.debug(
                "on_generate_sales: GenerateSalesService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.generate,
            kwargs={},
            start_message="Формирование файлов продаж...",
            finish_message="Продажи сформированы.",
            step_name="on_generate_sales",
            enable_after=self.btn_finalize_prices,
        )

    @log_button_action("btn_finalize_prices", "Ошибка в on_finalize_prices: {e}")
    def on_finalize_prices(self) -> None:
        """Шаг 5: установка цен и финализация ИТОГ-файлов."""
        if not self._precheck_target_dir():
            return

        saved_prices = self.main_window.main_config.get("seller_prices", {})

        service = FinalizePricesService(
            self.main_window.kiz_validator,
            self.log_manager_v2,
            price_requester=self._request_average_price,
        )
        if self.logger:
            self.logger.debug(
                "on_finalize_prices: FinalizePricesService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.finalize,
            kwargs={"saved_prices": saved_prices},
            start_message="Внесение цен и финализация...",
            finish_message="Цены установлены, файлы финализированы.",
            step_name="on_finalize_prices",
            enable_after=None,
        )

    # ============================================================
    # СПЕЦИФИКА ЦЕН (осталась в окне)
    # ============================================================

    @log_button_action("btn_prices", "Ошибка при открытии окна цен: {e}")
    def on_open_prices_window(self) -> None:
        """Открывает окно редактирования сохранённых цен."""
        if not self._precheck_target_dir():
            return
        window = PricesEditWindow(
            self,
            sellers_brands_service=self.main_window.sellers_brands_service,
            main_config=self.main_window.main_config,
        )
        window.exec()

    def _request_average_price(self, seller_name: str) -> int | None:
        """Callback от FinalizePricesService: спросить цену у пользователя.

        Вход: seller_name — имя продавца.
        Выход: int — цена; None — отмена.

        Роль: делегирует в _run_in_ui_blocking — тот сам решает,
              вызывать диалог напрямую или через invokeMethod.
        """
        self._price_response = None
        self._run_in_ui_blocking(
            lambda: self._show_price_dialog_slot(seller_name)
        )
        return self._price_response

    @Slot(str)
    def _show_price_dialog_slot(self, seller_name: str) -> None:
        """Открывает диалог ввода средней цены в UI-потоке.

        Вход: seller_name — имя продавца.
        Выход: нет.
        Роль: сохранён без изменений из прежней версии.
        """
        dialog = AveragePriceInputDialog(self, seller_name)
        if dialog.exec():
            self._price_response = dialog.get_price()
        else:
            self._price_response = None

    def _brand_request_unknown_decision(self, brands_unknown: dict) -> dict:
        """Callback от FilterPreFinalService: разрешить неизвестные бренды.

        Вход:
            brands_unknown — {норм_ключ: [сырая_1, ...]}.
        Выход:
            dict от мастера ({"total", "resolved", "skipped"}),
            либо None при ошибке (сервис обработает).

        Роль: делегирует открытие мастера в UI-поток через
              _run_in_ui_blocking. Вызывается из фонового потока
              сервиса — прямой показ QDialog там недопустим.
        """
        return self._run_in_ui_blocking(
            lambda: self._open_brands_unknown_dialog(brands_unknown)
        )

    @Slot(object)
    def _open_brands_unknown_dialog(self, brands_unknown: dict) -> dict:
        """Открывает мастер разрешения неизвестных брендов.

        Вход: brands_unknown — {норм_ключ: [сырая_1, ...]}.
        Выход: агрегаты мастера ({"total", "resolved", "skipped"}).

        Роль: создаёт BrandsUnknownDialog, открывает модально через
              exec(), возвращает get_stats().
        """
        dialog = BrandsUnknownDialog(
            parent=self,
            brands_unknown=brands_unknown,
            sellers_brands_service=self.main_window.sellers_brands_service,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        return dialog.get_stats()

    # ============================================================
    # ОБРАБОТКА ДУБЛЕЙ В ПРОДАЖАХ
    # ============================================================

    def _duplicate_sale_request_keeper(self, kiz: str,
                                       file_to_receiver: dict):
        """Callback от GenerateSalesService: выбрать файл-получатель.

        Вход:
            kiz — 31-символьный КИЗ.
            file_to_receiver — dict[Path, str]: путь → имя получателя.
        Выход:
            Path выбранного файла или None (сервис сделает fallback
            на file_paths[0]).

        Роль: делегирует открытие диалога в UI-поток через
              _run_in_ui_blocking. Из фонового потока прямой показ
              QDialog недопустим.
        """
        return self._run_in_ui_blocking(
            lambda: self._duplicate_open_picker_dialog(
                kiz, file_to_receiver,
            )
        )

    def _duplicate_open_picker_dialog(self, kiz: str,
                                      file_to_receiver: dict):
        """Открывает SaleDuplicatePickerDialog в UI-потоке.

        Вход:
            kiz — 31-символьный КИЗ.
            file_to_receiver — dict[Path, str]: путь → имя получателя.

        Выход:
            Path выбранного файла или None.

        Роль:
            Вызывается из _duplicate_sale_request_keeper через
            lambda + _run_in_ui_blocking — прямой Python-вызов,
            не invokeMethod. @Slot не требуется: сигнатура с двумя
            Python-параметрами всё равно не совпала бы с одним
            Q_ARG. Создаёт диалог, открывает модально через exec(),
            возвращает get_selected_path().
        """
        dialog = SaleDuplicatePickerDialog(
            parent=self,
            kiz=kiz,
            file_to_receiver=file_to_receiver,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        return dialog.get_selected_path()