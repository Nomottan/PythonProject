from PySide6.QtWidgets import QMainWindow, QDialog, QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, LayoutFactory,
    ListWidgetFactory, ButtonFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from models.models import Seller, Brand

class SellersWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

        brands = parent.config.get_brands_objects()
        brands_dict = {b.name: b for b in brands}
        self.sellers = parent.config.get_sellers_objects(brands_dict)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Список продавцов",
            bg_color=(10, 40, 50, 0.9),
            close_button=True,
            draggable=False,
            close_on_click_outside=False,
            modal=False,
            center=True,
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=580,
            default_height=450
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, "Продавцы"))

        scroll, self.sellers_widget, self.sellers_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=2
        )
        content_layout.addWidget(scroll)

        add_btn = ButtonFactory.create_add_button(self, self._add_new_seller)
        LayoutFactory.add_centered_widget(content_layout, add_btn)

        for seller in self.sellers:
            self._add_seller_row(seller)

    # ---------- Методы управления строками ----------
    def _add_seller_row(self, seller):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_seller(row, seller),
            size=(25, 25)
        )
        layout.addWidget(del_btn)

        name_btn = ButtonFactory.create_button(
            self, seller.name, (30, 50, 90, 0.8),
            fixed_size=(140, 30)
        )
        name_btn.clicked.connect(lambda checked, b=name_btn, s=seller: self._rename_seller(b, s))
        layout.addWidget(name_btn)

        company_btn = ButtonFactory.create_button(
            self, "Компания", (80, 100, 120, 0.7),
            fixed_size=(90, 30)
        )
        company_btn.clicked.connect(lambda: self._edit_company(seller))
        layout.addWidget(company_btn)

        brands_btn = ButtonFactory.create_button(
            self, "Бренды", (80, 100, 120, 0.7),
            fixed_size=(90, 30)
        )
        brands_btn.clicked.connect(lambda: self._edit_brands(seller))
        layout.addWidget(brands_btn)

        keys_btn = ButtonFactory.create_button(
            self, "Ключи", (40, 60, 70, 0.7),
            fixed_size=(30, 30), padding="8px 1px", font_size="8"
        )
        keys_btn.clicked.connect(lambda: self._edit_keys(seller))
        layout.addWidget(keys_btn)



        self.sellers_layout.addWidget(row)

    def _add_new_seller(self):
        new_seller = Seller("Новый продавец")
        self.sellers.append(new_seller)
        self._add_seller_row(new_seller)

    def _remove_seller(self, row_widget, seller):
        if seller in self.sellers:
            self.sellers.remove(seller)
        self.sellers_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _rename_seller(self, btn, seller):
        layout = btn.parent().layout()
        idx = layout.indexOf(btn)
        line_edit = InputWidgetFactory.create_line_edit(
            self, text=seller.name,
            bg_color=(100, 80, 130, 0.9),
            text_color="white",
            border_radius=5,
            padding="5px"
        )
        line_edit.setFixedWidth(btn.width())
        layout.insertWidget(idx, line_edit)
        btn.hide()

        def finish_edit():
            new_name = line_edit.text().strip()
            if new_name:
                seller.name = new_name
                btn.setText(new_name)
            line_edit.deleteLater()
            btn.show()
            btn.adjustSize()

        line_edit.editingFinished.connect(finish_edit)
        line_edit.returnPressed.connect(finish_edit)
        line_edit.setFocus()

    def _edit_company(self, seller):
        dialog = CompanyDialog(self, seller)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def _edit_brands(self, seller):
        brands = self.main_window.config.get_brands_objects()
        dialog = BrandChecklistDialog(self, seller, brands)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.show()

    def refresh_ui(self):
        self._rebuild_ui()

    def _rebuild_ui(self):
        while self.sellers_layout.count():
            item = self.sellers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for seller in self.sellers:
            self._add_seller_row(seller)

    def _edit_keys(self, seller):
        self.main_window.open_string_list_dialog(
            f"Ключи — {seller.name}",
            seller.keys
        )

    def save_and_close(self):
        self.main_window.config.set_sellers_objects(self.sellers)
        self.main_window.update_buttons_state()
        self.close()

class CompanyDialog(QMainWindow):
    def __init__(self, parent, seller: Seller):
        super().__init__(parent)
        self.seller = seller

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Компания",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            draggable=False,
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

        self.inn_edit = InputWidgetFactory.create_default_line_edit(self, text=seller.inn)
        self.company_edit = InputWidgetFactory.create_default_line_edit(self, text=seller.company)

        form_container = LayoutFactory.create_form(
            self,
            rows=[
                (LabelFactory.create_label(self, "ИНН:", bg_color=(0,0,0,0), text_color="#d4d4d4"), self.inn_edit),
                (LabelFactory.create_label(self, "Юр. лицо:", bg_color=(0,0,0,0), text_color="#d4d4d4"), self.company_edit)
            ],
            alignment=Qt.AlignLeft,
            spacing=10
        )
        content_layout.addWidget(form_container)

    def _save_and_close(self):
        self.seller.inn = self.inn_edit.text().strip()
        self.seller.company = self.company_edit.text().strip()
        self.close()

class BrandChecklistDialog(QMainWindow):
    def __init__(self, parent, seller: Seller, all_brands: list[Brand]):
        super().__init__(parent)
        self.seller = seller
        self.all_brands = all_brands
        self.current_names = {b.name for b in seller.brands}

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=f"Бренды — {seller.name}",
            bg_color=(40, 30, 50, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            ok_cancel=True,
            ok_callback=self.accept,
            cancel_callback=self.reject,
            return_content_layout=True,
            default_width=400,
            default_height=450
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, f"Бренды — {seller.name}"))

        scroll_area, content_widget, content_layout2 = ListWidgetFactory.create_scroll_container(
            self, spacing=2
        )
        content_layout.addWidget(scroll_area)

        selected = sorted([b for b in self.all_brands if b.name in self.current_names],
                          key=lambda b: b.name.lower())
        unselected = sorted([b for b in self.all_brands if b.name not in self.current_names],
                            key=lambda b: b.name.lower())

        self.checkboxes = []
        for brand in selected:
            cb = InputWidgetFactory.create_checkbox(
                self, brand.name, checked=True,
                bg_color=(0,0,0,0), text_color="#d4d4d4",
                object_name="brand_checkbox"
            )
            self.checkboxes.append((cb, brand))
            content_layout2.addWidget(cb)
        for brand in unselected:
            cb = InputWidgetFactory.create_checkbox(
                self, brand.name, checked=False,
                bg_color=(0,0,0,0), text_color="#d4d4d4",
                object_name="brand_checkbox",
                indicator_bg_color=(100, 80, 70),
                indicator_checked_bg_color=(150, 200, 250),
                indicator_border="1px solid #aaaaaa"
            )
            self.checkboxes.append((cb, brand))
            content_layout2.addWidget(cb)

    def accept(self):
        for cb, brand in self.checkboxes:
            if cb.isChecked() and brand not in self.seller.brands:
                self.seller.add_brand(brand)
            elif not cb.isChecked() and brand in self.seller.brands:
                self.seller.remove_brand(brand)
        self.close()

    def reject(self):
        self.close()