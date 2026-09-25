"""
Окно «Списание проданных КИЗов» (ЧЗ МП).

Назначение:
    Пайплайн из пяти шагов: подготовка файлов, выгрузка КИЗов,
    фильтрация предитоговых файлов, формирование продаж,
    установка цен и финализация.

Роль в программе:
    Открывается из MainWindow. Связано с LoggerV2 через
    log_manager_v2 — сервисы по-прежнему пишут через старый
    Logger/TaskContext, окно пишет только свои сообщения.
"""

from pathlib import Path
from openpyxl import load_workbook
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QApplication,
)
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot, QThread
from ui.factories.factories import (
    LabelFactory, ListWidgetFactory, ButtonFactory, LayoutFactory,
    FileDialogFactory, ThreadFactory, WindowFactory, StatusLogFactory,
)
from ui.widgets.path_selector import PathSelector
from ui.windows.shared_dialogs import (
    PricesEditWindow, AveragePriceInputDialog,
)
from services.sells_fbs_service import (
    PreparationService, ExportKizService,
    FilterPreFinalService, GenerateSalesService, FinalizePricesService,
)
from services.sales_accumulator import SalesAccumulatorService
from ui.windows.message_dialog import NotificationDialog
from utils.log_tools.decorators import log_button_action


class ChzMPWindow(QMainWindow):
    """Окно пайплайна ЧЗ МП.

    Роль: объединяет шаги обработки КИЗов. Каждый шаг —
          отдельный сервис, запускается в фоновом потоке через
          ThreadFactory. Логи шагов идут в status_display;
          короткие подсказки — в status_label.
    """
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
            log_manager_v2 — LogManagerV2 или None. Если None —
                             logger остаётся None, окно работает
                             как раньше, но без логирования.
        """
        super().__init__(parent)
        self._price_response: int | None = None
        self.log_manager_v2 = log_manager_v2

        self.logger = None
        if log_manager_v2 is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source="ChzMPWindow.chz_mp_window",
                domain="chz_mp",
            )
        if self.logger:
            self.logger.debug("ChzMPWindow.__init__: старт")

        # Переменные состояния
        self.target_dir = parent.main_config.get("target_dir", None)
        self.fbs_files = []
        self.mp_files = []
        self.fbs_signatures = []
        self.bg_color = (50, 60, 90, 0.95)

        # Настройка окна через фабрику
        main_layout = WindowFactory.setup_child_window(
            self, "Списание проданных КИЗов",
            bg_color=self.bg_color
        )

        # ============================================================
        # ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ
        # ============================================================

        # Кнопки-индикаторы
        _indicator_configs = [
            ("btn_fbs", "Отчёты с FBS", (30, 20, 35, 0.3)),
            ("btn_reports", "Отчёты с МП", (30, 20, 35, 0.3)),
        ]
        ButtonFactory.create_buttons_from_config(self, _indicator_configs)

        # Списки файлов
        self.list_fbs = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=105,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10
        )
        self.list_reports = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=105,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10
        )

        # Описание
        self.desc_label = LabelFactory.create_label(
            self,
            text="Подготовка отчётов по продавцам для вывода КИЗов из оборота\n"
                 "Загрузи файлы и отчёты выше\n"
                 "Шаг 1: Нажми Подготовка. Файлы будут скопированы в рабочую директорию, оригиналы будут нетронуты\n"
                 "Шаг 2: Нажми Выгрузка для обработки. Будут созданы текстовые файлы\n"
                 "Проведи все файлы через BestMark в Excell файлы сохранив названия\n"
                 "Шаг 3: Нажми Сбор данных. Файлы будут очищены от некорректных статусов и владельцев\n"
                 "Шаг 4: Нажми Продажи. Будут собраны файлы для продаж продавцам не их КИЗов\n"
                 "Проведи продажи через ЭДО\n"
                 "Шаг 5: Нажми установка Цен. \n"
                 "Будут использованы цены из Отчётов МП, а остальные заполняться случайным ценами от средней\n"
                 "После выводи их из оборота",
            bg_color=(0, 0, 0, 0),
            text_color="#c2c2c2",
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True
        )

        # Виджет выбора пути
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку"
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        # NEW: короткая подсказка для set_status-канала.
        self.status_label = LabelFactory.create_status_label(
            self, "Выберите целевую папку и файлы"
        )

        # ---- СТАТУСНАЯ ОБЛАСТЬ (лог с прокруткой) ----
        self.status_display = StatusLogFactory.create_status_log(
            self, bg_color=self.bg_color,
            min_height=100, max_height=200,
        )

        # ---- КНОПКИ ДЕЙСТВИЙ (НОВЫЙ ПРОЦЕСС) ----
        _action_configs = [
            ("btn_prepare",          "Подготовка",             (80, 90, 120),  "8px 16px", (180, 35)),
            ("btn_export_kiz",       "Выгрузка для обработки", (70, 100, 120),  "8px 16px", (180, 35)),
            ("btn_filter_prefinal",  "Сбор данных",            (60, 110, 120), "8px 16px", (180, 35)),
            ("btn_generate_sales",   "Продажи",                (50, 120, 120),   "8px 16px", (180, 35)),
            ("btn_finalize_prices",  "Установка цен",          (40, 130, 120),  "8px 16px", (180, 35)),
            ("btn_prices",           "Цены",                   (40, 40, 40),  "2px 2px", (35, 20)),
        ]
        _action_handlers = {
            "btn_prepare":          "on_prepare",
            "btn_export_kiz":       "on_export_kiz",
            "btn_filter_prefinal":  "on_filter_prefinal",
            "btn_generate_sales":   "on_generate_sales",
            "btn_finalize_prices":  "on_finalize_prices",
            "btn_prices": "on_open_prices_window",
        }
        ButtonFactory.create_buttons_from_config(self, _action_configs, _action_handlers)

        # Все кнопки изначально отключены, кроме подготовки
        self.btn_export_kiz.setEnabled(False)
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)

        # ============================================================
        # МАКЕТ
        # ============================================================
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        # Первая строка: индикаторы
        headers_container = LayoutFactory.create_row(
            self, self.btn_fbs, self.btn_reports,
            fixed_width=365
        )
        center_layout.addWidget(headers_container, alignment=Qt.AlignCenter)

        # Вторая строка: списки файлов
        lists_container = LayoutFactory.create_row(
            self, self.list_fbs, self.list_reports,
            fixed_width=365
        )
        center_layout.addWidget(lists_container, alignment=Qt.AlignCenter)

        # Описание
        center_layout.addWidget(self.desc_label)

        # Выбор папки
        center_layout.addWidget(self.path_selector)

        # NEW: короткая подсказка сразу под выбором пути.
        center_layout.addWidget(self.status_label)

        # Ряд кнопок: Подготовка, Выгрузка, Сбор данных
        row1 = LayoutFactory.create_row(
            self, self.btn_prepare, self.btn_export_kiz, self.btn_filter_prefinal,
            spacing=8
        )
        center_layout.addWidget(row1)

        # Ряд кнопок: Продажи, Установка цен
        row2 = LayoutFactory.create_row(
            self, self.btn_generate_sales, self.btn_finalize_prices, self.btn_prices,
            spacing=8
        )
        center_layout.addWidget(row2)

        # Статусный лог
        center_layout.addWidget(self.status_display)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35)
        )
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)
        # Растяжка
        center_layout.addStretch(1)

        main_layout.addLayout(center_layout)

        # Подключение специфических сигналов
        self.btn_fbs.clicked.connect(self.select_fbs_files)
        self.btn_reports.clicked.connect(self.select_report_files)

        if self.logger:
            self.logger.debug("ChzMPWindow.__init__: окно инициализировано")

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================
    def _on_target_dir_changed(self, new_path):
        """Обработка смены целевой папки.

        Вход: new_path — новый путь.
        Роль: обновляет target_dir, пишет в main_config,
              сбрасывает кнопки шагов 2–5 до готовности.
        """
        if self.logger:
            self.logger.debug(f"_on_target_dir_changed: новая папка {new_path}")
        self.target_dir = new_path
        self.parent().main_config.set("target_dir", new_path)
        self.status_display.clear()
        self.status_display.clear()
        self.set_status("Целевая папка обновлена.")
        self.set_info("Целевая папка обновлена.")
        self.btn_export_kiz.setEnabled(False)
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)

    # ---------- Общая обвязка шагов пайплайна ----------
    def set_status(self, msg: str) -> None:
        """Обновляет короткое сообщение в статусной строке.

        Вход: msg — текст.
        Выход: нет.
        Роль: единая точка обновления status_label. Вызывается
              из StatusHandler через active_child.set_status.
        """
        self.status_label.setText(msg)

    def set_info(self, msg: str) -> None:
        """Дописывает сообщение в прокручиваемый лог.

        Вход: msg — текст.
        Выход: нет.
        Роль: единая точка записи в status_display. Вызывается
              из InfoUIHandler через active_child.set_info.
        """
        self.status_display.append(msg)

    def _precheck_target_dir(self) -> bool:
        """Проверяет, что выбрана целевая папка.

            Вход: нет.
            Выход:
                True — папка выбрана, шаг можно запускать.
                False — папки нет, в status_display записано предупреждение.

            Роль:
                Единая точка проверки target_dir для всех пяти шагов
                пайплайна. Раньше одинаковый блок повторялся в каждом
                обработчике.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return False
        return True

    def _current_sellers(self) -> list:
        """Возвращает актуальный список продавцов.

        Вход: нет.
        Выход: список Seller из SellersBrandsService родителя.

        Роль:
            Единая точка получения sellers для шагов пайплайна.
            Раньше одинаковый вызов повторялся в каждом обработчике.
        """
        return self.parent().sellers_brands_service.get_sellers_objects()

    def _run_pipeline_step(self, *, service, target_method,
                               kwargs: dict, start_message: str,
                               finish_message: str, step_name: str,
                               enable_after=None) -> None:
        """Запускает шаг пайплайна в фоновом потоке.

            Вход (все параметры именованные — так защищаемся от перепутывания
            длинного списка похожих по типу аргументов):
                service — уже созданный экземпляр сервиса.
                target_method — bound method сервиса, который нужно
                                выполнить в потоке (service.prepare,
                                service.export, ...).
                kwargs — доп. именованные аргументы target_method.
                         target_dir и sellers добавляются здесь
                         автоматически. Дополнительно каждый шаг может
                         передать свои (fbs_files/mp_files/saved_prices).
                start_message — текст для статуса в начале шага.
                finish_message — текст для статуса при успехе.
                step_name — префикс для сообщений в logger окна.
                enable_after — виджет QPushButton, который нужно включить
                               после успешного завершения. None — если
                               включать нечего (последний шаг пайплайна).

            Выход: нет.

            Роль:
                Единая обвязка пяти шагов: запись короткого сообщения
                в status_label и подробного — в status_display, колбэки
                on_finished/on_error, вызов ThreadFactory с фиксированным
                списком блокируемых кнопок.
        """
        self.set_status(start_message)
        self.set_info(start_message)

        def on_finished():
            """Вызывается в UI-потоке после успешного завершения шага."""
            self.set_status(finish_message)
            self.set_info(finish_message)
            if enable_after is not None:
                enable_after.setEnabled(True)
            if self.logger:
                self.logger.debug(f"{step_name}: фоновый поток завершён")

        def on_error(e):
            """Вызывается в UI-потоке при исключении в фоновом потоке.

            Вход: e — пойманное исключение.
            """
            # REPLACE: было только self.status_display.append(...) —
            # стало двойное через set_status/set_info.
            self.set_status(f"Ошибка на шаге {step_name}: {e}")
            self.set_info(f"Ошибка на шаге {step_name}: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в {step_name}: {e}", can_influence=False,
                )

        # Собираем финальные kwargs: target_dir и sellers — общие
        # для всех шагов. Доп. параметры шага не должны их перекрывать.
        call_kwargs = {
            "target_dir": self.target_dir,
            "sellers": self._current_sellers(),
        }
        call_kwargs.update(kwargs)

        ThreadFactory.create_thread(
            parent=self,
            buttons=list(self.PIPELINE_BUTTONS),
            target_func=target_method,
            kwargs=call_kwargs,
            on_finished=on_finished,
            error_callback=on_error,
        )

    @log_button_action("btn_fbs", "Ошибка при выборе файлов ЧЗ МП: {e}")
    def select_fbs_files(self):
        """Открывает диалог выбора файлов ЧЗ МП.

        Роль: выбранные файлы добавляются в self.fbs_files.
              Дубликаты (по первой ячейке листа) отсеиваются
              с уведомлением.
        """
        start = self.parent().main_config.get("last_fbs_dir", None)
        files = FileDialogFactory.open_files_dialog(self, "Выберите файлы ЧЗ МП", start)
        if not files:
            return
        if self.logger:
            self.logger.debug(f"select_fbs_files: выбрано файлов {len(files)}")

        first_file = Path(files[0])
        self.parent().main_config.set("last_fbs_dir", str(first_file.parent))

        for f in files:
            try:
                wb = load_workbook(f, data_only=True)
                sheet = wb.active
                first_row = sheet[1] if sheet.max_row >= 1 else None
                first_val = first_row[0].value if first_row and first_row[0].value else ""
                wb.close()
            except Exception:
                first_val = ""

            if first_val in self.fbs_signatures:
                if self.logger:
                    self.logger.debug(
                        f"select_fbs_files: файл {Path(f).name} уже выбран (дубликат)"
                    )
                NotificationDialog.notify(
                    self,
                    f"Файл {Path(f).name} уже выбран (совпадает первая строка). Дубль не был добавлен",
                    title_text="Дубликат",
                    bg_color=self.bg_color,
                )
                continue

            self.fbs_files.append(f)
            self.fbs_signatures.append(first_val)
            self.list_fbs.addItem(Path(f).name)

    @log_button_action("btn_reports", "Ошибка при выборе отчётов МП: {e}")
    def select_report_files(self):
        """Открывает диалог выбора отчётов МП.

        Роль: выбранные файлы заменяют содержимое self.mp_files
              и списка list_reports.
        """
        start = self.parent().main_config.get("last_mp_dir", None)
        files = FileDialogFactory.open_files_dialog(self, "Выберите файлы отчётов МП", start)
        if files:
            if self.logger:
                self.logger.debug(f"select_report_files: выбрано файлов {len(files)}")
            first_file = Path(files[0])
            self.parent().main_config.set("last_mp_dir", str(first_file.parent))
            self.mp_files = files
            self.list_reports.clear()
            for f in files:
                self.list_reports.addItem(Path(f).name)

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================
    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self):
        """Шаг 1: подготовка — копирование файлов в рабочую папку."""
        if not self._precheck_target_dir():
            return
        # Дополнительная проверка шага: должен быть хоть один файл.
        if not self.fbs_files and not self.mp_files:
            self.status_display.append(
                "Как насчёт добавить хоть один отчётик?"
            )
            return

        service = PreparationService(
            self.parent().kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_prepare: PreparationService создан")

        self._run_pipeline_step(
            service=service,
            target_method=service.prepare,
            kwargs={
                "fbs_files": self.fbs_files,
                "mp_files": self.mp_files,
            },
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_export_kiz,
        )

    @log_button_action("btn_export_kiz", "Ошибка в on_export_kiz: {e}")
    def on_export_kiz(self):
        """Шаг 2: выгрузка КИЗов из ЧЗ_МП и отчётов МП."""
        if not self._precheck_target_dir():
            return

        service = ExportKizService(
            self.parent().kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_export_kiz: ExportKizService создан")

        self._run_pipeline_step(
            service=service,
            target_method=service.export,
            kwargs={},
            start_message="Выгрузка КИЗов для обработки...",
            finish_message="Выгрузка завершена.",
            step_name="on_export_kiz",
            enable_after=self.btn_filter_prefinal,
        )

    @log_button_action("btn_filter_prefinal", "Ошибка в on_filter_prefinal: {e}")
    def on_filter_prefinal(self):
        """Шаг 3: фильтрация предитоговых файлов."""
        if not self._precheck_target_dir():
            return

        service = FilterPreFinalService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_filter_prefinal: FilterPreFinalService создан"
            )

        self._run_pipeline_step(
            service=service,
            target_method=service.filter_files,
            kwargs={},
            start_message="Фильтрация предитоговых файлов...",
            finish_message="Сбор данных завершён.",
            step_name="on_filter_prefinal",
            enable_after=self.btn_generate_sales,
        )

    @log_button_action("btn_generate_sales", "Ошибка в on_generate_sales: {e}")
    def on_generate_sales(self):
        """Шаг 4: формирование файлов продаж между продавцами."""
        if not self._precheck_target_dir():
            return

        service = GenerateSalesService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_generate_sales: GenerateSalesService создан"
            )

        self._run_pipeline_step(
            service=service,
            target_method=service.generate,
            kwargs={},
            start_message="Формирование файлов продаж...",
            finish_message="Продажи сформированы.",
            step_name="on_generate_sales",
            enable_after=self.btn_finalize_prices,
        )

    @log_button_action("btn_finalize_prices", "Ошибка в on_finalize_prices: {e}")
    def on_finalize_prices(self):
        """Шаг 5: установка цен и финализация ИТОГ-файлов."""
        if not self._precheck_target_dir():
            return

        saved_prices = self.parent().main_config.get("seller_prices", {})

        service = FinalizePricesService(
            self.parent().kiz_validator,
            self.log_manager_v2,
            price_requester=self._request_average_price,
        )
        if self.logger:
            self.logger.debug(
                "on_finalize_prices: FinalizePricesService создан"
            )

        self._run_pipeline_step(
            service=service,
            target_method=service.finalize,
            kwargs={"saved_prices": saved_prices},
            start_message="Внесение цен и финализация...",
            finish_message="Цены установлены, файлы финализированы.",
            step_name="on_finalize_prices",
            enable_after=None,
        )

    @log_button_action("btn_prices", "Ошибка при открытии окна цен: {e}")
    def on_open_prices_window(self):
        """Открывает окно редактирования сохранённых цен.

        Роль: диалог синхронный, потока нет. Ошибка — в critical.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return
        window = PricesEditWindow(
            self,
            sellers_brands_service=self.parent().sellers_brands_service,
            main_config=self.parent().main_config,
        )
        window.exec()

    def _request_average_price(self, seller_name: str) -> int | None:
        """Callback от FinalizePricesService: спросить цену у пользователя.

        Вход:
            seller_name — имя продавца (для текста диалога).

        Выход:
            int — цена, введённая пользователем; None — отмена.

        Роль:
            Вызывается из фонового потока сервиса. Если текущий
            поток — главный (UI), открывает диалог напрямую.
            Иначе — через QMetaObject.invokeMethod с
            BlockingQueuedConnection: фон ждёт, пока главный поток
            выполнит слот _show_price_dialog_slot, в котором
            открывается диалог и результат пишется в self._price_response.
        """
        # Сброс предыдущего ответа — чтобы случайно не вернуть
        # цену из прошлого вызова.
        self._price_response = None

        app = QApplication.instance()
        if app is None:
            # Qt не запущен — сервис работает вне UI, диалог
            # показать не можем. Возвращаем None: сервис пропустит
            # продавца, как если бы пользователь отменил.
            return None

        if QThread.currentThread() == app.thread():
            # Мы уже в UI-потоке — открываем напрямую.
            self._show_price_dialog_slot(seller_name)
        else:
            # Фоновый поток — переключаемся в главный через
            # BlockingQueuedConnection. Слот выполнится в главном
            # потоке, а мы дождёмся его завершения.
            QMetaObject.invokeMethod(
                self,
                "_show_price_dialog_slot",
                Qt.BlockingQueuedConnection,
                Q_ARG(str, seller_name),
            )
        return self._price_response

    @Slot(str)
    def _show_price_dialog_slot(self, seller_name: str) -> None:
        """Открывает диалог ввода средней цены в UI-потоке.

        Вход:
            seller_name — имя продавца.

        Выход: нет.

        Роль:
            Выполняется в главном потоке. Открывает
            AveragePriceInputDialog, ждёт результата через .exec()
            (не .exec_() — тот deprecated), сохраняет цену
            в self._price_response.
        """
        dialog = AveragePriceInputDialog(self, seller_name)
        if dialog.exec():
            self._price_response = dialog.get_price()
        else:
            self._price_response = None

    @log_button_action("btn_accumulate_sales", "Ошибка в on_accumulate_sales: {e}")
    def on_accumulate_sales(self):
        """Отдельная операция: аккумуляция продаж из ЧЗ_МП и Возвратов."""
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return
        self.status_display.clear()
        self.status_display.append("Аккумуляция продаж...")
        service = SalesAccumulatorService()
        if self.logger:
            self.logger.debug("on_accumulate_sales: SalesAccumulatorService создан")

        def on_finished():
            self.status_display.append("Аккумуляция завершена.")
            if self.logger:
                self.logger.debug("on_accumulate_sales: фоновый поток завершён")

        def on_error(e):
            self.status_display.append(f"Ошибка аккумуляции: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в on_accumulate_sales: {e}", can_influence=False,
                )

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "chz"),
            on_finished=on_finished,
            error_callback=on_error
        )

    def cleanup(self):
        """Сброс состояния окна (файлы, списки, подписи)."""
        self.fbs_files = []
        self.mp_files = []
        self.list_fbs.clear()
        self.list_reports.clear()
        self.fbs_signatures = []

    def closeEvent(self, event):
        """Обработка закрытия окна.

        Роль: пишет debug, чистит состояние, снимает active_child
              у родителя.
        """
        if self.logger:
            self.logger.debug("ChzMPWindow: closeEvent получен")
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()