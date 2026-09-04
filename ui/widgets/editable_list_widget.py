from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit
from ui.factories.factories import ListWidgetFactory, ButtonFactory, InputWidgetFactory

class EditableListWidget(QWidget):
    """
    Виджет для управления списком строк с возможностью добавления/удаления.
    Используется в StringListDialog, BrandEditDialog и подобных.
    """
    def __init__(self, parent=None, initial_items=None, add_text="+ Добавить"):
        super().__init__(parent)
        self.items = initial_items or []
        self._build_ui(add_text)

    def _build_ui(self, add_text):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Прокручиваемая область для строк
        scroll, self.content_widget, self.content_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=2
        )
        layout.addWidget(scroll)

        # Кнопка добавления
        add_btn = ButtonFactory.create_button(
            self, add_text, (100, 80, 120, 0.7), padding="6px 12px"
        )
        add_btn.clicked.connect(self.add_item)
        layout.addWidget(add_btn)

        # Заполняем начальными строками
        for item in self.items:
            self._add_row(item)

    def _add_row(self, value=""):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        line_edit = InputWidgetFactory.create_default_line_edit(self, text=value)
        row_layout.addWidget(line_edit)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_row(row_widget, line_edit)
        )
        row_layout.addWidget(del_btn)

        self.content_layout.addWidget(row_widget)

    def _remove_row(self, row_widget, line_edit):
        self.content_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def add_item(self):
        self._add_row("")

    def get_items(self):
        """Возвращает список текущих строк (непустых)."""
        result = []
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item and item.widget():
                line_edit = item.widget().findChild(QLineEdit)
                if line_edit and line_edit.text().strip():
                    result.append(line_edit.text().strip())
        return result

    def set_items(self, items):
        """Очищает и заполняет список новыми значениями."""
        # Очищаем
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Заполняем
        for val in items:
            self._add_row(val)