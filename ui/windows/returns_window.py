from ui.factories.factories import ButtonFactory, LabelFactory, LayoutFactory, FileDialogFactory, ThreadFactory, WindowFactory
from ui.widgets.path_selector import PathSelector
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QTextEdit
)
from pathlib import Path
from PySide6.QtCore import Qt
from services.returns_service import ReturnsPreparationService, KizExportService, KizTransferService
from services.sales_accumulator import SalesAccumulatorService

class ReturnsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_dir = parent.config.get("target_dir", None)
        self.source_file = None

        main_layout = WindowFactory.setup_child_window(
            self, "Подготовка возвратов в оборот",
            bg_color=(50, 70, 80, 0.9)
        )

        # ---------- ЭЛЕМЕНТЫ ----------
        self.btn_choose_file = ButtonFactory.create_button(
            self, "Выбрать файл", (100, 120, 100, 0.8)
        )
        self.btn_choose_file.clicked.connect(self.select_source_file)

        self.header_label = LabelFactory.create_label(
            self,
            text="Подготовка возвратов\n"
                "Подготовь файл, он должен быть определенного формата\n"
                "Прогони коды через BestMark и сделай импорт в Excell\n"
                "С этим файлом всё работать будет\n"
                "Прежде чем продавать в ЭДО верни КИЗы в оборот",
            bg_color=(35, 50, 60, 0.9),
            text_color="#e0e0e0",
            padding="6px",
            border_radius=5,
            alignment=Qt.AlignCenter,
            font_size=14,
            word_wrap=True
        )

        self.file_label = LabelFactory.create_label(
            self, "Файл не выбран",
            bg_color=(64, 48, 66, 128),
            text_color="#d4d4d4",
            padding="4px 8px",
            border_radius=5,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_family="Consolas, monospace",
            font_size=10
        )

        # Виджет выбора пути
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку"
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        self.btn_prepare = ButtonFactory.create_button(
            self, "Подготовка", (26, 72, 118),
            padding="6px 12px", fixed_size=(180, 35)
        )
        self.btn_prepare.clicked.connect(self.on_prepare)

        self.status_label = LabelFactory.create_status_label(
            self, "Выберите файл и целевую папку"
        )

        self.btn_export_kiz = ButtonFactory.create_button(
            self, "Выгрузить КИЗы для возврата", (53, 34, 28),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_export_kiz.clicked.connect(self.on_export_kiz)

        self.btn_prepare_transfer = ButtonFactory.create_button(
            self, "Подготовить КИЗы для передачи", (83, 54, 58),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_prepare_transfer.clicked.connect(self.on_prepare_transfer)

        # ---------- МАКЕТ ----------
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        center_layout.addWidget(self.header_label)

        file_row = LayoutFactory.create_row(
            self, self.btn_choose_file, self.file_label, spacing=5
        )
        center_layout.addWidget(file_row)

        # Вместо path_row используем PathSelector напрямую
        center_layout.addWidget(self.path_selector)

        prepare_layout = QHBoxLayout()
        prepare_layout.addStretch()
        prepare_layout.addWidget(self.btn_prepare)
        prepare_layout.addStretch()
        center_layout.addLayout(prepare_layout)

        center_layout.addWidget(self.status_label)

        bottom_row = LayoutFactory.create_row(
            self, self.btn_export_kiz, self.btn_prepare_transfer, spacing=20
        )
        center_layout.addWidget(bottom_row)

        center_layout.addStretch(1)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35)
        )
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)
        main_layout.addLayout(center_layout)

    # ---------- МЕТОДЫ ----------
    def _on_target_dir_changed(self, new_path):
        self.target_dir = new_path
        self.parent().config.set("target_dir", new_path)
        self.status_label.setText("Целевая папка обновлена.")

    def select_source_file(self):
        start_dir = self.parent().config.get("last_returns_dir", None) or self.target_dir or str(Path.home())
        file_path = FileDialogFactory.open_file_dialog(
            self, "Выберите Excel-файл с возвратами",
            default_dir=start_dir,
            filter="Excel (*.xlsx)"
        )
        if file_path:
            self.source_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.parent().config.set("last_returns_dir", str(Path(file_path).parent))
            self.status_label.setText("Файл выбран. Нажмите «Подготовка».")

    def on_prepare(self):
        if not self.source_file:
            self.status_label.setText("Сначала выберите файл.")
            return
        if not self.target_dir:
            self.status_label.setText("Сначала выберите целевую папку.")
            return

        sellers = self.parent().config.get_sellers_with_brands()
        self.status_label.setText("Идёт подготовка...")

        service = ReturnsPreparationService()

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_choose_file", "btn_prepare",
                     "btn_export_kiz", "btn_prepare_transfer"],
            target_func=service.prepare,
            kwargs={
                "target_dir": self.target_dir,
                "source_file": self.source_file,
                "sellers": sellers,
                "log_callback": self.status_label.status_update.emit
            },
            on_finished=lambda: self.status_label.setText("Подготовка завершена."),
            error_callback=lambda e: self.status_label.status_update.emit(f"Ошибка: {e}")
        )

    def on_export_kiz(self):
        if not self.target_dir:
            self.status_label.setText("Сначала выберите целевую папку.")
            return

        self.status_label.setText("Выгрузка КИЗов...")
        service = KizExportService()

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_choose_file", "btn_prepare",
                     "btn_export_kiz", "btn_prepare_transfer"],
            target_func=service.export,
            kwargs={
                "target_dir": self.target_dir,
                "log_callback": self.status_label.status_update.emit
            },
            on_finished=lambda: self.status_label.setText("Выгрузка КИЗов завершена."),
            error_callback=lambda e: self.status_label.status_update.emit(f"Ошибка выгрузки: {e}")
        )

    def on_prepare_transfer(self):
        if not self.target_dir:
            self.status_label.setText("Сначала выберите целевую папку.")
            return

        sellers = self.parent().config.get_sellers_with_brands()
        self.status_label.setText("Подготовка передач КИЗов...")
        service = KizTransferService()

        ThreadFactory.create_thread(
            parent=self,
            buttons=["btn_choose_file", "btn_prepare",
                     "btn_export_kiz", "btn_prepare_transfer"],
            target_func=service.prepare_transfer,
            kwargs={
                "target_dir": self.target_dir,
                "sellers": sellers,
                "log_callback": self.status_label.status_update.emit
            },
            on_finished=lambda: self.status_label.setText("Подготовка передач КИЗов завершена."),
            error_callback=lambda e: self.status_label.status_update.emit(f"Ошибка подготовки передач: {e}")
        )

    def on_accumulate_sales(self):
        """Запускает аккумуляцию продаж из Возвратов и ЧЗ_МП."""
        if not self.target_dir:
            self.status_label.setText("Сначала выберите целевую папку")
            return
        self.status_label.setText("Аккумуляция продаж...")
        service = SalesAccumulatorService()

        def on_finished():
            self.status_label.setText("Аккумуляция завершена.")
            # Лог загружать некуда, можно просто вывести сообщение

        def on_error(e):
            self.status_label.setText(f"Ошибка аккумуляции: {e}")

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "returns"),
            on_finished=on_finished,
            error_callback=on_error
        )

    def cleanup(self):
        self.source_file = None
        self.file_label.setText("Файл не выбран")

    def closeEvent(self, event):
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()