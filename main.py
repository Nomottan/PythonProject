import sys
from pathlib import Path
import asyncio

from services.planner_services import PlannerFacade
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget,
                               QVBoxLayout, QHBoxLayout)
from PySide6.QtCore import QTimer, Qt

from ui.windows import (
    ChzMPWindow, SellersWindow, BrandsWindow, ReturnsWindow, CompareWindow,
    StringListDialog, DailyPlannerWindow, DailyTasksWidget, PlannerWindow
)

from config_manager import ConfigManager
from ui.factories.factories import ButtonFactory, LayoutFactory, WindowFactory
from utils.datetime_utils import DateTimeUtils
from utils.logger import CompositeLogger, FileLogger, QtStatusLogger
from utils.log_templates import LogTemplates

async def async_task():
    await asyncio.sleep(2)


def run_async_in_thread():
    """Запускает asyncio-задачу в отдельном потоке."""
    import threading
    def target():
        asyncio.run(async_task())
    threading.Thread(target=target, daemon=True).start()


class MainWindow(QMainWindow):
    # ============================================================
    # 1. ИНИЦИАЛИЗАЦИЯ ОКНА
    # ============================================================
    def __init__(self):
        super().__init__()
        self.planner_facade = PlannerFacade()
        self.setWindowTitle("Помощник")
        self.setGeometry(100, 100, 600, 900)
        self.setMinimumSize(600, 650)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2a323b;
                border-radius: 15px;
            }
        """)
        self.app_logger = CompositeLogger()
        self.ui_logger = QtStatusLogger()
        self.app_logger.add_logger(self.ui_logger)

        self.config = ConfigManager()
        self.active_child = None
        self.chz_mp_window = None
        self.sellers_window = None
        self.brands_window = None
        self.returns_window = None
        self.planner_window = None
        self.compare_window = None

        self.planner_facade = PlannerFacade()
        self.planner_facade.initialize()

        self.timer = QTimer()
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(100)

        # ============================================================
        # 2. ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ
        # ============================================================
        _main_button_configs = [
            ("btn_sellers", "Продавцы", (80, 60, 80), "8px 16px", None),
            ("btn_brands", "Бренды", (80, 60, 80), "8px 16px", None),
            ("btn_chz_mp", "Подготовка к списанию кодов по отчётам", (61, 20, 30, 0.6), "8px 16px", None),
            ("btn_returns", "Подготовка к возврату в оборот", (61, 20, 30, 0.6), "8px 16px", None),
            ("btn_compare", "Сравнение поставок", (100, 130, 160, 0.8), "8px 16px", None),
        ]

        debug_logger = FileLogger("logs/debug.log", level="debug")
        self.app_logger.add_logger(debug_logger)

        _main_handlers = {
            "btn_sellers": "open_sellers_window",
            "btn_brands": "open_brands_window",
            "btn_chz_mp": "open_chz_mp_window",
            "btn_returns": "open_returns_window",
            "btn_compare": "open_compare_window",
        }

        # Создаём основные кнопки через новую фабрику
        ButtonFactory.create_buttons_from_config(self, _main_button_configs, _main_handlers)

        # Кнопка даты/времени (правая верхняя)
        self.datetime_btn = ButtonFactory.create_datetime_button(self, self.open_datetime_window)

        self.daily_tasks_widget = DailyTasksWidget(self, facade=self.planner_facade)
        # ============================================================
        # 3. МАКЕТ
        # ============================================================
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Верхняя область ---
        # Левая колонка: кнопки "Продавцы" и "Бренды" друг под другом
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
        top_area.addStretch(1)                       # занимает пространство между левой колонкой и правой кнопкой
        top_area.addWidget(self.datetime_btn, alignment=Qt.AlignTop)

        main_layout.addLayout(top_area)

        center_col = LayoutFactory.create_column(
            self,
            self.btn_chz_mp,
            self.btn_returns,
            self.btn_compare,  # новая кнопка
            alignment=Qt.AlignCenter,
            spacing=10
        )

        # Вставляем в главный макет
        main_layout.addStretch(1)
        main_layout.addWidget(center_col, alignment=Qt.AlignCenter)
        main_layout.addStretch(1)





        # Проверка доступности кнопок
        self.update_buttons_state()

    # ============================================================
    # 4. МЕТОДЫ УПРАВЛЕНИЯ СОСТОЯНИЕМ
    # ============================================================
    def update_buttons_state(self):
        sellers = self.config.get_sellers_objects()
        has_sellers = len(sellers) > 0
        self.btn_chz_mp.setEnabled(has_sellers)
        if not has_sellers:
            self.btn_chz_mp.setText("Нет продавцов – сначала добавьте в окне 'Продавцы'")
        else:
            self.btn_chz_mp.setText("Подготовка к списанию кодов по отчётам")

    # ============================================================
    # 5. ОТКРЫТИЕ ДОЧЕРНИХ ОКОН
    # ============================================================
    def open_chz_mp_window(self):
        if self.chz_mp_window is None or not self.chz_mp_window.isVisible():
            self.chz_mp_window = ChzMPWindow(self)
            WindowFactory.show_child_window(self, self.chz_mp_window)
        else:
            self.chz_mp_window.raise_()
            self.chz_mp_window.activateWindow()

    def open_returns_window(self):
        if self.returns_window is None or not self.returns_window.isVisible():
            self.returns_window = ReturnsWindow(self)
            WindowFactory.show_child_window(self, self.returns_window)
        else:
            self.returns_window.raise_()
            self.returns_window.activateWindow()

    def open_sellers_window(self):
        if self.sellers_window is None or not self.sellers_window.isVisible():
            self.sellers_window = SellersWindow(self)
            WindowFactory.show_child_window(self, self.sellers_window)
        else:
            self.sellers_window.raise_()
            self.sellers_window.activateWindow()

    def refresh_sellers_window(self):
        if self.sellers_window and self.sellers_window.isVisible():
            self.sellers_window.refresh_ui()

    def open_brands_window(self):
        if self.brands_window is None or not self.brands_window.isVisible():
            self.brands_window = BrandsWindow(self)
            WindowFactory.show_child_window(self, self.brands_window)
        else:
            self.brands_window.raise_()
            self.brands_window.activateWindow()

    # ============================================================
    # 6. СОБЫТИЯ ОКНА
    # ============================================================
    def open_string_list_dialog(self, title, strings):
        """Открывает диалог редактирования списка строк (бренды / ключи)."""
        dialog = StringListDialog(self, title, strings)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def open_datetime_window(self):
        if self.planner_window is None or not self.planner_window.isVisible():
            self.planner_window = PlannerWindow(self, facade=self.planner_facade)
            WindowFactory.show_child_window(self, self.planner_window)
        else:
            self.planner_window.raise_()
            self.planner_window.activateWindow()

    def open_compare_window(self):
        if self.compare_window is None or not self.compare_window.isVisible():
            self.compare_window = CompareWindow(self)
            WindowFactory.show_child_window(self, self.compare_window)
        else:
            self.compare_window.raise_()
            self.compare_window.activateWindow()

    def resizeEvent(self, event):
        for child in (self.chz_mp_window, self.sellers_window,
                      self.brands_window, self.returns_window,
                      self.planner_window, self.compare_window):
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
        # Обновляем текст на кнопке даты/времени
        self.datetime_btn.setText(DateTimeUtils.get_current_datetime_text())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    run_async_in_thread()

    sys.exit(app.exec())
