from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt
from ui.factories.factories import (
    LabelFactory, ListWidgetFactory, ButtonFactory, LayoutFactory,
    FileDialogFactory, ThreadFactory, WindowFactory
)

from ui.widgets.path_selector import PathSelector
from ui.windows.shared_dialogs import PricesEditWindow
from services.sells_fbs_service import PreparationService, ExportKizService, FilterPreFinalService, GenerateSalesService, FinalizePricesService
from services.sales_accumulator import SalesAccumulatorService

from pathlib import Path
from datetime import date
from openpyxl import load_workbook

class ChzMPWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Переменные состояния
        self.target_dir = parent.config.get("target_dir", None)
        self.fbs_files = []
        self.mp_files = []
        self.fbs_signatures = []

        # Настройка окна через фабрику
        main_layout = WindowFactory.setup_child_window(
            self, "Списание проданных КИЗов",
            bg_color=(50, 60, 90, 0.95)
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

        # ---- СТАТУСНАЯ ОБЛАСТЬ (лог с прокруткой) ----
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

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================
    def _on_target_dir_changed(self, new_path):
        self.target_dir = new_path
        self.parent().config.set("target_dir", new_path)
        self.status_display.clear()
        self.status_display.append("Целевая папка обновлена.")
        self.btn_export_kiz.setEnabled(False)
        self.btn_filter_prefinal.setEnabled(False)
        self.btn_generate_sales.setEnabled(False)
        self.btn_finalize_prices.setEnabled(False)

    def select_fbs_files(self):
        start = self.parent().config.get("last_fbs_dir", None)
        files = FileDialogFactory.open_files_dialog(self, "Выберите файлы ЧЗ МП", start)
        if not files:
            return
        first_file = Path(files[0])
        self.parent().config.set("last_fbs_dir", str(first_file.parent))

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
                QMessageBox.warning(
                    self,
                    "Дубликат",
                    f"Файл {Path(f).name} уже выбран (совпадает первая строка). Дубль не был добавлен"
                )
                continue

            self.fbs_files.append(f)
            self.fbs_signatures.append(first_val)
            self.list_fbs.addItem(Path(f).name)

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

    def _get_log_path(self, log_filename):
        """Формирует путь к лог-файлу в рабочей папке."""
        if not self.target_dir:
            return None
        today = date.today()
        date_str = f"{today.day}_{today.month}_{today.year}"
        work_folder = Path(self.target_dir) / date_str / f"ЧЗ_МП_{date_str}"
        return work_folder / log_filename

    def _load_log_into_status(self, log_path):
        """Загружает содержимое лог-файла в статусную область."""
        self.status_display.clear()
        if not log_path or not Path(log_path).exists():
            self.status_display.append("Лог-файл не найден.")
            return
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.status_display.setPlainText(content)
        except Exception as e:
            self.status_display.append(f"Ошибка чтения лога: {e}")

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================
    def on_prepare(self):
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return
        if not self.fbs_files and not self.mp_files:
            self.status_display.append("Как насчёт добавить хоть один отчётик?")
            return

        sellers = self.parent().config.get_sellers_objects()
        self.status_display.clear()
        self.status_display.append("Идёт подготовка...")

        service = PreparationService()

        def on_finished():
            self.status_display.append("Подготовка завершена.")
            self.btn_export_kiz.setEnabled(True)
            log_path = self._get_log_path("log_подготовка.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка подготовки: {e}")

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_prepare", "btn_export_kiz", "btn_filter_prefinal",
                     "btn_generate_sales", "btn_finalize_prices",
                     "btn_fbs", "btn_reports"],
            target_func=service.prepare,
            kwargs={
                "target_dir": self.target_dir,
                "fbs_files": self.fbs_files,
                "mp_files": self.mp_files,
                "sellers": sellers,
                "log_callback": None
            },
            on_finished=on_finished,
            error_callback=on_error
        )

    def on_export_kiz(self):
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return

        sellers = self.parent().config.get_sellers_objects()
        self.status_display.clear()
        self.status_display.append("Выгрузка КИЗов для обработки...")

        service = ExportKizService(self.parent().kiz_validator)

        def on_finished():
            self.status_display.append("Выгрузка завершена.")
            self.btn_filter_prefinal.setEnabled(True)
            log_path = self._get_log_path("log_выгрузка_кизов.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка выгрузки: {e}")

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_prepare", "btn_export_kiz", "btn_filter_prefinal",
                     "btn_generate_sales", "btn_finalize_prices",
                     "btn_fbs", "btn_reports"],
            target_func=service.export,
            kwargs={
                "target_dir": self.target_dir,
                "sellers": sellers,
                "log_callback": None
            },
            on_finished=on_finished,
            error_callback=on_error
        )

    def on_filter_prefinal(self):
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return

        sellers = self.parent().config.get_sellers_objects()
        self.status_display.clear()
        self.status_display.append("Фильтрация предитоговых файлов...")

        service = FilterPreFinalService()

        def on_finished():
            self.status_display.append("Сбор данных завершён.")
            self.btn_generate_sales.setEnabled(True)
            log_path = self._get_log_path("log_фильтрация.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка фильтрации: {e}")

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_prepare", "btn_export_kiz", "btn_filter_prefinal",
                     "btn_generate_sales", "btn_finalize_prices",
                     "btn_fbs", "btn_reports"],
            target_func=service.filter_files,
            kwargs={
                "target_dir": self.target_dir,
                "sellers": sellers,
                "log_callback": None
            },
            on_finished=on_finished,
            error_callback=on_error
        )

    def on_generate_sales(self):
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return

        sellers = self.parent().config.get_sellers_objects()
        self.status_display.clear()
        self.status_display.append("Формирование файлов продаж...")

        service = GenerateSalesService()

        def on_finished():
            self.status_display.append("Продажи сформированы.")
            self.btn_finalize_prices.setEnabled(True)
            log_path = self._get_log_path("log_продажи.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка формирования продаж: {e}")

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_prepare", "btn_export_kiz", "btn_filter_prefinal",
                     "btn_generate_sales", "btn_finalize_prices",
                     "btn_fbs", "btn_reports"],
            target_func=service.generate,
            kwargs={
                "target_dir": self.target_dir,
                "sellers": sellers,
                "log_callback": None
            },
            on_finished=on_finished,
            error_callback=on_error
        )

    def on_finalize_prices(self):
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return

        sellers = self.parent().config.get_sellers_objects()
        saved_prices = self.parent().config.get("seller_prices", {})
        self.status_display.clear()
        self.status_display.append("Внесение цен и финализация...")

        service = FinalizePricesService(self.parent().kiz_validator)

        def on_finished():
            self.status_display.append("Цены установлены, файлы финализированы.")
            log_path = self._get_log_path("log_цены.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка установки цен: {e}")

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_prepare", "btn_export_kiz", "btn_filter_prefinal",
                     "btn_generate_sales", "btn_finalize_prices",
                     "btn_fbs", "btn_reports"],
            target_func=service.finalize,
            kwargs={
                "target_dir": self.target_dir,
                "sellers": sellers,
                "saved_prices": saved_prices,
                "log_callback": None
            },
            on_finished=on_finished,
            error_callback=on_error
        )

    def on_open_prices_window(self):
        """Открывает окно для редактирования сохранённых цен."""
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return
        config = self.parent().config
        window = PricesEditWindow(self, config)
        window.exec()

    def on_accumulate_sales(self):
        """Запускает аккумуляцию продаж из ЧЗ_МП и Возвратов."""
        if not self.target_dir:
            self.status_display.append("Сначала выберите целевую папку")
            return
        self.status_display.clear()
        self.status_display.append("Аккумуляция продаж...")
        service = SalesAccumulatorService()

        def on_finished():
            self.status_display.append("Аккумуляция завершена.")
            log_path = self._get_log_path("log_аккумуляция.txt")
            if log_path:
                self._load_log_into_status(log_path)

        def on_error(e):
            self.status_display.append(f"Ошибка аккумуляции: {e}")

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "chz"),
            on_finished=on_finished,
            error_callback=on_error
        )

    def cleanup(self):
        self.fbs_files = []
        self.mp_files = []
        self.list_fbs.clear()
        self.list_reports.clear()
        self.fbs_signatures = []

    def closeEvent(self, event):
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()