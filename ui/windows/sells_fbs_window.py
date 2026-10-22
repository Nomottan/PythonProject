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

Структура файла:
    КОНСТАНТЫ → ИНИЦИАЛИЗАЦИЯ → ОБРАБОТЧИКИ КНОПОК →
    ПРИВАТНЫЕ МЕТОДЫ → ВЗАИМОДЕЙСТВИЕ С ОКНОМ.
"""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QSizePolicy

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
    ListWidgetFactory,
)
from ui.styles import ColorCalculator, WindowStyle
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
from services.sells_fbs_service import PreparationService, FinalProcessingService
from utils.log_tools.decorators import log_button_action


class SellsFBSWindow(BaseServiceWindow):
    """Окно пайплайна ЧЗ МП.

    Роль:
        Объединяет шаги обработки КИЗов. Каждый шаг — отдельный
        сервис, запускается в фоновом потоке через
        BaseServiceWindow._run_async_step. Логи шагов идут в
        status_log; короткие подсказки — в status_label.

    Цвет:
        BG_COLOR вычисляется в __init__ от цвета MainWindow через
        WindowStyle.resolve_parent_bg. Классовый BG_COLOR оставлен
        как fallback, если окно создаётся без родителя.
    """

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = "SellsFBSWindow.sells_fbs_window"
    LOGGER_DOMAIN = "chz_mp"

    # Fallback; реальный BG_COLOR вычисляется в __init__ от parent.
    BG_COLOR = (50, 50, 50)

    PIPELINE_BUTTONS = (
        "btn_prepare",
        "btn_processing",
        "btn_files",
    )

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: вычисляет цвет от родителя, строит состояние, элементы
              и макет. Порядок блоков жёсткий: состояние → элементы
              → макет.
        """
        # Цвет — от родителя. Формула: r, g+g//5, 2b-b//5.
        parent_bg = WindowStyle.resolve_parent_bg(parent, (50, 50, 50))
        self.BG_COLOR = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r,
            g_fn=lambda g: g + g // 5,
            b_fn=lambda b: 2 * b - b // 2,
        )

        super().__init__(
            parent,
            title="Списание проданных КИЗов",
            log_manager_v2=log_manager_v2,
        )

        # ---------- СОСТОЯНИЕ ----------
        self._resolver_context_map: dict = {}
        self._price_response: int | None = None

        # ---------- ЭЛЕМЕНТЫ: файлы ----------
        self.btn_files = ButtonFactory.create_button(
            self, "Файлы", (30, 20, 35, 0.3),
            padding="4px 8px", fixed_size=(180, 24),
        )
        self.list_files = ListWidgetFactory.create_file_list_widget(
            self, fixed_width=180, bg_color=(30, 20, 35, 0.3),
            text_color=None, font_size=10,
        )

        # ---------- ЭЛЕМЕНТЫ: описание ----------
        self.desc_label = LabelFactory.create_label(
            self,
            text=(
                "Загрузи файлы и отчёты\n"
                "Шаг 1: Нажми Подготовка. Файлы будут скопированы и разобраны в рабочую директорию, оригиналы нетронуты\n"
                "Проведи все файлы через BestMark в Excell файлы сохранив названия\n"
                "Шаг 2: Нажми Обработка. Файлы будут очищены от некорректных статусов и владельцев, собраны файлы для продаж, установлены цены и финализированы ИТОГ-файлы.\n"
                "Шаг 3: Проверка (в разработке)\n"
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

        # ---------- ЭЛЕМЕНТЫ: путь ----------
        # path_selector создаётся в BaseServiceWindow.
        self.path_selector.setFixedWidth(370)

        # ---------- ЭЛЕМЕНТЫ: кнопки действий ----------
        _action_configs = [
            ("btn_prepare", "Подготовка", (80, 90, 120), "8px 16px", (180, 35)),
            ("btn_data_verification", "Проверка", (40, 130, 120), "8px 16px", (180, 35)),
            ("btn_processing", "Обработка", (60, 110, 120), "8px 16px", (180, 35)),
            ("btn_prices", "Цены", (40, 40, 40), "2px 2px", (35, 20)),
        ]
        _action_handlers = {
            "btn_prepare": "on_prepare",
            "btn_data_verification": "on_data_verification",
            "btn_processing": "on_processing",
            "btn_prices": "on_open_prices_window",
        }
        ButtonFactory.create_buttons_from_config(
            self, _action_configs, _action_handlers,
        )
        # Все кнопки шагов изначально отключены, кроме подготовки.
        self.btn_processing.setEnabled(False)
        self.btn_files.clicked.connect(self.select_files)

        # ---------- МАКЕТ ----------
        box = LayoutFactory.create_service_box(
            self,
            path_selector=self.path_selector,
            status_label=self.status_label,
            left_buttons=[
                self.btn_prepare, self.btn_data_verification,
                self.btn_processing, self.btn_prices,
            ],
            right_items=[self.btn_files, self.list_files],
        )

        self._add_service_page(
            self.desc_label, box, self._create_accumulate_row(),
        )

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
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
            enable_after=self.btn_processing,
        )

    @log_button_action("btn_processing", "Ошибка в on_processing: {e}")
    def on_processing(self) -> None:
        """Шаг 2: обработка файлов + формирование продаж + дубли."""
        if not self._precheck_target_dir():
            return

        saved_prices = self.main_window.main_config.get("seller_prices", {})

        service = FinalProcessingService(
            self.main_window.kiz_validator,
            self.log_manager_v2,
            brand_unknown_resolver=self._brand_request_unknown_decision,
            duplicate_keeper_resolver=self._duplicate_sale_request_keeper,
            price_requester=self._request_average_price,
        )
        if self.logger:
            self.logger.debug(
                "on_processing: FinalProcessingService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.completion,
            kwargs={"saved_prices": saved_prices},
            start_message="Обработка файлов...",
            finish_message="Обработка завершена.",
            step_name="on_processing",
            enable_after=None,
        )

    @log_button_action("btn_data_verification", "Ошибка в on_data_verification: {e}")
    def on_data_verification(self) -> None:
        """Шаг 3: заглушка сервиса проверки данных."""
        self.set_status("Сервис проверки данных в разработке")
        self.set_info("Сервис проверки данных в разработке")

    @log_button_action("btn_prices", "Ошибка при открытии окна цен: {e}")
    def on_open_prices_window(self) -> None:
        """Открывает окно редактирования сохранённых цен."""
        window = PricesEditWindow(
            self,
            sellers_brands_service=self.main_window.sellers_brands_service,
            main_config=self.main_window.main_config,
        )
        window.exec()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ЦЕНА
    # ============================================================

    def _request_average_price(self, seller_name: str) -> int | None:
        """Callback от FinalProcessingService: спросить цену у пользователя.

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

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: РЕЗОЛВЕР БРЕНДОВ
    # ============================================================

    def _brand_request_unknown_decision(self, brands_unknown: dict) -> dict:
        """Callback от FinalProcessingService: разрешить неизвестные бренды.

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

    def _pick_brand(self, norm_key: str, raws: list,
                    parent=None) -> Brand:
        """Выбор существующего бренда из списка.

        Вход:
            norm_key — нормализованный ключ.
            raws — список сырых строк.
            parent — резолвер (иерархия: закрытие вместе, z-order).

        Выход: Brand.

        Роль: открывает ObjectPickerDialog, ищет Brand по имени.
              Если ничего не выбрано — ValueError (окно покажет
              уведомление и останется на текущем объекте).

        Геометрия: parent — резолвер, но service_window явно
              ставится в SellsFBSWindow. Так центрирование
              считается от сервисного окна, а не от резолвера.
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
        dialog.service_window = self
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
            dialog.service_window = self
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

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: РЕЗОЛВЕР ПРОДАВЦОВ
    # ============================================================

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
        dialog.service_window = self
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
        # Явно: по геометрии — от сервисного окна.
        dialog.service_window = self
        dialog.exec()
        selected = dialog.get_selected()
        if selected is None:
            raise ValueError("Продавец не выбран")
        return selected

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ДУБЛИ В ПРОДАЖАХ
    # ============================================================

    def _duplicate_sale_request_keeper(self, kiz: str,
                                       file_to_receiver: dict):
        """Callback от FinalProcessingService: выбрать файл-получатель.

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

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _on_target_dir_changed_hook(self) -> None:
        """Сброс кнопки обработки при смене папки.

        Вход: нет.
        Выход: нет.
        Роль: базовый _on_target_dir_changed уже очистил status_log
              и обновил target_dir; здесь — только сброс btn_processing.
        """
        self.btn_processing.setEnabled(False)

    def _current_sellers(self) -> list:
        """Возвращает продавцов с восстановленными связями Brand.

        Вход: нет.
        Выход: list[Seller] с заполненным .brands.

        Роль:
            Override базового _current_sellers. Для шага
            «Обработка» нужны продавцы с полной информацией
            о брендах — иначе фильтрация не соберёт маппинг
            «ключ бренда → Brand».
        """
        return (
            self.main_window.sellers_brands_service
            .get_sellers_with_brands()
        )

    # ============================================================
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def cleanup(self) -> None:
        """Сброс списка файлов при закрытии окна.

        Вход: нет.
        Выход: нет.
        Роль: вызывается из базового closeEvent. Очищает list_files.
        """
        self.list_files.clear_files()