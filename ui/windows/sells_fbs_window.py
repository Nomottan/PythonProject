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
    QHBoxLayout, QVBoxLayout, QWidget, QSizePolicy
)

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
    ListWidgetFactory,
)
from ui.styles import ColorCalculator
from ui.widgets.path_selector import PathSelector
from ui.windows.shared_dialogs import (
    PricesEditWindow, AveragePriceInputDialog, SaleDuplicatePickerDialog,
)
from ui.windows.unknown_resolver_dialog import (
    UnknownResolverDialog, ObjectPickerDialog,
)
from ui.windows.brands_window import BrandEditDialog
from ui.windows.message_dialog import NotificationDialog
from models.models import Brand
from utils.text_utils import TextUtils
from utils.unknown_resolver import ResolverRouter
from services.sells_fbs_service import (
    PreparationService,
    FilterPreFinalService, GenerateSalesService, FinalizePricesService,
)
from utils.log_tools.decorators import log_button_action


class SellsFBSWindow(BaseServiceWindow):
    """Окно пайплайна ЧЗ МП.

    Роль:
        Объединяет шаги обработки КИЗов. Каждый шаг — отдельный
        сервис, запускается в фоновом потоке через
        BaseServiceWindow._run_async_step. Логи шагов идут в
        status_log; короткие подсказки — в status_label.
    """

    LOGGER_SOURCE = "SellsFBSWindow.sells_fbs_window"
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
        "btn_filter_prefinal",
        "btn_generate_sales",
        "btn_finalize_prices",
        "btn_files",
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
        self._resolver_context_map: dict = {}
        # Специфичное состояние для диалога средней цены.
        self._price_response: int | None = None

        # ---------- ОДНА КНОПКА И ОДИН СПИСОК ФАЙЛОВ ----------
        self.btn_files = ButtonFactory.create_button(
            self, "Файлы", (30, 20, 35, 0.3),
            padding="4px 8px", fixed_size=(180, 24),
        )
        self.list_files = ListWidgetFactory.create_file_list_widget(
            self, fixed_width=180, bg_color=(30, 20, 35, 0.3),
            text_color=None, font_size=10,
        )

        # ---------- ОПИСАНИЕ ----------
        self.desc_label = LabelFactory.create_label(
            self,
            text=(
                "Подготовка отчётов по продавцам для вывода КИЗов из оборота\n"
                "Загрузи файлы и отчёты\n"
                "Шаг 1: Нажми Подготовка. Файлы будут скопированы и разобраны в рабочую директорию, оригиналы нетронуты\n"
                "Проведи все файлы через BestMark в Excell файлы сохранив названия\n"
                "Шаг 2: Нажми Сбор данных. Файлы будут очищены от некорректных статусов и владельцев\n"
                "Шаг 3: Нажми Продажи. Будут собраны файлы для продаж продавцам не их КИЗов\n"
                "Шаг 4: Нажми Установка цен.\n"
                "Проведи продажи через ЭДО. После выводи их из оборота"
            ),
            bg_color=(0, 0, 0, 0),
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        self.desc_label.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Ignored,
        )
        self.desc_label.setMinimumHeight(0)
        # ---------- ВЫБОР ПАПКИ ----------
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку",
        )
        self.path_selector.setFixedWidth(370)
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        # ---------- КНОПКИ ДЕЙСТВИЙ ----------
        _action_configs = [
            ("btn_prepare", "Подготовка", (80, 90, 120), "8px 16px", (180, 35)),
            ("btn_filter_prefinal", "Сбор данных", (60, 110, 120), "8px 16px", (180, 35)),
            ("btn_generate_sales", "Продажи", (50, 120, 120), "8px 16px", (180, 35)),
            ("btn_finalize_prices", "Установка цен", (40, 130, 120), "8px 16px", (180, 35)),
            ("btn_prices", "Цены", (40, 40, 40), "2px 2px", (35, 20)),
        ]
        _action_handlers = {
            "btn_prepare": "on_prepare",
            "btn_filter_prefinal": "on_filter_prefinal",
            "btn_generate_sales": "on_generate_sales",
            "btn_finalize_prices": "on_finalize_prices",
            "btn_prices": "on_open_prices_window",
        }
        ButtonFactory.create_buttons_from_config(
            self, _action_configs, _action_handlers,
        )
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35),
        )
        # Все кнопки шагов изначально отключены, кроме подготовки.
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)


        # ---------- МАКЕТ ----------
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)

        # Верх: описание и выбор папки.
        center_layout.addWidget(self.desc_label)
        center_layout.addWidget(self.path_selector, alignment=Qt.AlignCenter)

        # Две колонки: слева статус-строка и кнопки этапов,
        # справа кнопка и список файлов.
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)
        columns_layout.setAlignment(Qt.AlignCenter)

        left_widget = QWidget()
        left_widget.setFixedWidth(180)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        # Статус-строка сверху, на одной линии с btn_files справа.
        self.status_label.setMinimumHeight(28)
        left_layout.addWidget(self.status_label)
        left_layout.addWidget(self.btn_prepare)
        left_layout.addWidget(self.btn_filter_prefinal)
        left_layout.addWidget(self.btn_generate_sales)
        left_layout.addWidget(self.btn_finalize_prices)
        left_layout.addWidget(self.btn_prices)
        left_layout.addStretch()

        right_widget = QWidget()
        right_widget.setFixedWidth(180)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        right_layout.addWidget(self.btn_files)
        right_layout.addWidget(self.list_files)
        right_layout.addStretch()

        columns_layout.addWidget(left_widget)
        columns_layout.addWidget(right_widget)

        columns_row = QHBoxLayout()
        columns_row.addStretch()
        columns_row.addLayout(columns_layout)
        columns_row.addStretch()
        center_layout.addLayout(columns_row)

        # Растяжка: прижимает лог и «Собрать продажи» к низу.
        center_layout.addStretch(1)

        # Низ: лог и кнопка «Собрать продажи».
        center_layout.addWidget(self.status_log)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)

        self.main_layout.addLayout(center_layout)

        # Кнопка выбора входных файлов.
        self.btn_files.clicked.connect(self.select_files)

    # ============================================================
    # ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _on_target_dir_changed_hook(self) -> None:
        """Сброс кнопок шагов 2–4 при смене папки.

        Вход: нет.
        Выход: нет.
        Роль: базовый _on_target_dir_changed уже очистил status_log
              и обновил target_dir; здесь — только сброс кнопок.
        """
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
        """Сброс списка файлов при закрытии окна."""
        self.list_files.clear_files()

    # ============================================================
    # ВЫБОР ФАЙЛОВ
    # ============================================================

    @log_button_action("btn_files", "Ошибка при выборе файлов: {e}")
    def select_files(self) -> None:
        """Открывает диалог выбора входных файлов (отчёты со склада, wb и ozon).

        Роль: единая точка выбора. Файлы попадают в list_files
              через FileListWidget.add_file, тип определяется
              позже — на шаге «Подготовка».
        """
        self._select_multiple_files(
            config_key="last_files_dir",
            title="Выберите файлы",
            filter="Excel (*.xlsx *.xls)",
            list_widget=self.list_files,
            on_success=lambda added: self.set_info(
                f"Добавлено {len(added)} файлов"
            ),
        )

    # ============================================================
    # ОБРАБОТЧИКИ ПАЙПЛАЙНА
    # ============================================================

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
        """Шаг 1: подготовка + разбор отчётов одним сервисом."""
        if not self._precheck_target_dir():
            return
        if not self.list_files.get_files():
            self.set_info("Как насчёт добавить хоть один файл?")
            return

        service = PreparationService(
            self.main_window.kiz_validator,
            self.log_manager_v2,
            seller_unknown_resolver=self._seller_request_unknown_decision,
        )
        if self.logger:
            self.logger.debug("on_prepare: PreparationService создан")

        self._run_async_step(
            service=service,
            target_method=service.prepare,
            kwargs={"files": self.list_files.get_files()},
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_filter_prefinal,
        )

    @log_button_action("btn_filter_prefinal", "Ошибка в on_filter_prefinal: {e}")
    def on_filter_prefinal(self) -> None:
        """Шаг 2: фильтрация предитоговых файлов."""
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
        """Шаг 3: формирование файлов продаж между продавцами."""
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
        """Шаг 4: установка цен и финализация ИТОГ-файлов."""
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
            dict от мастера ({"total", "resolved", "skipped"}).

        Роль: делегирует открытие мастера в UI-поток через
              _run_in_ui_blocking. Вызывается из фонового потока
              сервиса — прямой показ QDialog там недопустим.
        """
        return self._run_in_ui_blocking(
            lambda: self._show_brand_resolver(brands_unknown)
        )

    @Slot(object)
    def _show_brand_resolver(self, brands_unknown: dict) -> dict:
        """Открывает UnknownResolverDialog для брендов.

        Вход: brands_unknown — {норм_ключ: [сырая_1, ...]}.
        Выход: агрегаты {"total", "resolved", "skipped"}.

        Роль: собирает actions для брендов, открывает мастер,
              применяет результат через ResolverRouter.
        """
        service = self.main_window.sellers_brands_service
        dialog = None

        def _pick(nk, raws):
            return self._pick_brand(nk, raws, parent=dialog)

        def _edit(nk, raws):
            return self._edit_brand_for_resolver(nk, raws, parent=dialog)

        actions = ResolverRouter.build_brand_actions(
            service=service,
            pick_brand_cb=_pick,
            edit_brand_cb=_edit,
        )
        dialog = UnknownResolverDialog(
            parent=self,
            items=brands_unknown,
            actions=actions,
            get_label=lambda nk, raws: raws[0],
            title="Неизвестные бренды",
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        result = dialog.get_result()
        return ResolverRouter.apply_result(
            result, actions, items=brands_unknown, logger=self.logger,
        )

    def _seller_request_unknown_decision(self, unresolved: dict,
                                         context_map: dict) -> dict:
        """Callback от PreparationService: разрешить неизвестные имена.

        Вход:
            unresolved — {норм_ключ: [сырая_1, ...]}.
            context_map — {норм_ключ: set{"mp", "wh"}}.

        Выход:
            dict {"total", "resolved", "skipped", "decisions"}.

        Роль: сохраняет context_map для _format_seller_item_label,
              делегирует открытие в UI-поток.
        """
        self._resolver_context_map = context_map
        return self._run_in_ui_blocking(
            lambda: self._show_seller_resolver(unresolved)
        )

    @Slot(object)
    def _show_seller_resolver(self, unresolved: dict) -> dict:
        """Открывает UnknownResolverDialog для продавцов.

        Вход: unresolved — {норм_ключ: [сырая_1, ...]}.
        Выход: агрегаты + decisions.

        Роль: собирает actions для продавцов, открывает мастер,
              применяет результат, формирует decisions.
        """
        service = self.main_window.sellers_brands_service
        dialog = None

        def _pick_special(nk, raws):
            return self._pick_seller_with_special(nk, raws, parent=dialog)

        def _pick_no_special(nk, raws):
            return self._pick_seller_no_special(nk, raws, parent=dialog)

        actions = ResolverRouter.build_seller_actions(
            service=service,
            pick_seller_with_special_cb=_pick_special,
            pick_seller_no_special_cb=_pick_no_special,
        )
        dialog = UnknownResolverDialog(
            parent=self,
            items=unresolved,
            actions=actions,
            get_label=self._format_seller_item_label,
            title="Неизвестные имена",
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        result = dialog.get_result()
        stats = ResolverRouter.apply_result(
            result, actions, items=unresolved, logger=self.logger,
        )
        stats["decisions"] = ResolverRouter.build_decisions_from_result(
            result, self._resolver_context_map,
        )
        return stats

    def _format_seller_item_label(self, norm_key: str,
                                  raws: list) -> str:
        """Форматирует лейбл неизвестного имени с контекстом.

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
        Выход: "сырое_имя (файл)" / "(лист склада)" / "(файл, лист склада)".

        Роль: показывает пользователю, откуда пришло имя — из файла
              МП или из листа склада.
        """
        contexts = self._resolver_context_map.get(norm_key, set())
        if isinstance(contexts, str):
            contexts = {contexts}
        parts = []
        if "mp" in contexts:
            parts.append("файл")
        if "wh" in contexts:
            parts.append("лист склада")
        suffix = f" ({', '.join(parts)})" if parts else ""
        return f"{raws[0]}{suffix}"

    # ============================================================
    # ПИКЕРЫ (вызываются из UnknownResolverDialog)
    # ============================================================

    def _pick_brand(self, norm_key: str, raws: list, parent=None) -> Brand:
        """Выбор существующего бренда из списка.

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
            parent — резолвер (для наследования цвета).

        Выход: Brand.

        Роль: открывает ObjectPickerDialog, ищет Brand по имени.
              Если ничего не выбрано — ValueError (окно покажет
              уведомление и останется на текущем объекте).
        """
        brands = (
            self.main_window.sellers_brands_service.get_brands_objects()
        )
        items = {b.name: b.name for b in brands}
        dialog = ObjectPickerDialog(
            parent=parent,
            items=items,
            extra_items=None,
            title="Выбор бренда",
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        selected = dialog.get_selected()
        if selected is None:
            raise ValueError("Бренд не выбран")
        for b in brands:
            if b.name == selected:
                return b
        raise ValueError("Бренд не найден")

    def _edit_brand_for_resolver(self, norm_key: str, raws: list,
                                 parent=None) -> Brand:
        """Создание нового бренда через цикл редактирования.

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
            parent — резолвер (для наследования цвета).

        Выход: созданный Brand.

        Роль: переоткрывает BrandEditDialog, пока бренд не создан.
              При was_deleted() — повтор. При пустом имени — повтор.
              При ошибке create_brand — уведомление и повтор.
        """
        service = self.main_window.sellers_brands_service
        while True:
            new_brand = Brand(name=raws[0], keys=list(raws))
            sellers = service.get_sellers_with_brands()
            dialog = BrandEditDialog(
                parent=parent,
                brand=new_brand,
                sellers=sellers,
                main_window=self.main_window,
                log_manager_v2=self.log_manager_v2,
            )
            dialog.exec()
            if dialog.was_deleted():
                continue
            if (not new_brand.name
                    or TextUtils.normalize(new_brand.name) == ""):
                continue
            if service.create_brand(
                    new_brand.name, new_brand.keys,
                    new_brand.requires_saving,
            ):
                return new_brand
            NotificationDialog.notify(
                self,
                f"Не удалось создать бренд '{new_brand.name}'",
                title_text="Ошибка", bg_color=self.bg_color,
            )

    def _pick_seller_with_special(self, norm_key: str, raws: list,
                                  parent=None) -> str:
        """Выбор продавца с опцией Мусор / Неопознанный / Возвраты.

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
            parent — резолвер.

        Выход: имя продавца или спец-значение.
        """
        sellers = (
            self.main_window.sellers_brands_service.get_sellers_objects()
        )
        items = {s.name: s.name for s in sellers}
        extra_items = {
            "garbage": "Мусор",
            "unknown": "Неопознанный",
            "returns": "Возвраты",
        }
        dialog = ObjectPickerDialog(
            parent=parent,
            items=items,
            extra_items=extra_items,
            title="Выбор продавца",
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        selected = dialog.get_selected()
        if selected is None:
            raise ValueError("Продавец не выбран")
        return selected

    def _pick_seller_no_special(self, norm_key: str, raws: list,
                                parent=None) -> str:
        """Выбор продавца без спец-опций (для «Добавить ключ»).

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
            parent — резолвер.

        Выход: имя продавца.
        """
        sellers = (
            self.main_window.sellers_brands_service.get_sellers_objects()
        )
        items = {s.name: s.name for s in sellers}
        dialog = ObjectPickerDialog(
            parent=parent,
            items=items,
            extra_items=None,
            title="Выбор продавца",
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        selected = dialog.get_selected()
        if selected is None:
            raise ValueError("Продавец не выбран")
        return selected

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