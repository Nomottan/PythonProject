"""
Окно управления продавцами.

Содержит три класса:
    SellersWindow           — список продавцов с действиями.
    CompanyDialog           — редактирование ИНН и юр. лица.
    BrandChecklistDialog    — чек-лист брендов у продавца.

Роль в программе:
    Открывается из MainWindow по кнопке «Продавцы». Работает через
    parent.sellers_brands_service.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout
from PySide6.QtCore import Qt

from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, LayoutFactory,
    ListWidgetFactory, ButtonFactory,
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.base.base_edit_dialog import BaseEditDialog
from models.models import Seller, Brand


class SellersWindow(QMainWindow):
    """Окно со списком продавцов.

    Назначение:
        Показать список продавцов. Позволяет переименовать, задать
        компанию, отметить бренды, отредактировать ключи, удалить.

    Роль в программе:
        Открывается из MainWindow. Список изменяется локально;
        сохранение в config.json — в save_and_close при закрытии окна.
    """

    def __init__(self, parent=None):
        """Конструктор.

        Вход: parent — MainWindow.
        """
        super().__init__(parent)

        self.main_window = parent

        # Читаем бренды и продавцов через сервис.
        brands = parent.sellers_brands_service.get_brands_objects()
        brands_dict = {b.name: b for b in brands}
        self.sellers = parent.sellers_brands_service.get_sellers_objects(brands_dict)

        self.bg_color = (10, 40, 50, 0.9)
        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Список продавцов",
            bg_color=self.bg_color,
            close_button=True,
            draggable=False,
            close_on_click_outside=False,
            center=True,
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=580,
            default_height=450,
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, "Продавцы"))

        scroll, self.sellers_widget, self.sellers_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        content_layout.addWidget(scroll)

        add_btn = ButtonFactory.create_add_button(self, self._add_new_seller)
        LayoutFactory.add_centered_widget(content_layout, add_btn)

        for seller in self.sellers:
            self._add_seller_row(seller)

    # ---------- Строки ----------

    def _add_seller_row(self, seller: Seller) -> None:
        """Добавляет строку продавца с кнопками действий.

        Вход: seller — Seller.
        Роль: слева кнопка удаления, затем имя, «Компания», «Бренды»,
              «Ключи».
        """
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_seller(row, seller),
            size=(25, 25),
        )
        layout.addWidget(del_btn)

        name_btn = ButtonFactory.create_button(
            self, seller.name, (30, 50, 90, 0.8),
            fixed_size=(140, 30),
        )
        name_btn.clicked.connect(
            lambda checked, b=name_btn, s=seller: self._rename_seller(b, s)
        )
        layout.addWidget(name_btn)

        company_btn = ButtonFactory.create_button(
            self, "Компания", (80, 100, 120, 0.7),
            fixed_size=(90, 30),
        )
        company_btn.clicked.connect(lambda: self._edit_company(seller))
        layout.addWidget(company_btn)

        brands_btn = ButtonFactory.create_button(
            self, "Бренды", (80, 100, 120, 0.7),
            fixed_size=(90, 30),
        )
        brands_btn.clicked.connect(lambda: self._edit_brands(seller))
        layout.addWidget(brands_btn)

        keys_btn = ButtonFactory.create_button(
            self, "Ключи", (40, 60, 70, 0.7),
            fixed_size=(30, 30), padding="8px 1px", font_size="8",
        )
        keys_btn.clicked.connect(lambda: self._edit_keys(seller))
        layout.addWidget(keys_btn)

        self.sellers_layout.addWidget(row)

    # ---------- Действия ----------

    def _add_new_seller(self) -> None:
        """Создаёт нового пустого продавца и добавляет строку."""
        new_seller = Seller("Новый продавец")
        self.sellers.append(new_seller)
        self._add_seller_row(new_seller)

    def _remove_seller(self, row_widget, seller: Seller) -> None:
        """Удаляет продавца из списка и удаляет строку.

        Вход: row_widget — виджет строки; seller — Seller.
        """
        if seller in self.sellers:
            self.sellers.remove(seller)
        self.sellers_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _rename_seller(self, btn, seller: Seller) -> None:
        """Инлайн-переименование продавца.

        Вход: btn — кнопка с именем; seller — Seller.
        Роль: подменяет кнопку на QLineEdit, по завершении ввода —
              возвращает кнопку с новым текстом.
        """
        layout = btn.parent().layout()
        idx = layout.indexOf(btn)
        line_edit = InputWidgetFactory.create_line_edit(
            self, text=seller.name,
            bg_color=(100, 80, 130, 0.9),
            text_color="white",
            border_radius=5,
            padding="5px",
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

    def _edit_company(self, seller: Seller) -> None:
        """Открывает диалог редактирования компании."""
        dialog = CompanyDialog(self, seller)
        dialog.show()

    def _edit_brands(self, seller: Seller) -> None:
        """Открывает диалог с чек-листом брендов."""
        brands = self.main_window.sellers_brands_service.get_brands_objects()
        dialog = BrandChecklistDialog(self, seller, brands)
        dialog.show()

    def _edit_keys(self, seller: Seller) -> None:
        """Открывает диалог редактирования ключей."""
        self.main_window.open_string_list_dialog(
            f"Ключи — {seller.name}",
            seller.keys,
        )

    # ---------- Обновление / сохранение ----------

    def refresh_ui(self) -> None:
        """Перестраивает UI с текущим составом self.sellers."""
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        """Очищает и заново строит список строк."""
        while self.sellers_layout.count():
            item = self.sellers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for seller in self.sellers:
            self._add_seller_row(seller)

    def save_and_close(self) -> None:
        """Сохраняет продавцов в config.json и закрывает окно."""
        try:
            self.main_window.sellers_brands_service.set_sellers_objects(self.sellers)
            self.main_window.update_buttons_state()
        except Exception as e:
            import sys
            sys.stderr.write(f"[SellersWindow] Ошибка сохранения: {e}\n")
        finally:
            self.close()

class CompanyDialog(BaseEditDialog):
    """Диалог редактирования компании продавца.

    Назначение:
        Поля: ИНН, юр. лицо. Кнопка «Готово».

    Роль в программе:
        Открывается из SellersWindow по кнопке «Компания».
        Наследник BaseEditDialog: ok_cancel=False, кнопка «Готово»
        в _build_content. Сохранение — по закрытию через on_close.
    """

    def __init__(self, parent, seller: Seller):
        """Конструктор.

        Вход:
            parent — SellersWindow.
            seller — Seller, чью компанию редактируем.
        """
        self.seller = seller
        super().__init__(
            parent=parent,
            title="Компания",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            ok_cancel=False,
            draggable=False,
            close_on_click_outside=True,
            modal=True,
            center=True,
            on_close=self._save_and_close,
            width=400,
            height=350,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _build_content(self, layout) -> None:
        """Поля ИНН и юр. лица + кнопка «Готово».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        self.inn_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.inn,
        )
        self.company_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.company,
        )

        form_container = LayoutFactory.create_form(
            self,
            rows=[
                (
                    LabelFactory.create_label(
                        self, "ИНН:",
                        bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                    ),
                    self.inn_edit,
                ),
                (
                    LabelFactory.create_label(
                        self, "Юр. лицо:",
                        bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                    ),
                    self.company_edit,
                ),
            ],
            alignment=Qt.AlignLeft,
            spacing=10,
        )
        layout.addWidget(form_container)

        # Кнопка «Готово» — закрывает диалог, closeEvent вызовет on_close.
        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        ok_btn.clicked.connect(self.close)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _save_and_close(self) -> None:
        """Переносит ИНН и юр. лицо в модель Seller.

        Роль: вызывается из closeEvent через on_close. Не вызывает
              self.close() — иначе получилась бы рекурсия.
        """
        self.seller.inn = self.inn_edit.text().strip()
        self.seller.company = self.company_edit.text().strip()


class BrandChecklistDialog(BaseEditDialog):
    """Диалог чек-листа брендов у продавца.

    Назначение:
        Отметить/снять бренды у продавца. OK сохраняет, Отмена
        не применяет изменения.

    Роль в программе:
        Открывается из SellersWindow по кнопке «Бренды».
        Наследник BaseEditDialog: ok_cancel=True. Логика
        «добавить/удалить бренд» — в _collect_result.
    """

    def __init__(self, parent, seller: Seller, all_brands: list):
        """Конструктор.

        Вход:
            parent — SellersWindow.
            seller — Seller, чьи бренды редактируем.
            all_brands — все доступные Brand.
        """
        self.seller = seller
        self.all_brands = all_brands
        # Имена уже привязанных брендов — для сортировки «выбранные сверху».
        self.current_names = {b.name for b in seller.brands}
        self.checkboxes = []  # список (QCheckBox, Brand)
        self.bg_color = (40, 30, 50, 0.95)
        super().__init__(
            parent=parent,
            title=f"Бренды — {seller.name}",
            bg_color= self.bg_color,
            close_button=True,
            ok_cancel=True,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            width=400,
            height=450,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _build_content(self, layout) -> None:
        """Строит список чекбоксов брендов.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: заголовок, скролл с чекбоксами. Выбранные бренды
              сверху, невыбранные — снизу.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, f"Бренды — {self.seller.name}",
        ))

        scroll_area, _, content_layout2 = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll_area)

        selected = sorted(
            [b for b in self.all_brands if b.name in self.current_names],
            key=lambda b: b.name.lower(),
        )
        unselected = sorted(
            [b for b in self.all_brands if b.name not in self.current_names],
            key=lambda b: b.name.lower(),
        )

        for brand in selected:
            cb = InputWidgetFactory.create_checkbox(
                self, brand.name, checked=True,
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                object_name="brand_checkbox",
            )
            self.checkboxes.append((cb, brand))
            content_layout2.addWidget(cb)

        for brand in unselected:
            cb = InputWidgetFactory.create_checkbox(
                self, brand.name, checked=False,
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                object_name="brand_checkbox",
                indicator_bg_color=(100, 80, 70),
                indicator_checked_bg_color=(150, 200, 250),
                indicator_border="1px solid #aaaaaa",
            )
            self.checkboxes.append((cb, brand))
            content_layout2.addWidget(cb)

    def _collect_result(self):
        """Применяет изменения чекбоксов к модели Seller.

        Выход: None.
        Роль: по каждому чекбоксу — добавляет или удаляет бренд
              через add_brand/remove_brand (эти методы поддерживают
              двустороннюю связь).
        """
        for cb, brand in self.checkboxes:
            if cb.isChecked() and brand not in self.seller.brands:
                self.seller.add_brand(brand)
            elif not cb.isChecked() and brand in self.seller.brands:
                self.seller.remove_brand(brand)
        return None