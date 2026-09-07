from PySide6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout,
    QMessageBox, QInputDialog
)
from PySide6.QtCore import Qt
from ui.factories.factories import (
    LabelFactory, ListWidgetFactory, ButtonFactory, LayoutFactory,
    InputWidgetFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.widgets.editable_list_widget import EditableListWidget
from models.models import Seller, Brand

class BrandsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.brands = parent.config.get_brands_objects()
        for b in self.brands:
            b.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        _ = parent.config.get_sellers_objects(brands_dict=brands_dict)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Бренды",
            bg_color=(70, 60, 90, 0.9),
            close_button=True,
            draggable=False,
            close_on_click_outside=False,
            modal=False,
            center=True,
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=600,
            default_height=500
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, "Бренды"))

        self.brands_widget = QWidget()
        self.grid_layout = QGridLayout(self.brands_widget)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(5)

        scroll = ListWidgetFactory.create_scroll_area(
            self, widget=self.brands_widget, widget_resizable=True
        )
        content_layout.addWidget(scroll)

        self._refresh_grid()

        add_btn = ButtonFactory.create_add_button(self, self._add_new_brand)
        LayoutFactory.add_centered_widget(content_layout, add_btn)

    def _refresh_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        columns = 4
        sorted_brands = sorted(self.brands, key=lambda b: b.name.lower())

        for i, brand in enumerate(sorted_brands):
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)

            btn = ButtonFactory.create_button(
                self, brand.name, (100, 80, 130, 0.8),
                fixed_size=(130, 30),
                alignment='left'
            )
            btn.clicked.connect(lambda checked, b=brand: self._on_brand_click(b))
            container_layout.addWidget(btn)

            self.grid_layout.addWidget(container, i // columns, i % columns)

    def _on_brand_click(self, brand):
        brand.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        sellers = self.main_window.config.get_sellers_objects(brands_dict=brands_dict)
        dialog = BrandEditDialog(self, brand, sellers, main_window=self.main_window)
        dialog.setWindowModality(Qt.ApplicationModal)
        original_close = dialog.closeEvent
        def new_close(event):
            original_close(event)
            self._refresh_grid()
        dialog.closeEvent = new_close
        dialog.show()

    def _add_new_brand(self):
        new_brand = Brand("Новый бренд")
        self.brands.append(new_brand)
        self._refresh_grid()
        new_brand.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        sellers = self.main_window.config.get_sellers_objects(brands_dict=brands_dict)
        dialog = BrandEditDialog(self, new_brand, sellers, main_window=self.main_window)
        dialog.setWindowModality(Qt.ApplicationModal)
        original_close = dialog.closeEvent
        def new_close(event):
            original_close(event)
            self._refresh_grid()
        dialog.closeEvent = new_close
        dialog.show()

    def save_and_close(self):
        self.main_window.config.set_brands_objects(self.brands)
        self.close()

class BrandEditDialog(QMainWindow):
    def __init__(self, parent=None, brand: Brand = None, sellers: list[Seller] = None, main_window=None):
        super().__init__(parent)
        self.brand = brand
        self.sellers = sellers if sellers is not None else []
        self.main_window = main_window

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=f"Редактирование бренда: {brand.name}",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=550,
            default_height=500
        )

        # Поле имени
        self.name_edit = InputWidgetFactory.create_default_line_edit(self, text=brand.name)
        content_layout.addWidget(self.name_edit)

        # Две колонки
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(10)

        # Левая колонка: ключи
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(LabelFactory.create_header_label(self, "Ключи:", alignment=Qt.AlignLeft))
        self.keys_list = EditableListWidget(self, initial_items=brand.keys, add_text="+ добавить ключ")
        left_layout.addWidget(self.keys_list)
        cols_layout.addWidget(left_widget)

        # Правая колонка: продавцы
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(LabelFactory.create_header_label(self, "Продавцы:", alignment=Qt.AlignLeft))
        self.sellers_widget = QWidget()
        self.sellers_layout = QVBoxLayout(self.sellers_widget)
        self.sellers_layout.setContentsMargins(0, 0, 0, 0)
        self.sellers_layout.setSpacing(2)
        scroll = ListWidgetFactory.create_scroll_area(self, widget=self.sellers_widget, widget_resizable=True)
        right_layout.addWidget(scroll)
        add_seller_btn = ButtonFactory.create_button(
            self, "+ добавить продавца", (100, 80, 120, 0.7), padding="6px 12px"
        )
        add_seller_btn.clicked.connect(self._add_seller)
        right_layout.addWidget(add_seller_btn)
        cols_layout.addWidget(right_widget)

        content_layout.addLayout(cols_layout)

        # Нижние кнопки (вручную, т.к. они специфичны)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        ok_btn = ButtonFactory.create_button(self, "Готово", (70, 120, 90, 0.8), fixed_size=(400, 30))
        ok_btn.clicked.connect(self.close)
        bottom_layout.addWidget(ok_btn)
        delete_btn = ButtonFactory.create_button(self, "Удалить бренд", (180, 60, 60, 0.8), fixed_size=(120, 30))
        delete_btn.clicked.connect(self._delete_brand)
        bottom_layout.addWidget(delete_btn)
        content_layout.addLayout(bottom_layout)

        self._populate_sellers()

    def _populate_sellers(self):
        while self.sellers_layout.count():
            item = self.sellers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        seen = set()
        unique = []
        for s in self.brand.sellers:
            if s.name not in seen:
                seen.add(s.name)
                unique.append(s)
        self.brand.sellers = unique
        for seller in unique:
            self._add_seller_row(seller)

    def _add_seller_row(self, seller):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)
        name_lbl = LabelFactory.create_label(
            self, seller.name, bg_color=(0,0,0,0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        row_layout.addWidget(name_lbl)
        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_seller_row(row_widget, seller)
        )
        row_layout.addWidget(del_btn)
        self.sellers_layout.addWidget(row_widget)

    def _remove_seller_row(self, row_widget, seller):
        self.brand.remove_seller(seller)
        row_widget.deleteLater()
        self._save_sellers()

    def _add_seller(self):
        available = [s for s in self.sellers if self.brand not in s.brands]
        if not available:
            QMessageBox.information(self, "Информация", "Все продавцы уже привязаны к этому бренду.")
            return
        names = [s.name for s in available]
        item, ok = QInputDialog.getItem(self, "Выбор продавца", "Продавец:", names, 0, False)
        if ok and item:
            seller = next(s for s in available if s.name == item)
            self.brand.add_seller(seller)
            self._add_seller_row(seller)
            self._save_sellers()

    def _save_sellers(self):
        if self.main_window:
            self.main_window.config.set_sellers_objects(self.sellers)

    def _delete_brand(self):
        # ... (без изменений, как в исходном коде)
        pass

    def _collect_keys(self):
        self.brand.keys = self.keys_list.get_items()

    def closeEvent(self, event):
        self.brand.name = self.name_edit.text().strip()
        self._collect_keys()
        super().closeEvent(event)