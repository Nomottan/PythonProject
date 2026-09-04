from pathlib import Path
from datetime import date
from openpyxl import load_workbook

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QTextEdit
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from ui.factories.factories import (
    LabelFactory, ListWidgetFactory, ButtonFactory, LayoutFactory,
    FileDialogFactory, ThreadFactory, WindowFactory
)
from ui.widgets.path_selector import PathSelector
from ui.windows.shared_dialogs import PricesEditWindow

from services.sells_fbs_service import (
    PreparationService, ExportKizService, FilterPreFinalService,
    GenerateSalesService, FinalizePricesService
)
from services.sales_accumulator import SalesAccumulatorService

from utils.logger import ILogger, CompositeLogger, FileLogger, QtStatusLogger
from utils.path_utils import AppPaths
from utils.process_controller import ProcessController
from utils.state_manager import ButtonState


class ChzMPWindow(QMainWindow):
    """Окно подготовки к списанию проданных КИЗов (ЧЗ МП)."""

    def __init__(self, parent=None, logger: ILogger = None, app_paths: AppPaths = None):
        super().__init__(parent)
        self.main_window = parent

        # ---- Настройка логгера ----
        if logger is not None:
            self.logger = logger
        else:
            self.logger = CompositeLogger()
            debug_logger = FileLogger(
                (app_paths or AppPaths()).get_logs_path() / "debug.log",
                level="debug"
            )
            self.logger.add_logger(debug_logger)
            self.ui_logger = QtStatusLogger(min_level=1)
            self.ui_logger.log_signal.connect(self._on_log_message)
            self.logger.add_logger(self.ui_logger)

        self.app_paths = app_paths or AppPaths()

        # Переменные состояния (используются в методах действий)
        self.target_dir = parent.config.get("target_dir", None)
        self.fbs_files = []
        self.mp_files = []
        self.fbs_signatures = []
        self.sellers = parent.config.get_sellers_objects()

        # ---- Создаём контроллер процесса ----
        self.controller = ProcessController(
            process_name="ЧЗ_МП",
            target_dir=self.target_dir,
            config_manager=parent.config,
            logger=self.logger,
            parent_widget=self
        )

        # Подписываемся на сигналы контроллера
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.log_message.connect(self._on_log_message)
        self.controller.open_folder.connect(self._on_open_folder)

        # ---- Настройка окна ----
        main_layout = WindowFactory.setup_child_window(
            self, "Списание проданных КИЗов",
            bg_color=(45, 70, 65, 0.95)
        )

        # ============================================================
        # ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ UI
        # ============================================================

        # Кнопки-индикаторы выбора файлов
        _indicator_configs = [
            ("btn_fbs", "Отчёты с FBS", (30, 20, 35, 0.3)),
            ("btn_reports", "Отчёты с МП", (30, 20, 35, 0.3)),
        ]
        ButtonFactory.create_buttons_from_config(self, _indicator_configs)

        # Списки файлов
        self.list_fbs = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=110,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10
        )
        self.list_reports = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=110,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10
        )

        # Описание процесса
        self.desc_label = LabelFactory.create_label(
            self,
            text="Подготовка отчётов по продавцам для вывода КИЗов из оборота\n"
                 "Шаг 1: загрузи файлы и отчёты\n"
                 "Шаг 2: Нажми Подготовка. Файлы будут скопированы в рабочую директорию \n"
                 "Шаг 3: Нажми Выгрузка для обработки. Будут созданы текстовые файлы\n"
                 "Проведи все файлы через BestMark в Excell файлы сохранив названия\n"
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

        # ---- Статусная область ----
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 20, 35, 0.3);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 5px;
                padding: 5px;
                font-family: Consolas, monospace;
                font-size: 10px;
            }
        """)
        self.status_display.setMaximumHeight(200)
        self.status_display.setMinimumHeight(100)

        # ---- Кнопки действий (шаги процесса) ----
        # Они создаются через фабрику, затем мы их получим и зарегистрируем в контроллере
        _action_configs = [
            ("btn_prepare",          "Подготовка",             (10, 40, 160),  "8px 16px", (180, 35)),
            ("btn_export_kiz",       "Выгрузка для обработки", (40, 130, 130),  "8px 16px", (180, 35)),
            ("btn_filter_prefinal",  "Сбор данных",            (70, 160, 100), "8px 16px", (180, 35)),
            ("btn_generate_sales",   "Продажи",                (100, 160, 70),   "8px 16px", (180, 35)),
            ("btn_finalize_prices",  "Установка цен",          (130, 130, 40),  "8px 16px", (180, 35)),
            ("btn_prices",           "Цены",                   (40, 40, 40),  "2px 2px", (35, 20)),
        ]
        _action_handlers = {}  # Будем подключать через контроллер, поэтому обработчики пустые
        ButtonFactory.create_buttons_from_config(self, _action_configs, _action_handlers)

        # Кнопка "Собрать продажи" (отдельное действие)
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35)
        )
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)

        # ============================================================
        # МАКЕТ
        # ============================================================
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        headers_container = LayoutFactory.create_row(
            self, self.btn_fbs, self.btn_reports,
            fixed_width=365
        )
        center_layout.addWidget(headers_container, alignment=Qt.AlignCenter)

        lists_container = LayoutFactory.create_row(
            self, self.list_fbs, self.list_reports,
            fixed_width=365
        )
        center_layout.addWidget(lists_container, alignment=Qt.AlignCenter)

        center_layout.addWidget(self.desc_label)
        center_layout.addWidget(self.path_selector)

        row1 = LayoutFactory.create_row(
            self, self.btn_prepare, self.btn_export_kiz, self.btn_filter_prefinal,
            spacing=8
        )
        center_layout.addWidget(row1)

        row2 = LayoutFactory.create_row(
            self, self.btn_generate_sales, self.btn_finalize_prices, self.btn_prices,
            spacing=8
        )
        center_layout.addWidget(row2)

        center_layout.addWidget(self.status_display)

        # Кнопка "Собрать продажи"
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)

        center_layout.addStretch(1)
        main_layout.addLayout(center_layout)

        # ============================================================
        # РЕГИСТРАЦИЯ ШАГОВ В КОНТРОЛЛЕРЕ
        # ============================================================
        self._register_steps()

        # Подключаем кнопки к контроллеру (кроме "Цены" и "Собрать продажи")
        self.btn_prepare.clicked.connect(lambda: self.controller.on_button_clicked("prepare"))
        self.btn_export_kiz.clicked.connect(lambda: self.controller.on_button_clicked("export_kiz"))
        self.btn_filter_prefinal.clicked.connect(lambda: self.controller.on_button_clicked("filter_prefinal"))
        self.btn_generate_sales.clicked.connect(lambda: self.controller.on_button_clicked("generate_sales"))
        self.btn_finalize_prices.clicked.connect(lambda: self.controller.on_button_clicked("finalize_prices"))

        # Кнопка "Цены" — отдельное действие, не входит в цепочку
        self.btn_prices.clicked.connect(self.on_open_prices_window)

        # Подключаем кнопки выбора файлов
        self.btn_fbs.clicked.connect(self.select_fbs_files)
        self.btn_reports.clicked.connect(self.select_report_files)

        # Стартовое сообщение
        self.logger.info("Окно ЧЗ МП готово к работе.")

    # ============================================================
    # РЕГИСТРАЦИЯ ШАГОВ
    # ============================================================
    def _register_steps(self):
        """Регистрирует шаги процесса в контроллере."""
        checker = self.controller.condition_checker

        # 1. Подготовка (первый шаг, всегда активен при наличии файлов)
        self.controller.register_step(
            step_id="prepare",
            button_text="Подготовка",
            condition_func=lambda: (bool(self.fbs_files or self.mp_files), ""),
            action_func=self._do_prepare,
            action_kwargs={
                "fbs_files": self.fbs_files,
                "mp_files": self.mp_files,
                "sellers": self.sellers
            },
            is_first=True
        )

        # 2. Выгрузка для обработки
        self.controller.register_step(
            step_id="export_kiz",
            button_text="Выгрузка для обработки",
            condition_func=checker.can_export_kiz_chz,
            action_func=self._do_export_kiz,
            action_kwargs={"sellers": self.sellers},
            depends_on=["prepare"]
        )

        # 3. Сбор данных (фильтрация предитоговых)
        self.controller.register_step(
            step_id="filter_prefinal",
            button_text="Сбор данных",
            condition_func=checker.can_filter_prefinal_chz,
            action_func=self._do_filter_prefinal,
            action_kwargs={"sellers": self.sellers},
            depends_on=["export_kiz"]
        )

        # 4. Продажи
        self.controller.register_step(
            step_id="generate_sales",
            button_text="Продажи",
            condition_func=checker.can_generate_sales_chz,
            action_func=self._do_generate_sales,
            action_kwargs={"sellers": self.sellers},
            depends_on=["filter_prefinal"]
        )

        # 5. Установка цен (финальный шаг)
        self.controller.register_step(
            step_id="finalize_prices",
            button_text="Установка цен",
            condition_func=checker.can_finalize_prices_chz,
            action_func=self._do_finalize_prices,
            action_kwargs={
                "sellers": self.sellers,
                "saved_prices": self.main_window.config.get("seller_prices", {})
            },
            depends_on=["generate_sales"],
            is_final=True,
            auto_open_folder=True
        )

    # ============================================================
    # МЕТОДЫ ДЕЙСТВИЙ (вызываются контроллером)
    # ============================================================
    def _do_prepare(self, fbs_files: list, mp_files: list, sellers):
        """Запускает подготовку (копирование файлов)."""
        service = PreparationService(self.logger, self.controller.run_manager)
        service.prepare(
            target_dir=self.target_dir,
            fbs_files=fbs_files,
            mp_files=mp_files,
            sellers=sellers
        )

    def _do_export_kiz(self, sellers):
        """Запускает выгрузку КИЗов для обработки."""
        service = ExportKizService(self.logger, self.controller.run_manager)
        service.export(self.target_dir, sellers)

    def _do_filter_prefinal(self, sellers):
        """Запускает фильтрацию предитоговых файлов."""
        service = FilterPreFinalService(self.logger, self.controller.run_manager)
        service.filter_files(self.target_dir, sellers)

    def _do_generate_sales(self, sellers):
        """Запускает формирование файлов продаж."""
        service = GenerateSalesService(self.logger, self.controller.run_manager)
        service.generate(self.target_dir, sellers)

    def _do_finalize_prices(self, sellers, saved_prices: dict):
        """Запускает установку цен и финализацию."""
        service = FinalizePricesService(self.logger, self.controller.run_manager)
        updated_prices = service.finalize(self.target_dir, sellers, saved_prices)
        # Сохраняем обновлённые цены в конфиг
        if updated_prices:
            self.main_window.config.set("seller_prices", updated_prices)

    # ============================================================
    # ОБРАБОТЧИКИ СИГНАЛОВ КОНТРОЛЛЕРА
    # ============================================================
    def _on_state_changed(self, step_id: str, old_state: ButtonState, new_state: ButtonState):
        """Обновляет внешний вид кнопки в соответствии с состоянием."""
        button_map = {
            "prepare": self.btn_prepare,
            "export_kiz": self.btn_export_kiz,
            "filter_prefinal": self.btn_filter_prefinal,
            "generate_sales": self.btn_generate_sales,
            "finalize_prices": self.btn_finalize_prices,
        }
        btn = button_map.get(step_id)
        if not btn:
            return

        config = self.controller.state_manager.steps.get(step_id)
        if not config:
            return

        # Сбрасываем стандартный стиль и enable
        btn.setEnabled(True)
        btn.setStyleSheet("")

        if new_state == ButtonState.GRAY:
            btn.setStyleSheet("background-color: rgba(80, 80, 80, 0.5); color: #666;")
            btn.setText(config.button_text)
        elif new_state == ButtonState.ACTIVE:
            btn.setStyleSheet("")  # стандартный стиль из фабрики
            btn.setText(config.button_text)
        elif new_state == ButtonState.EXECUTED:
            btn.setStyleSheet("background-color: rgb(60, 150, 80); color: white; font-weight: bold;")
            btn.setText(config.button_text_executed)
        elif new_state == ButtonState.LOCKED:
            btn.setEnabled(False)
            btn.setText("Выполняется...")

    def _on_log_message(self, msg: str, level: int):
        """Выводит сообщение в статусную область."""
        self.status_display.append(msg)

    def _on_open_folder(self, path: str):
        """Открывает папку в проводнике."""
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ============================================================
    # ОБРАБОТЧИКИ UI (выбор файлов, изменение папки и т.д.)
    # ============================================================
    def _on_target_dir_changed(self, new_path):
        self.target_dir = new_path
        self.parent().config.set("target_dir", new_path)
        self.logger.info(f"Целевая папка обновлена: {new_path}")
        # Обновляем состояние кнопок через контроллер
        self.controller.state_manager.update_all()

    def select_fbs_files(self):
        start = self.parent().config.get("last_fbs_dir", None)
        files = FileDialogFactory.open_files_dialog(self, "Выберите файлы ЧЗ МП", start)
        if not files:
            return
        first_file = Path(files[0])
        self.parent().config.set("last_fbs_dir", str(first_file.parent))

        for f in files:
            # Проверка на дубликат по сигнатуре первой ячейки
            try:
                wb = load_workbook(f, data_only=True)
                sheet = wb.active
                first_row = sheet[1] if sheet.max_row >= 1 else None
                first_val = first_row[0].value if first_row and first_row[0].value else ""
                wb.close()
            except Exception:
                first_val = ""

            if first_val in self.fbs_signatures:
                QMessageBox.warning(
                    self,
                    "Дубликат",
                    f"Файл {Path(f).name} уже выбран (совпадает первая строка). Дубль не был добавлен"
                )
                continue

            self.fbs_files.append(f)
            self.fbs_signatures.append(first_val)
            self.list_fbs.addItem(Path(f).name)

        # После выбора файлов обновляем состояние кнопок
        self.controller.state_manager.update_all()

    def select_report_files(self):
        start = self.parent().config.get("last_mp_dir", None)
        files = FileDialogFactory.open_files_dialog(self, "Выберите файлы отчётов МП", start)
        if files:
            first_file = Path(files[0])
            self.parent().config.set("last_mp_dir", str(first_file.parent))
            self.mp_files = files
            self.list_reports.clear()
            for f in files:
                self.list_reports.addItem(Path(f).name)
            # После выбора файлов обновляем состояние кнопок
            self.controller.state_manager.update_all()

    def on_open_prices_window(self):
        """Открывает окно для редактирования сохранённых цен."""
        if not self.target_dir:
            self.logger.info("Сначала выберите целевую папку")
            return
        window = PricesEditWindow(self, self.main_window.config)
        window.exec()

    def on_accumulate_sales(self):
        """Запускает аккумуляцию продаж (отдельная кнопка)."""
        if not self.target_dir:
            self.logger.info("Сначала выберите целевую папку")
            return

        self.logger.info("Аккумуляция продаж...")
        service = SalesAccumulatorService()

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "chz"),
            on_finished=lambda: self.logger.info("Аккумуляция завершена."),
            error_callback=lambda e: self.logger.error(f"Ошибка аккумуляции: {e}")
        )

    # ============================================================
    # ЗАКРЫТИЕ ОКНА
    # ============================================================
    def cleanup(self):
        self.fbs_files = []
        self.mp_files = []
        self.list_fbs.clear()
        self.list_reports.clear()
        self.fbs_signatures = []

    def closeEvent(self, event):
        # Сохраняем состояние через контроллер
        self.controller.shutdown()
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()