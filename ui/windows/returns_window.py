"""
Окно «Подготовка возвратов в оборот».

Назначение:
    Пайплайн из трёх шагов: подготовка (фильтрация исходного файла),
    выгрузка КИЗов для возврата, подготовка КИЗов для передачи
    между продавцами. Плюс отдельная операция — аккумуляция продаж
    из Возвратов и ЧЗ_МП в одну папку.

Роль в программе:
    Открывается из MainWindow. Сервисы возвратов получают
    log_manager_v2 и создают LoggerV2 в начале публичного метода.
    Окно ведёт свой логгер для собственных сообщений.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
    FileDialogFactory, ThreadFactory, WindowFactory, StatusLogFactory,
)
from ui.widgets.path_selector import PathSelector
from services.returns_service import (
    ReturnsPreparationService, KizExportService, KizTransferService,
)
from services.sales_accumulator import SalesAccumulatorService
from utils.log_tools.decorators import log_button_action


class ReturnsWindow(QMainWindow):
    """Окно пайплайна возвратов.

    Роль:
        Объединяет три шага обработки возвратов. Каждый шаг —
        отдельный сервис, запускается в фоновом потоке через
        ThreadFactory. Логи шагов идут в status_log; короткие
        подсказки — в status_label.
    """

    # Кнопки, блокируемые на время фонового потока пайплайна.
    # btn_accumulate сюда не входит: это отдельная операция,
    # её во время шага блокировать не нужно.
    PIPELINE_BUTTONS = (
        "btn_choose_file",
        "btn_prepare",
        "btn_export_kiz",
        "btn_prepare_transfer",
    )

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None. Если None —
                             logger остаётся None, окно работает
                             без логирования.

        Роль: сохраняет менеджер логирования и создаёт логгер
              окна. Настраивает раскладку и подключает сигналы.
        """
        super().__init__(parent)
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source="ReturnsWindow.returns_window",
                domain="returns",
            )
        if self.logger:
            self.logger.debug("ReturnsWindow.__init__: старт")

        self.target_dir = parent.main_config.get("target_dir", None)
        self.source_file = None
        self.bg_color = (70, 60, 70, 0.95)

        main_layout = WindowFactory.setup_child_window(
            self, "Подготовка возвратов в оборот",
            bg_color=self.bg_color,
        )

        # ---------- ЭЛЕМЕНТЫ ----------
        self.btn_choose_file = ButtonFactory.create_button(
            self, "Выбрать файл", (120, 90, 120, 0.8)
        )
        self.btn_choose_file.clicked.connect(self.select_source_file)

        self.header_label = LabelFactory.create_label(
            self,
            text="Подготовка возвратов\n"
                "Подготовь файл, он должен быть определенного формата\n"
                "Прогони коды через BestMark и сделай импорт в Excell\n"
                "С этим файлом всё работать будет\n"
                "Прежде чем продавать в ЭДО верни КИЗы в оборот",
            bg_color=(35, 50, 60, 0),
            text_color="#e0e0e0",
            padding="6px",
            border_radius=5,
            alignment=Qt.AlignCenter,
            font_size=14,
            word_wrap=True,
        )

        self.file_label = LabelFactory.create_label(
            self, "Файл не выбран",
            bg_color=(64, 48, 66, 128),
            text_color="#d4d4d4",
            padding="4px 8px",
            border_radius=5,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_family="Consolas, monospace",
            font_size=10,
        )

        # Виджет выбора пути.
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку",
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        self.btn_prepare = ButtonFactory.create_button(
            self, "Подготовка", (100, 50, 100),
            padding="6px 12px", fixed_size=(180, 35),
        )
        self.btn_prepare.clicked.connect(self.on_prepare)

        self.status_label = LabelFactory.create_status_label(
            self, "Выберите файл и целевую папку"
        )
        self.status_log = StatusLogFactory.create_status_log(
            self, min_height=100, max_height=200,
        )

        self.btn_export_kiz = ButtonFactory.create_button(
            self, "Выгрузить КИЗы для возврата", (130, 50, 100),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_export_kiz.clicked.connect(self.on_export_kiz)

        self.btn_prepare_transfer = ButtonFactory.create_button(
            self, "Подготовить КИЗы для передачи", (100, 50, 70),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_prepare_transfer.clicked.connect(self.on_prepare_transfer)

        # Гейтинг: шаги 2 и 3 недоступны до подготовки.
        self.btn_export_kiz.setEnabled(False)
        self.btn_prepare_transfer.setEnabled(False)

        # ---------- МАКЕТ ----------
        center_layout = QVBoxLayout()
        center_layout.setSpacing(10)
        center_layout.setAlignment(Qt.AlignCenter)

        center_layout.addWidget(self.header_label)

        file_row = LayoutFactory.create_row(
            self, self.btn_choose_file, self.file_label, spacing=5
        )
        center_layout.addWidget(file_row)

        center_layout.addWidget(self.path_selector)

        prepare_layout = QHBoxLayout()
        prepare_layout.addWidget(self.btn_prepare)
        center_layout.addLayout(prepare_layout)

        center_layout.addWidget(self.status_label)

        bottom_row = LayoutFactory.create_row(
            self, self.btn_export_kiz, self.btn_prepare_transfer, spacing=20
        )
        center_layout.addWidget(bottom_row)

        # Лог статуса — там же, где в ChzMPWindow: после кнопок
        # действий, до кнопки «Собрать продажи».
        center_layout.addWidget(self.status_log)

        center_layout.addStretch(1)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(160, 35),
        )
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)
        bottom_layout.addWidget(self.btn_accumulate)
        center_layout.addLayout(bottom_layout)

        main_layout.addLayout(center_layout)

        if self.logger:
            self.logger.debug("ReturnsWindow.__init__: окно инициализировано")

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================

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
        Роль: единая точка записи в status_log. Вызывается
              из InfoUIHandler через active_child.set_info.
        """
        self.status_log.log(msg)

    def _on_target_dir_changed(self, new_path) -> None:
        """Обработка смены целевой папки.

        Вход: new_path — новый путь.
        Роль: обновляет target_dir, пишет в main_config,
              сбрасывает кнопки шагов 2–3 до готовности.
        """
        if self.logger:
            self.logger.debug(
                f"_on_target_dir_changed: новая папка {new_path}"
            )
        self.target_dir = new_path
        self.parent().main_config.set("target_dir", new_path)
        self.set_status("Целевая папка обновлена.")
        self.btn_export_kiz.setEnabled(False)
        self.btn_prepare_transfer.setEnabled(False)

    def _precheck_target_dir(self) -> bool:
        """Проверяет, что выбрана целевая папка.

        Вход: нет.
        Выход:
            True — папка выбрана.
            False — папки нет, в status_label записано предупреждение.

        Роль: единая точка проверки target_dir для трёх шагов
              пайплайна.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return False
        return True

    def _current_sellers(self) -> list:
        """Возвращает актуальный список продавцов.

        Вход: нет.
        Выход: список Seller с брендами.
        Роль: единая точка получения sellers для шагов пайплайна.
              Для возвратов используется get_sellers_with_brands —
              продавцы с полной информацией о брендах.
        """
        return self.parent().sellers_brands_service.get_sellers_with_brands()

    def _run_pipeline_step(self, *, service, target_method,
                           kwargs: dict, start_message: str,
                           finish_message: str, step_name: str,
                           enable_after=None) -> None:
        """Запускает шаг пайплайна в фоновом потоке.

        Вход (все параметры именованные):
            service — уже созданный экземпляр сервиса.
            target_method — bound method сервиса.
            kwargs — доп. именованные аргументы target_method.
                     target_dir и sellers добавляются автоматически.
            start_message — текст в status_label/status_log в начале.
            finish_message — текст при успехе.
            step_name — префикс для logger.debug/logger.critical.
            enable_after — виджет QPushButton для включения после
                           успеха. None — если включать нечего.

        Выход: нет.

        Роль:
            Единая обвязка трёх шагов возвратов: запись в
            status_label и status_log, колбэки on_finished/on_error,
            вызов ThreadFactory с фиксированным списком
            блокируемых кнопок.
        """
        # Двойная запись: короткое сообщение в статусную строку
        # и подробное — в прокручиваемый лог.
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
            Роль: короткое сообщение в status_label, подробное —
                  в status_log, запись в errors.txt через
                  logger.critical (как в ChzMPWindow).
            """
            self.set_status(f"Ошибка на шаге {step_name}: {e}")
            self.set_info(f"Ошибка на шаге {step_name}: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в {step_name}: {e}", can_influence=False,
                )

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

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================

    @log_button_action(
        "btn_choose_file",
        "Ошибка при выборе файла возвратов: {e}",
    )
    def select_source_file(self):
        """Открывает диалог выбора исходного файла возвратов.

        Роль: выбранный файл сохраняется в self.source_file,
              имя показывается в file_label, путь запоминается
              в main_config для следующего запуска.
        """
        start_dir = (
            self.parent().main_config.get("last_returns_dir", None)
            or self.target_dir
            or str(Path.home())
        )
        file_path = FileDialogFactory.open_file_dialog(
            self, "Выберите Excel-файл с возвратами",
            default_dir=start_dir,
            filter="Excel (*.xlsx)",
        )
        if file_path:
            self.source_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.parent().main_config.set(
                "last_returns_dir", str(Path(file_path).parent)
            )
            self.set_status("Файл выбран. Нажмите «Подготовка».")

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self):
        """Шаг 1: подготовка — фильтрация исходного файла возвратов."""
        if not self._precheck_target_dir():
            return
        if not self.source_file:
            self.set_status("Сначала выберите файл")
            return

        service = ReturnsPreparationService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_prepare: ReturnsPreparationService создан"
            )

        self._run_pipeline_step(
            service=service,
            target_method=service.prepare,
            kwargs={"source_file": self.source_file},
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_export_kiz,
        )

    @log_button_action("btn_export_kiz", "Ошибка в on_export_kiz: {e}")
    def on_export_kiz(self):
        """Шаг 2: выгрузка КИЗов для возврата."""
        if not self._precheck_target_dir():
            return

        service = KizExportService(
            self.parent().kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_export_kiz: KizExportService создан")

        self._run_pipeline_step(
            service=service,
            target_method=service.export,
            kwargs={},
            start_message="Выгрузка КИЗов...",
            finish_message="Выгрузка КИЗов завершена.",
            step_name="on_export_kiz",
            enable_after=self.btn_prepare_transfer,
        )

    @log_button_action(
        "btn_prepare_transfer",
        "Ошибка в on_prepare_transfer: {e}",
    )
    def on_prepare_transfer(self):
        """Шаг 3: подготовка КИЗов для передачи между продавцами."""
        if not self._precheck_target_dir():
            return

        service = KizTransferService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_prepare_transfer: KizTransferService создан"
            )

        self._run_pipeline_step(
            service=service,
            target_method=service.prepare_transfer,
            kwargs={},
            start_message="Подготовка передач КИЗов...",
            finish_message="Подготовка передач КИЗов завершена.",
            step_name="on_prepare_transfer",
            enable_after=None,
        )

    @log_button_action(
        "btn_accumulate_sales",
        "Ошибка в on_accumulate_sales: {e}",
    )
    def on_accumulate_sales(self):
        """Отдельная операция: аккумуляция продаж из ЧЗ_МП и Возвратов.

        Роль: в отличие от трёх шагов пайплайна, запускается через
              ThreadFactory.run_in_thread (без блокировки кнопок
              пайплайна). Логи идут через set_status / set_info.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return

        self.set_status("Аккумуляция продаж...")
        self.set_info("Аккумуляция продаж...")
        service = SalesAccumulatorService()
        if self.logger:
            self.logger.debug(
                "on_accumulate_sales: SalesAccumulatorService создан"
            )

        def on_finished():
            self.set_status("Аккумуляция завершена.")
            self.set_info("Аккумуляция завершена.")
            if self.logger:
                self.logger.debug(
                    "on_accumulate_sales: фоновый поток завершён"
                )

        def on_error(e):
            self.set_status(f"Ошибка аккумуляции: {e}")
            self.set_info(f"Ошибка аккумуляции: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в on_accumulate_sales: {e}",
                    can_influence=False,
                )

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir, "returns"),
            on_finished=on_finished,
            error_callback=on_error,
        )

    # ============================================================
    # ЗАВЕРШЕНИЕ
    # ============================================================

    def cleanup(self):
        """Сброс состояния окна: файл, имя файла."""
        self.source_file = None
        self.file_label.setText("Файл не выбран")

    def closeEvent(self, event):
        """Обработка закрытия окна.

        Роль: чистит состояние, снимает active_child у родителя,
              принимает событие.
        """
        if self.logger:
            self.logger.debug("ReturnsWindow: closeEvent получен")
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()