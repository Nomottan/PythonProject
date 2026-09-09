from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout
from ui.factories.factories import ButtonFactory, LabelFactory, FileDialogFactory

class PathSelector(QWidget):
    """
    Виджет для выбора папки: кнопка "..." и отображение выбранного пути.
    Эмитит сигнал path_changed при выборе новой папки.
    """
    path_changed = Signal(str)

    def __init__(self, parent=None, initial_path="", dialog_title="Выберите папку",
                 button_text="...", label_style=None):
        super().__init__(parent)
        self.dialog_title = dialog_title
        self.button_text = button_text
        self.selected_path = initial_path

        # Горизонтальная компоновка
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Кнопка выбора
        self.btn_select = ButtonFactory.create_button(
            self, button_text, (250, 230, 180)
        )
        self.btn_select.clicked.connect(self._choose_path)
        layout.addWidget(self.btn_select)

        # Метка с путём
        self.path_label = LabelFactory.create_label(
            self,
            text=initial_path or "Путь не выбран",
            bg_color=(64, 48, 66, 128),
            text_color="#d4d4d4",
            padding="4px 8px",
            border_radius=5,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_family="Consolas, monospace",
            font_size=10
        )
        # Если нужно переопределить стиль метки, можно передать label_style
        if label_style:
            self.path_label.setStyleSheet(self.path_label.styleSheet() + label_style)

        layout.addWidget(self.path_label, stretch=1)

    def _choose_path(self):
        """Открывает диалог выбора папки и обновляет путь."""
        start = self.selected_path or None
        path = FileDialogFactory.open_directory_dialog(self, self.dialog_title, start)
        if path:
            self.set_path(path)
            self.path_changed.emit(path)

    def set_path(self, path):
        """Устанавливает новый путь и обновляет метку."""
        self.selected_path = path
        self.path_label.setText(path if path else "Путь не выбран")

    def get_path(self):
        """Возвращает текущий выбранный путь."""
        return self.selected_path