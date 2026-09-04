from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout
from datetime import datetime
from ui.factories.factories import ProgressFactory, LabelFactory, BaseWidgetFactory

class DeadlineProgressWidget(QWidget):
    """
    Виджет для отображения дедлайна: прогресс-бар + лычка с оставшимся временем.
    Кликабелен, эмитирует сигнал clicked.
    """
    clicked = Signal()

    def __init__(self, parent=None, deadline=None):
        super().__init__(parent)
        self.deadline = deadline

        # Вертикальная компоновка: прогресс-бар и метка
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Прогресс-бар
        self.progress_bar = ProgressFactory.create_progress_bar(
            self,
            min_value=0,
            max_value=100,
            value=0,
            bg_color=(60, 50, 70, 0.9),
            chunk_color=(100, 180, 100),  # нейтральный по умолчанию
            border_radius=5,
            fixed_size=None
        )
        layout.addWidget(self.progress_bar)

        # Лычка с текстом
        self.time_label = LabelFactory.create_label(
            self,
            text="",
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_size=10
        )
        layout.addWidget(self.time_label)

        # Устанавливаем начальные данные
        self.set_deadline(deadline)

    def set_deadline(self, deadline):
        """Обновляет отображение на основе переданного дедлайна."""
        self.deadline = deadline
        if deadline is None:
            self.progress_bar.setVisible(False)
            self.time_label.setText("")
            return

        now = datetime.now()
        delta = deadline - now
        total_seconds = delta.total_seconds()

        if total_seconds <= 0:
            self.time_label.setText("Срок истёк")
            self.progress_bar.setVisible(False)
            return

        # Определяем количество дней
        days = total_seconds / 86400.0

        # Устанавливаем прогресс: 100% в начале, уменьшается к нулю
        if days > 30:
            percentage = 100  # показываем полный, нейтральный
            chunk_color = (100, 180, 100)
        else:
            # Для яркого состояния прогресс = осталось / 30 * 100
            percentage = max(0, min(100, int((days / 30.0) * 100)))
            chunk_color = (230, 120, 50)  # оранжевый/красный

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(percentage)
        self.progress_bar.setStyleSheet(
            self.progress_bar.styleSheet() +
            f" QProgressBar::chunk {{ background-color: {BaseWidgetFactory.color_to_str(chunk_color)}; }}"
        )

        if days >= 1:
            self.time_label.setText(f"Осталось {int(days)} дн.")
        else:
            hours = total_seconds / 3600.0
            self.time_label.setText(f"Осталось {int(hours)} ч.")

    def mousePressEvent(self, event):
        """Эмитируем clicked при нажатии."""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)