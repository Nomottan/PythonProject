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

from PySide6.QtCore import Qt
from ui.windows.dict_models_windows.address_dialog import AddressDialog
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, LayoutFactory, ButtonFactory,
)
from services.sellers_brands_service import SellersBrandsService
from ui.windows.dict_models_windows.counterparties_window import (
    CounterpartiesWindow,
)
from ui.windows.shared_dialogs import StringListDialog
from ui.base.base_edit_dialog import BaseEditDialog
from ui.base.base_checklist_dialog import ChecklistDialog
from ui.styles import ColorCalculator, WindowStyle
from models.models import Seller


class SellersWindow(CounterpartiesWindow):
    """Окно справочника продавцов.

    Назначение:
        Список продавцов: удаление, свободное имя, юр. наименование,
        «Компания», «Реквизиты», «Доп» с приоритетом, «Бренды».

    Роль в программе:
        Уровень 1, fill_parent=True. Наследует CounterpartiesWindow.
        Данные — SellersBrandsService, ключ "sellers".
    """

    LOGGER_SOURCE = "SellersWindow.dict_models_windows"
    LOGGER_DOMAIN = "sellers"
    WINDOW_TITLE = "Продавцы"
    WINDOW_NAME = "sellers"
    objectName = "sellers_window"

    def _resolve_bg_color(self):
        """Считает фон Seller от MainWindow: -60%, -10%, -10%."""
        parent = self.main_window
        if parent is None:
            parent_bg = (0, 0, 0, 0)
        else:
            parent_bg = WindowStyle.resolve_parent_bg(
                parent, getattr(parent, "bg_color", (0, 0, 0, 0)),
            )
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 0.4),
            g_fn=lambda g: int(g * 0.9),
            b_fn=lambda b: int(b * 0.9),
        )
        return self.bg_color

    def _create_service(self):
        """Создаёт SellersBrandsService."""
        return SellersBrandsService(
            self.main_window.main_config,
            self.log_manager_v2,
        )

    def _load_items(self) -> list:
        """Загружает продавцов с восстановленными брендами."""
        if self.service is None:
            self.service = self._create_service()
        sellers = self.service.get_sellers_with_brands()
        if not isinstance(sellers, list):
            if self.logger is not None:
                self.logger.critical(
                    "SellersWindow: get_sellers_with_brands "
                    "вернул не список",
                    can_influence=False,
                )
            sellers = []
        self.items = sellers
        return self.items

    def _save_items(self) -> None:
        """Сохраняет продавцов через сервис."""
        if self.service is None:
            self.service = self._create_service()
        if not isinstance(self.items, list):
            if self.logger is not None:
                self.logger.critical(
                    "SellersWindow: self.items не список, "
                    "сохранение отменено",
                    can_influence=False,
                )
            return
        self.service.set_sellers_objects(self.items)

    def _create_new_item(self) -> Seller:
        """Создаёт нового продавца."""
        return Seller("Новый продавец")

    def _edit_company(self, item: Seller) -> None:
        """Открывает CompanyDialog для продавца."""
        dialog = CompanyDialog(self, item, self.log_manager_v2)
        dialog.finished.connect(self._on_dialog_finished)
        dialog.show()

    def _edit_requisites(self, item: Seller) -> None:
        """Открывает RequisitesDialog для продавца."""
        dialog = RequisitesDialog(self, item, self.log_manager_v2)
        dialog.finished.connect(self._on_dialog_finished)
        dialog.show()

    def _on_dialog_finished(self, result: int) -> None:
        """Сохраняет продавцов после закрытия диалога."""
        self._save_items()

    def _edit_keys(self, item: Seller) -> None:
        """Открывает редактор ключей с приоритетом."""
        dialog = StringListDialog(
            self,
            title=f"Дополнительно — {self._display_name(item)}",
            strings=item.keys,
            seller=item,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.accepted.connect(self._save_items)
        dialog.show()

    def _add_extra_buttons(self, layout, item: Seller,
                           button_bg) -> None:
        """Добавляет «Доп» с приоритетом и «Бренды»."""
        super()._add_extra_buttons(layout, item, button_bg)
        brands_btn = ButtonFactory.create_button(
            self, "Бренды", button_bg, fixed_size=(90, 30),
        )
        brands_btn.clicked.connect(lambda: self._on_brands(item))
        layout.addWidget(brands_btn)

    def _on_brands(self, item: Seller) -> None:
        """Открывает чек-лист брендов продавца."""
        brands = self.service.get_brands_objects()
        if not isinstance(brands, list):
            if self.logger is not None:
                self.logger.critical(
                    "SellersWindow: get_brands_objects вернул не список",
                    can_influence=False,
                )
            return
        dialog = BrandChecklistDialog(
            self, item, brands, self.log_manager_v2,
        )
        dialog.accepted.connect(self._save_items)
        dialog.show()

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
        tax_text = self.tax_edit.text().strip()
        try:
            tax = int(tax_text)
            if tax < 0:
                raise ValueError("tax < 0")
            self.seller.tax = tax
        except (TypeError, ValueError) as e:
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
        dialog = AddressDialog(
            self, model=self.seller.address,
            log_manager_v2=self.log_manager_v2,
        )
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