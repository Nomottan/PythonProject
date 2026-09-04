from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QMessageBox
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory, FileDialogFactory,
    ThreadFactory, WindowFactory
)
from ui.widgets.path_selector import PathSelector

from services.returns_service import (
    ReturnsPreparationService,
    KizExportService,
    KizTransferService
)
from services.sales_accumulator import SalesAccumulatorService

from utils.logger import ILogger, CompositeLogger, FileLogger, QtStatusLogger
from utils.path_utils import AppPaths
from utils.process_controller import ProcessController
from utils.state_manager import ButtonState


class ReturnsWindow(QMainWindow):
    """Окно подготовки возвратов в оборот с управлением состоянием кнопок."""

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

        # Переменные состояния (будут использоваться в методах действий)
        self.target_dir = parent.config.get("target_dir", None)
        self.source_file = None
        self.sellers = parent.config.get_sellers_with_brands()

        # ---- Создаём контроллер процесса ----
        self.controller = ProcessController(
            process_name="Возвраты",
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
            self, "Подготовка возвратов в оборот",
            bg_color=(30, 30, 50, 0.9)
        )

        # ============================================================
        # ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ UI
        # ============================================================

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

        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку"
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        # Кнопки процесса
        self.btn_prepare = ButtonFactory.create_button(
            self, "Подготовка", (26, 72, 118),
            padding="6px 12px", fixed_size=(180, 35)
        )
        # Подключаем к контроллеру позже, после регистрации шагов

        self.btn_export_kiz = ButtonFactory.create_button(
            self, "Выгрузить КИЗы", (53, 34, 28),
            padding="8px 16px", fixed_size=(220, 35)
        )

        self.btn_prepare_transfer = ButtonFactory.create_button(
            self, "Подготовить передачу", (83, 54, 58),
            padding="8px 16px", fixed_size=(220, 35)
        )

        # Кнопка "Собрать продажи" (не входит в основной процесс)
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35)
        )
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)

        # Статусная область
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
        self.status_display.setMaximumHeight(150)
        self.status_display.setMinimumHeight(80)

        # ============================================================
        # МАКЕТ
        # ============================================================
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        center_layout.addWidget(self.header_label)

        file_row = LayoutFactory.create_row(
            self, self.btn_choose_file, self.file_label, spacing=5
        )
        center_layout.addWidget(file_row)

        center_layout.addWidget(self.path_selector)

        # Кнопка "Подготовка"
        prepare_layout = QHBoxLayout()
        prepare_layout.addStretch()
        prepare_layout.addWidget(self.btn_prepare)
        prepare_layout.addStretch()
        center_layout.addLayout(prepare_layout)

        center_layout.addWidget(self.status_display)

        # Кнопки "Выгрузить КИЗы" и "Подготовить передачу"
        bottom_row = LayoutFactory.create_row(
            self, self.btn_export_kiz, self.btn_prepare_transfer, spacing=20
        )
        center_layout.addWidget(bottom_row)

        center_layout.addStretch(1)

        # Кнопка "Собрать продажи"
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)

        main_layout.addLayout(center_layout)

        # ============================================================
        # РЕГИСТРАЦИЯ ШАГОВ В КОНТРОЛЛЕРЕ
        # ============================================================
        self._register_steps()

        # Подключаем кнопки к контроллеру
        self.btn_prepare.clicked.connect(
            lambda: self.controller.on_button_clicked("prepare")
        )
        self.btn_export_kiz.clicked.connect(
            lambda: self.controller.on_button_clicked("export_kiz")
        )
        self.btn_prepare_transfer.clicked.connect(
            lambda: self.controller.on_button_clicked("prepare_transfer")
        )

        # Стартовое сообщение
        self.logger.info("Окно возвратов готово к работе.")

    # ============================================================
    # РЕГИСТРАЦИЯ ШАГОВ
    # ============================================================
    def _register_steps(self):
        from ui.instructions.returns_instruction import ReturnsInstruction

        self.controller.register_step(
            step_id="prepare",
            button_text="Подготовка",
            condition_func=lambda: ReturnsInstruction.can_prepare(self.source_file),
            action_func=self._do_prepare,
            is_first=True
        )

        self.controller.register_step(
            step_id="export_kiz",
            button_text="Выгрузить КИЗы",
            condition_func=lambda: ReturnsInstruction.can_export_kiz(self.controller.run_manager),
            action_func=self._do_export_kiz,
            depends_on=["prepare"]
        )

        self.controller.register_step(
            step_id="prepare_transfer",
            button_text="Подготовить передачу",
            condition_func=lambda: ReturnsInstruction.can_prepare_transfer(self.controller.run_manager),
            action_func=self._do_prepare_transfer,
            depends_on=["prepare"],  # <-- тоже зависит только от prepare
            is_final=True,
            auto_open_folder=True
        )

    # ============================================================
    # МЕТОДЫ ДЕЙСТВИЙ (вызываются контроллером)
    # ============================================================
    def _do_prepare(self, target_dir: str, source_file: str, sellers):
        """Запускает подготовку возвратов."""
        if not source_file:
            self.logger.warning("Файл не выбран")
            return
        service = ReturnsPreparationService(self.logger, self.controller.run_manager)
        service.prepare(target_dir, source_file, sellers)

    def _do_export_kiz(self, target_dir: str):
        """Запускает выгрузку КИЗов."""
        service = KizExportService(self.logger, self.controller.run_manager)
        service.export(target_dir)

    def _do_prepare_transfer(self, target_dir: str, sellers):
        """Запускает подготовку передач КИЗов."""
        service = KizTransferService(self.logger, self.controller.run_manager)
        service.prepare_transfer(target_dir, sellers)

    # ============================================================
    # ОБРАБОТЧИКИ СИГНАЛОВ КОНТРОЛЛЕРА
    # ============================================================
    def _on_state_changed(self, step_id: str, old_state: ButtonState, new_state: ButtonState):
        """Обновляет внешний вид кнопки в соответствии с состоянием."""
        button_map = {
            "prepare": self.btn_prepare,
            "export_kiz": self.btn_export_kiz,
            "prepare_transfer": self.btn_prepare_transfer
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
        # Обновляем состояние кнопок (контроллер сам пересчитает условия)
        self.controller.state_manager.update_all()

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
            self.logger.info(f"Выбран файл: {Path(file_path).name}")
            # После выбора файла обновляем состояние кнопок
            self.controller.state_manager.update_all()

    def on_accumulate_sales(self):
        """Запускает аккумуляцию продаж (отдельная кнопка, не входит в процесс)."""
        if not self.target_dir:
            self.logger.info("Сначала выберите целевую папку.")
            return

        self.logger.info("Аккумуляция продаж...")
        service = SalesAccumulatorService()

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "returns"),
            on_finished=lambda: self.logger.info("Аккумуляция завершена."),
            error_callback=lambda e: self.logger.error(f"Ошибка аккумуляции: {e}")
        )

    # ============================================================
    # ЗАКРЫТИЕ ОКНА
    # ============================================================
    def cleanup(self):
        self.source_file = None
        self.file_label.setText("Файл не выбран")

    def closeEvent(self, event):
        # Сохраняем состояние через контроллер
        self.controller.shutdown()
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()