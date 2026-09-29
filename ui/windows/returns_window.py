"""
Окно «Подготовка возвратов в оборот».

Назначение:
    Пайплайн из трёх шагов: подготовка (фильтрация исходного файла),
    выгрузка КИЗов для возврата, подготовка КИЗов для передачи между
    продавцами. Плюс операция аккумуляции продаж — в базовом классе.

Роль в программе:
    Открывается из MainWindow. Наследник BaseServiceWindow:
    set_status/set_info/_precheck_target_dir/closeEvent/
    on_accumulate_sales — унаследованы, окно отвечает только за
    свою раскладку и обработчики шагов.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
)
from ui.styles import ColorCalculator
from ui.widgets.path_selector import PathSelector
from services.returns_service import (
    ReturnsPreparationService, KizExportService, KizTransferService,
)
from utils.log_tools.decorators import log_button_action


class ReturnsWindow(BaseServiceWindow):
    """Окно пайплайна возвратов.

    Роль:
        Объединяет три шага обработки возвратов. Каждый шаг —
        отдельный сервис, запускается в фоновом потоке через
        BaseServiceWindow._run_async_step. Логи шагов идут в
        status_log (унаследован); короткие подсказки — в
        status_label (унаследован).
    """

    LOGGER_SOURCE = "ReturnsWindow.returns_window"
    LOGGER_DOMAIN = "returns"

    # BG_COLOR вычисляется через ColorCalculator.derive от нейтрального
    # (50,50,50): r+2(r//5), g+g//5, b+2(b//5) → (70, 60, 70).
    BG_COLOR = ColorCalculator.derive(
        (50, 50, 50),
        r_fn=lambda r: r + 2 * (r // 5),
        g_fn=lambda g: g + g // 5,
        b_fn=lambda b: b + 2 * (b // 5),
    )

    # Кнопки, блокируемые на время шага пайплайна.
    # btn_accumulate сюда не входит — это отдельная операция.
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
            log_manager_v2 — LogManagerV2 или None.

        Роль: строит раскладку и подключает сигналы. Логгер,
              target_dir, status_label, status_log и main_layout
              созданы базовым классом.
        """
        super().__init__(
            parent,
            title="Подготовка возвратов в оборот",
            log_manager_v2=log_manager_v2,
        )

        # Специфичное для окна состояние.
        self.source_file = None

        # ---------- ЭЛЕМЕНТЫ ----------
        self.btn_choose_file = ButtonFactory.create_button(
            self, "Выбрать файл", (120, 90, 120, 0.8),
        )
        self.btn_choose_file.clicked.connect(self.select_source_file)

        self.header_label = LabelFactory.create_label(
            self,
            text=(
                "Подготовка возвратов\n"
                "Подготовь файл, он должен быть определенного формата\n"
                "Прогони коды через BestMark и сделай импорт в Excell\n"
                "С этим файлом всё работать будет\n"
                "Прежде чем продавать в ЭДО верни КИЗы в оборот"
            ),
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
            self, self.btn_choose_file, self.file_label, spacing=5,
        )
        center_layout.addWidget(file_row)

        center_layout.addWidget(self.path_selector)

        prepare_layout = QHBoxLayout()
        prepare_layout.addWidget(self.btn_prepare)
        center_layout.addLayout(prepare_layout)

        # status_label — из базового класса.
        center_layout.addWidget(self.status_label)

        bottom_row = LayoutFactory.create_row(
            self, self.btn_export_kiz, self.btn_prepare_transfer, spacing=20,
        )
        center_layout.addWidget(bottom_row)

        # status_log — из базового класса.
        center_layout.addWidget(self.status_log)

        center_layout.addStretch(1)

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

        self.main_layout.addLayout(center_layout)

        if self.logger:
            self.logger.debug("ReturnsWindow.__init__: окно инициализировано")

    # ============================================================
    # ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _current_sellers(self) -> list:
        """Возвращает список продавцов с брендами.

        Вход: нет.
        Выход: list[Seller] с заполненными .brands.
        Роль: переопределение базового — для возвратов нужны
              продавцы с полной информацией о брендах.
        """
        return self.main_window.sellers_brands_service.get_sellers_with_brands()

    def _on_target_dir_changed_hook(self) -> None:
        """Сброс кнопок шагов 2–3 при смене папки.

        Вход: нет.
        Выход: нет.
        Роль: хук вызывается базовым _on_target_dir_changed после
              очистки логов и обновления target_dir.
        """
        self.btn_export_kiz.setEnabled(False)
        self.btn_prepare_transfer.setEnabled(False)

    def cleanup(self) -> None:
        """Сброс состояния окна при закрытии."""
        self.source_file = None
        self.file_label.setText("Файл не выбран")

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================

    @log_button_action(
        "btn_choose_file",
        "Ошибка при выборе файла возвратов: {e}",
    )
    def select_source_file(self) -> None:
        """Открывает диалог выбора исходного файла возвратов.

        Роль: тонкая обёртка над _select_single_file. Путь
              сохраняется в self.source_file через callback.
        """
        self._select_single_file(
            config_key="last_returns_dir",
            title="Выберите Excel-файл с возвратами",
            filter="Excel (*.xlsx)",
            label_widget=self.file_label,
            on_success=self._on_source_file_selected,
        )

    def _on_source_file_selected(self, path: str) -> None:
        """Сохраняет выбранный файл и подсказывает следующий шаг."""
        self.source_file = path
        self.set_status("Файл выбран. Нажмите «Подготовка».")

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
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

        self._run_async_step(
            service=service,
            target_method=service.prepare,
            kwargs={"source_file": self.source_file},
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_export_kiz,
        )

    @log_button_action("btn_export_kiz", "Ошибка в on_export_kiz: {e}")
    def on_export_kiz(self) -> None:
        """Шаг 2: выгрузка КИЗов для возврата."""
        if not self._precheck_target_dir():
            return

        service = KizExportService(
            self.main_window.kiz_validator, self.log_manager_v2,
        )
        if self.logger:
            self.logger.debug("on_export_kiz: KizExportService создан")

        self._run_async_step(
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
    def on_prepare_transfer(self) -> None:
        """Шаг 3: подготовка КИЗов для передачи между продавцами."""
        if not self._precheck_target_dir():
            return

        service = KizTransferService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_prepare_transfer: KizTransferService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.prepare_transfer,
            kwargs={},
            start_message="Подготовка передач КИЗов...",
            finish_message="Подготовка передач КИЗов завершена.",
            step_name="on_prepare_transfer",
            enable_after=None,
        )
