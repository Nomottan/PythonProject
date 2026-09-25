import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout)
from PySide6.QtCore import QTimer, Qt
from ui.windows import (
    ChzMPWindow, SellersWindow, BrandsWindow, ReturnsWindow, CompareWindow,
    StringListDialog, PlannerWindow
)
from ui.factories.factories import ButtonFactory, LayoutFactory, WindowFactory
from ui.widgets.planner_quick_view import PlannerQuickView
from utils.datetime_utils import DateTimeUtils
from utils.path_manager import PathManager
from utils.log_system import LogManager
from utils.log_tools.decorators import log_button_action
from services.subservices.logging import LogManagerV2
from services.kiz_validator import KizValidator
from services.planner_service import PlannerService
from services.planner_archive_service import PlannerArchiveService
from services.planner_recurrence_service import PlannerRecurrenceService
from services.plannerviewer_service import PlannerQuickViewController
from services.sellers_brands_service import SellersBrandsService
from storage import (
    KizStorage,
    MainConfig,
    CompareMappingsStorage,
    PlannerTaskStorage,
    PlannerArchiveStorage,
)


class MainWindow(QMainWindow):
    # ============================================================
    # 1. ИНИЦИАЛИЗАЦИЯ ОКНА
    # ============================================================
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Помощник")
        self.setGeometry(100, 100, 600, 900)
        self.setMinimumSize(600, 650)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #28323c;
                border-radius: 15px;
            }
        """)

        # --- Пути и старое логирование ---
        self.paths = PathManager()
        self.log_manager = LogManager()

        # --- Конфиг + сервис продавцов/брендов ---
        self.main_config = MainConfig(self.paths, self.log_manager)
        self.sellers_brands_service = SellersBrandsService(self.main_config)

        # --- Хранилище сопоставлений (для CompareWindow) ---
        self.compare_mappings_storage = CompareMappingsStorage(
            self.paths, self.log_manager,
        )

        # --- Теги активности дочерних окон ---
        # REPLACE: active_child объявлен ДО LogManagerV2 — getter
        # ссылается на атрибут, поэтому он должен существовать.
        self.active_child = None

        # NEW: новая система логирования LoggerV2.
        # Параллельно со старой, старую не отключаем.
        debug_enabled = self.main_config.get("debug_enabled", False)
        self.log_manager_v2 = LogManagerV2(
            debug_enabled=debug_enabled,
            paths=self.paths,
            active_child_getter=lambda: self.active_child,
        )
        self.logger = self.log_manager_v2.create_logger_v2(
            source="MainWindow.main",
            domain="main",
        )

        # NEW: счётчик тиков on_timer — для периодического debug.
        # Срабатывает раз в 600 тиков (600 * 100 мс = 60 сек).
        self._timer_tick_count = 0

        # --- Теги активности дочерних окон ---
        self.chz_mp_window = None
        self.sellers_window = None
        self.brands_window = None
        self.returns_window = None
        self.compare_window = None
        self.planner_window = None

        # --- KizStorage (used_kiz.json) ---
        self.kiz_storage = KizStorage(
            self.paths.get_data_file("used_kiz.json"),
            log_manager=self.log_manager,
        )
        self.kiz_validator = KizValidator(self.kiz_storage)

        # --- Planner storages ---
        self.planner_storage = PlannerTaskStorage(
            self.paths.get_data_file("planner_tasks.json"),
            log_manager=self.log_manager,
        )
        # --- Archive storages ---
        self.planner_archive_storage = PlannerArchiveStorage(
            self.paths.get_data_file("planner_archive.json"),
            log_manager=self.log_manager,
        )
        # --- Вызов сервиса планировщика ---
        self.planner_service = PlannerService(
            self.planner_storage,
            archive_storage=self.planner_archive_storage,
            log_manager=self.log_manager,
        )
        # --- Вызов сервиса архива планировщика ---
        self.planner_archive_service = PlannerArchiveService(
            self.planner_archive_storage,
            self.planner_storage,
            log_manager=self.log_manager,
            planner_service=self.planner_service,
        )
        # NEW: сервис генерации экземпляров регулярных задач.
        self.planner_recurrence_service = PlannerRecurrenceService(
            self.planner_service,
            log_manager=self.log_manager,
        )

        # --- Стартовый порядок обслуживания планировщика---
        # 1. Архивируем «вчерашние» экземпляры — генерация увидит
        #    актуальное состояние storage.
        # 2. Архивируем прошедшие события — они не должны участвовать
        #    в активации.
        # 3. Активируем сегодняшние события — они появятся в мини-планировщике.
        # 4. Генерируем экземпляры регулярных задач.
        self.planner_service.archive_stale_instances()
        self.planner_service.expire_past_events()
        self.planner_service.activate_due_events()
        self.planner_recurrence_service.generate_due_instances()

        # --- Таймер регулярных задач и событий: раз в 30 секунд ---
        self.recurrence_timer = QTimer(self)
        self.recurrence_timer.setInterval(1 * 30 * 1000)
        self.recurrence_timer.timeout.connect(self._on_recurrence_timer)
        self.recurrence_timer.start()

        # --- Мини-планировщик ---
        self.planner_quick_view = PlannerQuickView(self)
        self.planner_quick_controller = PlannerQuickViewController(
            self.planner_service,
            self.planner_quick_view,
        )

        # --- Таймер кнопки даты/времени ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(100)

        # ============================================================
        # 2. ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ
        # ============================================================
        _main_button_configs = [
            ("btn_sellers", "Продавцы", (80, 100, 130), "8px 16px", None),
            ("btn_brands", "Бренды", (80, 100, 130), "8px 16px", None),
            ("btn_chz_mp", "Подготовка к списанию кодов по отчётам", (70, 90, 100, 0.8), "8px 16px", None),
            ("btn_returns", "Подготовка к возврату в оборот", (70, 90, 100, 0.8), "8px 16px", None),
            ("btn_compare", "Сравнение поставок", (100, 90, 70, 0.8), "8px 16px", None),
        ]

        _main_handlers = {
            "btn_sellers": "open_sellers_window",
            "btn_brands": "open_brands_window",
            "btn_chz_mp": "open_chz_mp_window",
            "btn_returns": "open_returns_window",
            "btn_compare": "open_compare_window",
        }

        ButtonFactory.create_buttons_from_config(self, _main_button_configs, _main_handlers)

        # Кнопка даты/времени (правая верхняя) — сделать неактивной
        self.datetime_btn = ButtonFactory.create_datetime_button(self, self.open_datetime_window)

        # ============================================================
        # 3. МАКЕТ
        # ============================================================
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Верхняя область: левая колонка (Продавцы, Бренды), правая — кнопка даты
        left_col = LayoutFactory.create_column(
            self,
            self.btn_sellers,
            self.btn_brands,
            alignment=Qt.AlignLeft | Qt.AlignTop,
            spacing=5
        )

        top_area = QHBoxLayout()
        top_area.setAlignment(Qt.AlignTop)
        top_area.addWidget(left_col)
        top_area.addStretch(1)
        top_area.addWidget(self.datetime_btn, alignment=Qt.AlignTop)

        main_layout.addLayout(top_area)

        main_layout.addStretch(1)
        quick_row = LayoutFactory.create_row(
            self, self.planner_quick_view,
            alignment=Qt.AlignCenter,
        )
        main_layout.addWidget(quick_row)

        # Центральная колонка с основными кнопками
        center_col = LayoutFactory.create_column(
            self,
            self.btn_chz_mp,
            self.btn_returns,
            self.btn_compare,
            alignment=Qt.AlignCenter,
            spacing=10
        )

        main_layout.addStretch(1)
        main_layout.addWidget(center_col, alignment=Qt.AlignCenter)
        main_layout.addStretch(1)

        self.update_buttons_state()

    # ============================================================
    # 4. МЕТОДЫ УПРАВЛЕНИЯ СОСТОЯНИЕМ
    # ============================================================
    def update_buttons_state(self):
        sellers = self.sellers_brands_service.get_sellers_objects()
        has_sellers = len(sellers) > 0
        self.btn_chz_mp.setEnabled(has_sellers)
        if not has_sellers:
            self.btn_chz_mp.setText("Нет продавцов – сначала добавьте в окне 'Продавцы'")
        else:
            self.btn_chz_mp.setText("Подготовка к списанию кодов по отчётам")

    # ============================================================
    # 5. ОТКРЫТИЕ ДОЧЕРНИХ ОКОН
    # ============================================================
    @log_button_action(
        "open_chz_mp_window",
        "Ошибка при открытии окна 'Списание КИЗов': {e}",
    )
    def open_chz_mp_window(self):
        if self.chz_mp_window is None or not self.chz_mp_window.isVisible():
            self.chz_mp_window = ChzMPWindow(
                self, log_manager_v2=self.log_manager_v2,
            )
            WindowFactory.show_child_window(self, self.chz_mp_window)
            self.logger.debug("open_chz_mp_window: окно создано заново")
        else:
            self.chz_mp_window.raise_()
            self.chz_mp_window.activateWindow()
            self.logger.debug("open_chz_mp_wi   ndow: окно активировано")

    @log_button_action(
        "open_returns_window",
        "Ошибка при открытии окна 'Возвраты': {e}",
    )
    def open_returns_window(self):
        if self.returns_window is None or not self.returns_window.isVisible():
            # ReturnsWindow получает старый log_manager — не меняем.
            self.returns_window = ReturnsWindow(self, self.log_manager)
            WindowFactory.show_child_window(self, self.returns_window)
            self.logger.debug("open_returns_window: окно создано заново")
        else:
            self.returns_window.raise_()
            self.returns_window.activateWindow()
            self.logger.debug("open_returns_window: окно активировано")

    @log_button_action(
        "open_sellers_window",
        "Ошибка при открытии окна 'Продавцы': {e}",
    )
    def open_sellers_window(self):
        if self.sellers_window is None or not self.sellers_window.isVisible():
            self.sellers_window = SellersWindow(self)
            WindowFactory.show_child_window(self, self.sellers_window)
            self.logger.debug("open_sellers_window: окно создано заново")
        else:
            self.sellers_window.raise_()
            self.sellers_window.activateWindow()
            self.logger.debug("open_sellers_window: окно активировано")

    def refresh_sellers_window(self):
        # Без декоратора: внутренний метод, не кнопка.
        if self.sellers_window and self.sellers_window.isVisible():
            self.sellers_window.refresh_ui()

    @log_button_action(
        "open_brands_window",
        "Ошибка при открытии окна 'Бренды': {e}",
    )
    def open_brands_window(self):
        if self.brands_window is None or not self.brands_window.isVisible():
            self.brands_window = BrandsWindow(self)
            WindowFactory.show_child_window(self, self.brands_window)
            self.logger.debug("open_brands_window: окно создано заново")
        else:
            self.brands_window.raise_()
            self.brands_window.activateWindow()
            self.logger.debug("open_brands_window: окно активировано")

    @log_button_action(
        "open_compare_window",
        "Ошибка при открытии окна 'Сравнение поставок': {e}",
    )
    def open_compare_window(self):
        if self.compare_window is None or not self.compare_window.isVisible():
            self.compare_window = CompareWindow(
                self, mappings_storage=self.compare_mappings_storage,
            )
            WindowFactory.show_child_window(self, self.compare_window)
            self.logger.debug("open_compare_window: окно создано заново")
        else:
            # REPLACE: было self.brands_window.raise_() — опечатка.
            self.compare_window.raise_()
            self.compare_window.activateWindow()
            self.logger.debug("open_compare_window: окно активировано")

    # ============================================================
    # 6. СОБЫТИЯ ОКНА
    # ============================================================
    def open_string_list_dialog(self, title, strings):
        dialog = StringListDialog(self, title, strings)
        dialog.show()

    @log_button_action(
        "open_datetime_window",
        "Ошибка при открытии окна 'Планировщик': {e}",
    )
    def open_datetime_window(self):
        if self.planner_window is None or not self.planner_window.isVisible():
            self.planner_window = PlannerWindow(
                self,
                planner_service=self.planner_service,
                archive_service=self.planner_archive_service,
            )
            WindowFactory.show_child_window(self, self.planner_window)
            self.logger.debug("open_datetime_window: окно создано заново")
        else:
            self.planner_window.raise_()
            self.planner_window.activateWindow()
            self.logger.debug("open_datetime_window: окно активировано")

    def resizeEvent(self, event):
        for child in (self.chz_mp_window, self.sellers_window,
                      self.brands_window, self.returns_window,
                      self.compare_window, self.planner_window):
            if child and child.isVisible():
                parent_rect = self.frameGeometry()
                child.setGeometry(10, 10,
                                  parent_rect.width() - 20,
                                  parent_rect.height() - 50)
        super().resizeEvent(event)

    def moveEvent(self, event):
        screen = QApplication.primaryScreen().availableGeometry()
        x = max(screen.x(), min(self.x(), screen.x() + screen.width() - self.width()))
        y = max(screen.y(), min(self.y(), screen.y() + screen.height() - self.height()))
        if x != self.x() or y != self.y():
            self.move(x, y)
        super().moveEvent(event)

    def on_timer(self):
        """Тик таймера кнопки даты/времени.

        Роль: обновляет текст кнопки. Раз в 600 тиков (60 сек при
              интервале 100 мс) пишет debug «таймер работает».
              Ошибки не пробрасываются — critical и продолжаем.
        """
        # NEW: счётчик для периодического debug.
        self._timer_tick_count += 1
        if self._timer_tick_count >= 600:
            self._timer_tick_count = 0
            self.logger.debug(
                f"on_timer: таймер работает, время "
                f"{DateTimeUtils.get_current_datetime_text()}"
            )

        try:
            self.datetime_btn.setText(DateTimeUtils.get_current_datetime_text())
        except Exception as e:
            self.logger.critical(
                f"Ошибка в on_timer: {e}", can_influence=False,
            )

    def _on_recurrence_timer(self):
        """Обработчик таймера: события + генерация экземпляров.

        Роль: раз в 30 секунд приводит систему в актуальное состояние:
              1. expire_past_events — прошедшие события → архив (EXPIRED).
              2. activate_due_events — сегодняшние события → ACTIVE,
                 чтобы они появились в мини-планировщике в тот же день.
              3. generate_due_instances — генерация экземпляров
                 регулярных задач.

        Порядок важен и совпадает с порядком в __init__: сначала
        архивируем «вчерашнее», потом активируем «сегодняшнее»,
        потом генерируем новое. Иначе на границе дня возможна гонка:
        генерация создаст экземпляр, а expire тут же его заархивирует.

        При ошибке на любом шаге — critical и прерываем тик: следующий
        шаг зависит от предыдущего.
        """
        self.logger.debug("_on_recurrence_timer: старт")
        try:
            self.planner_service.expire_past_events()
            self.logger.debug(
                "_on_recurrence_timer: expire_past_events выполнен"
            )
            self.planner_service.activate_due_events()
            self.logger.debug(
                "_on_recurrence_timer: activate_due_events выполнен"
            )
            self.planner_recurrence_service.generate_due_instances()
            self.logger.debug(
                "_on_recurrence_timer: generate_due_instances выполнен"
            )
        except Exception as e:
            self.logger.critical(
                f"Ошибка в _on_recurrence_timer: {e}",
                can_influence=False,
            )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())