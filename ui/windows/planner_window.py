from PySide6.QtWidgets import QMainWindow
from ui.factories.factories import WindowFactory


class PlannerWindow(QMainWindow):
    """Окно-заглушка «Планировщик».

    Назначение:
        Показывает заголовок в шапке и кнопку закрытия. Тело пустое —
        элементы будут добавлены в следующих задачах.

    Роль в программе:
        Открывается по кнопке даты/времени в главном окне. Служит заделом
        для будущего планировщика.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = WindowFactory.setup_child_window(
            self, "Планировщик",
            bg_color=(70, 60, 50, 0.95)
        )
        # Тело окна пустое — элементы будут добавлены в следующих задачах.

    def cleanup(self):
        """Очистка состояния при закрытии. Пока нечего чистить."""
        pass

    def closeEvent(self, event):
        """Обработка закрытия окна."""
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()