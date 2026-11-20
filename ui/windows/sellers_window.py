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

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QDialog
from PySide6.QtCore import Qt
from ui.windows.address_dialog import AddressDialog
from utils.log_tools.decorators import log_button_action
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, LayoutFactory,
    ListWidgetFactory, ButtonFactory,
)
from ui.windows.shared_dialogs import StringListDialog
from ui.factories.window_factories import ExtendedWindowFactory
from ui.base.base_edit_dialog import BaseEditDialog
from ui.base.base_checklist_dialog import ChecklistDialog
from ui.styles import ColorCalculator, WindowStyle
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

    LOGGER_SOURCE = "SellersWindow.sellers_window"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent=None, log_manager_v2=None):
        super().__init__(parent)
        """Конструктор.

        Вход: parent — MainWindow.
        """

        self.main_window = parent
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )
        # Читаем бренды и продавцов через сервис.
        self.service_window = self
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
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=580,
            default_height=450,
        )

        # Регистрация в WindowManager: SellersWindow — псевдосервисное
        # окно (не модальное, занимает область родителя с отступами).
        if parent is not None and hasattr(parent, "window_manager"):
            parent.window_manager.register_window(
                self, parent=parent, fill_parent=True, modal=False,
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
        # Создание кнопок
        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_seller(row, seller),
            size=(25, 25),
        )
        name_btn = ButtonFactory.create_button(
            self, seller.name, (30, 50, 90, 0.8),
            fixed_size=(140, 30),
        )
        company_btn = ButtonFactory.create_button(
            self, "Компания", (80, 100, 120, 0.7),
            fixed_size=(90, 30),
        )
        requisites_btn = ButtonFactory.create_button(
            self, "Реквизиты", (80, 100, 120, 0.7),
            fixed_size=(90, 30),
        )
        brands_btn = ButtonFactory.create_button(
            self, "Бренды", (80, 100, 120, 0.7),
            fixed_size=(90, 30),
        )
        keys_btn = ButtonFactory.create_button(
            self, "Доп", (40, 60, 70, 0.7),
            fixed_size=(30, 30), padding="8px 1px", font_size="8",
        )

        # Подключение кнопок
        name_btn.clicked.connect(
            lambda checked, b=name_btn, s=seller: self._rename_seller(b, s)
        )
        company_btn.clicked.connect(lambda: self._edit_company(seller))
        requisites_btn.clicked.connect(lambda: self._edit_requisites(seller))
        brands_btn.clicked.connect(lambda: self._edit_brands(seller))
        keys_btn.clicked.connect(lambda: self._edit_keys(seller))

        #Макет
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        layout.addStretch()
        layout.addWidget(del_btn)
        layout.addWidget(name_btn)
        layout.addWidget(company_btn)
        layout.addWidget(requisites_btn)
        layout.addWidget(brands_btn)
        layout.addWidget(keys_btn)
        layout.addStretch()
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
            text_color=None,
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

    @log_button_action(
        "open_edit_company",
        "Ошибка при открытии окна 'Редактирование данных о компании': {e}",
    )
    def _edit_company(self, seller: Seller) -> None:
        dialog = CompanyDialog(
            self, seller, log_manager_v2=self.log_manager_v2,
        )
        dialog.show()

    @log_button_action(
        "open_edit_brands",
        "Ошибка при открытии окна 'Редактирование данных о брендах компании': {e}",
    )
    def _edit_brands(self, seller: Seller) -> None:
        brands = self.main_window.sellers_brands_service.get_brands_objects()
        dialog = BrandChecklistDialog(
            self, seller, brands, log_manager_v2=self.log_manager_v2,
        )
        dialog.show()

    @log_button_action(
        "_edit_requisites",
        "Ошибка при открытии окна 'Редактирование данных реквизитах компании': {e}",
    )
    def _edit_requisites(self, seller: Seller) -> None:
        dialog = RequisitesDialog(
            self, seller, log_manager_v2=self.log_manager_v2,
        )
        dialog.show()

    @log_button_action(
        "open_edit_keys",
        "Ошибка при открытии окна 'Редактирование служебных данных': {e}",
    )
    def _edit_keys(self, seller: Seller) -> None:
        """Открывает диалог редактирования ключей продавца.

        Роль: диалог создаётся здесь, а не через MainWindow —
              это окно знает и про seller, и про log_manager_v2.
              Пробрасывает seller — диалог покажет приоритет.
        """
        if self.logger:
            self.logger.debug(
                f"_edit_keys: seller={seller.name}, "
                f"priority={seller.priority}"
            )
        dialog = StringListDialog(
            parent=self,
            title=f"Дополнительно — {seller.name}",
            strings=seller.keys,
            seller=seller,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.show()

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
        try:
            self.main_window.sellers_brands_service.set_sellers_objects(self.sellers)
            self.main_window.update_buttons_state()
        except Exception as e:
            if self.logger is not None:
                self.logger.critical(
                    f"Ошибка сохранения продавцов: {e}",
                    can_influence=False,
                )
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

    LOGGER_SOURCE = "CompanyDialog.sellers_window"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent, seller: Seller, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — SellersWindow.
            seller — Seller, чью компанию редактируем.
        """
        self.seller = seller

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 1.5),
            g_fn=lambda g: int(g * 0.8),
            b_fn=lambda b: int(b * 1.2),
            alpha=0.95,
        )

        super().__init__(
            parent=parent, title="Компания",
            bg_color=self.bg_color,
            close_button=False, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=True, center=True,
            on_close=self._save_and_close,
            width=400, height=150,
            log_manager_v2=log_manager_v2,
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
        self.tax_edit = InputWidgetFactory.create_default_line_edit(
            self, text=str(self.seller.tax),
        )
        form_container = LayoutFactory.create_form(
            self,
            rows=[
                (
                    LabelFactory.create_label(
                        self, "ИНН:",
                        bg_color=(0, 0, 0, 0), text_color=None,
                    ),
                    self.inn_edit,
                ),
                (
                    LabelFactory.create_label(
                        self, "Юр. лицо:",
                        bg_color=(0, 0, 0, 0), text_color=None,
                    ),
                    self.company_edit,
                ),
                (
                    LabelFactory.create_label(
                        self, "НДС:",
                        bg_color=(0, 0, 0, 0), text_color=None,
                    ),
                    self.tax_edit,
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
        try:
            self.seller.tax = int(self.tax_edit.text().strip())
        except Exception as e:
            if self.logger is not None:
                self.logger.critical(
                    f"Налоговая ставка не была сохранена: {e}",
                    can_influence=False,
                )

class BrandChecklistDialog(ChecklistDialog):
    """Диалог чек-листа брендов у продавца.

    Назначение:
        Отметить/снять бренды у продавца. OK применяет изменения
        к модели Seller in-memory, Отмена — ничего не делает.

    Роль в программе:
        Открывается из SellersWindow по кнопке «Бренды» через
        show(). Наследник ChecklistDialog: каркас, список
        чекбоксов и сбор результата — в базе. Здесь только
        логика «бренд ↔ продавец» и цвета.
    """

    LOGGER_SOURCE = "BrandChecklistDialog.sellers_window"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent, seller: Seller, all_brands: list,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — SellersWindow.
            seller — Seller, чьи бренды редактируем.
            all_brands — все доступные Brand.
            log_manager_v2 — LogManagerV2 или None.
        """
        self.seller = seller
        self.all_brands = all_brands
        # Имена уже привязанных брендов — для сортировки
        # «выбранные сверху» через _is_item_checked.
        self.current_names = {b.name for b in seller.brands}

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 0.95),
            g_fn=lambda g: int(g * 1.5),
            b_fn=lambda b: int(b * 1.5),
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title=f"Бренды — {seller.name}",
            bg_color=self.bg_color,
            close_button=True,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            width=400,
            height=450,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    # ---------- Абстрактные методы ChecklistDialog ----------

    def _get_items(self) -> list:
        """Полный список брендов для показа."""
        return self.all_brands

    def _get_item_label(self, item) -> str:
        """Подпись чекбокса — имя бренда."""
        return item.name

    def _is_item_checked(self, item) -> bool:
        """Связан ли бренд с продавцом на момент открытия."""
        return item.name in self.current_names

    def _apply_result(self, checked: list, unchecked: list) -> None:
        """Применяет отметки к модели Seller.

        Вход:
            checked — бренды, отмеченные пользователем.
            unchecked — бренды, с которых галка снята.

        Выход: нет.

        Роль:
            Мутация моделей Seller/Brand in-memory. Сохранение
            в config.json — на SellersWindow.save_and_close
            (раз в конце работы окна, не по каждому чекбоксу).
            add_brand/remove_brand поддерживают двустороннюю
            связь Brand.sellers ↔ Seller.brands.
        """
        for brand in checked:
            if brand not in self.seller.brands:
                self.seller.add_brand(brand)
        for brand in unchecked:
            if brand in self.seller.brands:
                self.seller.remove_brand(brand)

    # ---------- Опциональные hooks ----------

    def _get_header_text(self) -> str:
        """Заголовок над списком."""
        return f"Бренды — {self.seller.name}"

    def _get_item_sort_key(self, item) -> str:
        """Сортировка по имени бренда (регистронезависимо)."""
        return item.name.lower()

    def _get_checkbox_object_name(self) -> str:
        """objectName чекбоксов — сохранён из прежней версии."""
        return "brand_checkbox"

class RequisitesDialog(BaseEditDialog):
    """Диалог редактирования реквизитов продавца.

    Назначение:
        Поля: телефон, почта, ЭДО ID, ОГРН, адрес.
        КПП и Директор — только если seller.company начинается
        на «ООО». Кнопка «Готово» закрывает диалог, closeEvent
        вызывает _save_and_close.

    Роль в программе:
        Открывается из SellersWindow по кнопке «Реквизиты».
        Наследник BaseEditDialog: ok_cancel=False, кнопка «Готово»
        в _build_content. Сохранение — по закрытию через on_close.
    """

    def __init__(self, parent, seller: Seller, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — SellersWindow.
            seller — Seller, чьи реквизиты редактируем.
            log_manager_v2 — LogManagerV2 или None.
        """
        self.seller = seller
        # ООО — показываем КПП и Директора, иначе — скрываем.
        self._is_ooo = seller.company.strip().upper().startswith("ООО")
        _height = 280 if self._is_ooo else 220
        print(f"[REQ] _is_ooo={self._is_ooo}, _height={_height}, company={self.seller.company!r}")
        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 0.95),
            g_fn=lambda g: int(g * 1.5),
            b_fn=lambda b: int(b * 1.5),
            alpha=0.95,
        )

        super().__init__(
            parent=parent, title="Реквизиты",
            bg_color=self.bg_color,
            close_button=False, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=True, center=True,
            on_close=self._save_and_close,
            width=300, height=_height,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _build_content(self, layout) -> None:
        """Строит поля реквизитов и адреса + кнопку «Готово».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        self.phone_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.phone,
        )
        self.mail_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.mail,
        )
        self.edo_id_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.edo_id,
        )
        self.ogrn_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.seller.ogrn,
        )

        rows = [
            (
                LabelFactory.create_label(
                    self, "Телефон:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.phone_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "Почта:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.mail_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "ЭДО ID:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.edo_id_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "ОГРН:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.ogrn_edit,
            ),
        ]

        # КПП и Директор — только для ООО.
        self.kpp_edit = None
        self.director_edit = None
        if self._is_ooo:
            self.kpp_edit = InputWidgetFactory.create_default_line_edit(
                self, text=self.seller.kpp,
            )
            self.director_edit = InputWidgetFactory.create_default_line_edit(
                self, text=self.seller.director,
            )
            rows.append((
                LabelFactory.create_label(
                    self, "КПП:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.kpp_edit,
            ))
            rows.append((
                LabelFactory.create_label(
                    self, "Директор:",
                    bg_color=(0, 0, 0, 0), text_color=None,
                ),
                self.director_edit,
            ))

        form_container = LayoutFactory.create_form(
            self,
            rows=rows,
            alignment=Qt.AlignLeft,
            spacing=10,
        )
        layout.addWidget(form_container)

        self.address_field = InputWidgetFactory.create_default_line_edit(
            self, text=str(self.seller.address),
        )
        self.address_field.setReadOnly(True)
        self.address_field.setFocusPolicy(Qt.NoFocus)

        self.address_btn = ButtonFactory.create_button(
            self, "Адрес:", (80, 100, 120, 0.7),
            padding="6px 16px",
        )
        self.address_btn.setFixedHeight(
            self.address_field.sizeHint().height()
        )
        self.address_btn.clicked.connect(self._on_edit_address)

        address_form = LayoutFactory.create_form(
            self,
            rows=[
                (self.address_btn, self.address_field),
            ],
            alignment=Qt.AlignLeft,
            spacing=10,
        )
        layout.addWidget(address_form)

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        ok_btn.clicked.connect(self.close)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _on_edit_address(self) -> None:
        """Открывает AddressDialog и обновляет адрес при подтверждении.

        Роль:
            Если пользователь сохранил адрес в AddressDialog, поле
            self.seller.address заменяется на новое, лейбл рядом
            с кнопкой обновляется. При отмене — ничего не меняется.
        """
        dialog = AddressDialog(self, model=self.seller.address)
        dialog.accepted.connect(self._on_address_accepted)
        dialog.show()

    def _on_address_accepted(self) -> None:
        """Вызывается при подтверждении AddressDialog."""
        dialog = self.sender()
        new_address = dialog.get_result()
        self.seller.address = new_address
        self.address_field.setText(str(new_address))

    def _save_and_close(self) -> None:
        """Переносит валидные поля в модель Seller.

        Роль:
            Вызывается из closeEvent через on_close. Не вызывает
            self.close() — иначе была бы рекурсия.

        Валидация:
            phone, edo_id — пишутся всегда.
            mail — пишется, если пусто или содержит «@».
            kpp — пишется, если пусто или 9 цифр.
            ogrn — пишется, если пусто или 13/15 цифр.
            Невалидное значение в модель не пишется, поле
            подсвечивается через set_error_state.
            Адрес уже обновлён через AddressDialog — здесь не трогается.
        """
        self.seller.phone = self.phone_edit.text().strip()
        self.seller.edo_id = self.edo_id_edit.text().strip()

        mail = self.mail_edit.text().strip()
        mail_ok = (mail == "") or ("@" in mail)
        InputWidgetFactory.set_error_state(self.mail_edit, not mail_ok)
        if mail_ok:
            self.seller.mail = mail

        ogrn = self.ogrn_edit.text().strip()
        ogrn_ok = (ogrn == "") or (ogrn.isdigit() and len(ogrn) in (13, 15))
        InputWidgetFactory.set_error_state(self.ogrn_edit, not ogrn_ok)
        if ogrn_ok:
            self.seller.ogrn = ogrn

        kpp_edit = getattr(self, "kpp_edit", None)
        if kpp_edit is not None:
            kpp = kpp_edit.text().strip()
            kpp_ok = (kpp == "") or (kpp.isdigit() and len(kpp) == 9)
            InputWidgetFactory.set_error_state(kpp_edit, not kpp_ok)
            if kpp_ok:
                self.seller.kpp = kpp

        director_edit = getattr(self, "director_edit", None)
        if director_edit is not None:
            self.seller.director = director_edit.text().strip()