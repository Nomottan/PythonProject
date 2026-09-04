from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import QTimer, Qt
from ui.factories.factories import WindowFactory, ButtonFactory
from utils.datetime_utils import DateTimeUtils

class DailyPlannerWindow(QMainWindow):
    """Окно ежедневника с кнопкой даты/времени (пока только закрытие)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

        # Настройка окна в нефритовых тонах
        main_layout = WindowFactory.setup_child_window(
            self, "Ежедневник",
            bg_color=(0, 95, 80, 0.95),
            close_callback=self.close
        )

        # Кнопка с датой и временем, клик по которой закрывает окно
        self.date_btn = ButtonFactory.create_datetime_button(self, self.close)
        self.date_btn.setText(DateTimeUtils.get_current_datetime_text())
        main_layout.addWidget(self.date_btn, alignment=Qt.AlignCenter)

        # Таймер для обновления времени на кнопке (опционально)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_datetime)
        self.update_timer.start(60000)  # обновление раз в минуту

    def _update_datetime(self):
        self.date_btn.setText(DateTimeUtils.get_current_datetime_text())