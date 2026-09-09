from PySide6.QtWidgets import QMainWindow, QDialog, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory,
    ListWidgetFactory, ButtonFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.widgets.editable_list_widget import EditableListWidget
from utils.validation import ValidationNumb


class StringListDialog(QMainWindow):
    def __init__(self, parent=None, title="Редактирование", strings=None):
        super().__init__(parent)
        self.strings = strings if strings is not None else []

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=title,
            bg_color=(40, 30, 50, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            on_close=self._save_and_close,
            action_button="Готово",
            action_callback=self._save_and_close,
            action_button_alignment="center",
            return_content_layout=True,
            default_width=400,
            default_height=350
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, title))

        self.list_widget = EditableListWidget(self, initial_items=self.strings)
        content_layout.addWidget(self.list_widget)

    def _save_and_close(self):
        self.strings = self.list_widget.get_items()
        self.close()

class AveragePriceInputDialog(QDialog):
    """Модальное окно для ввода средней цены для продавца."""

    def __init__(self, parent, seller_name):
        super().__init__(parent)
        self.price = None
        self.seller_name = seller_name

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Ввод средней цены",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            draggable=False,
            close_on_click_outside=False,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=400,
            default_height=200
        )

        self.label = LabelFactory.create_label(
            self,
            text=f"Не установлена средняя цена для продавца {seller_name}\nУкажите цену",
            bg_color=(0,0,0,0),
            text_color="#d4d4d4",
            alignment=Qt.AlignCenter,
            word_wrap=True
        )
        content_layout.addWidget(self.label)

        self.input_edit = InputWidgetFactory.create_default_line_edit(self, placeholder="Введите число")
        content_layout.addWidget(self.input_edit)

        save_btn = ButtonFactory.create_button(self, "Сохранить", (70, 120, 90, 0.8))
        save_btn.clicked.connect(self._on_save)
        content_layout.addWidget(save_btn)

    def _on_save(self):
        text = self.input_edit.text().strip()
        if not ValidationNumb.is_number(text):
            current_text = self.label.text()
            if "Данные не подходят" not in current_text:
                self.label.setText(current_text + "\nДанные не подходят. Введите число")
            self.input_edit.clear()
            self.input_edit.setFocus()
            return

        self.price = ValidationNumb.to_int(text)
        self.accept()

    def get_price(self):
        return self.price

class PricesEditWindow(QDialog):
    """Окно для просмотра и редактирования сохранённых цен продавцов."""

    def __init__(self, parent, config):
        super().__init__(parent)
        self.config = config
        self.sellers = config.get_sellers_objects()
        self.saved_prices = config.get("seller_prices", {})

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Цены продавцов",
            bg_color=(40, 30, 50, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=500,
            default_height=500
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, "Цены продавцов"))

        scroll, self.content_widget, self.content_layout2 = ListWidgetFactory.create_scroll_container(
            self, spacing=2
        )
        content_layout.addWidget(scroll)

        self.price_edits = {}
        for seller in self.sellers:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(4)

            name_label = LabelFactory.create_label(
                self, seller.name,
                bg_color=(0,0,0,0),
                text_color="#d4d4d4",
                alignment=Qt.AlignLeft | Qt.AlignVCenter
            )
            row_layout.addWidget(name_label, stretch=1)

            price_edit = InputWidgetFactory.create_default_line_edit(
                self,
                text=str(self.saved_prices.get(seller.name, ""))
            )
            row_layout.addWidget(price_edit, stretch=1)

            self.price_edits[seller.name] = price_edit
            self.content_layout2.addWidget(row_widget)

        save_btn = ButtonFactory.create_button(self, "Сохранить", (70, 120, 90, 0.8))
        save_btn.clicked.connect(self._on_save)
        content_layout.addWidget(save_btn)

    def _on_save(self):
        updated_prices = {}
        for seller_name, edit in self.price_edits.items():
            text = edit.text().strip()
            if text and ValidationNumb.is_number(text):
                updated_prices[seller_name] = ValidationNumb.to_int(text)
        self.config.set("seller_prices", updated_prices)
        self.close()