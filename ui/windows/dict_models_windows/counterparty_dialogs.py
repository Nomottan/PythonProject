"""
Диалоги справочника контрагентов.

Содержит:
    CounterpartyNameDialog — «Компания», тип, наименование/ФИО.
    CounterpartyCompanyDialog — ИНН, ОГРН/ОГРНИП, КПП, адрес.
    CounterpartyRequisitesDialog — ЭДО ID, ОКТМО.
"""

from PySide6.QtCore import Qt

from models.models import Counterparty
from utils.text_utils import TextUtils
from utils.validations import Validations
from ui.base.base_edit_dialog import BaseEditDialog
from ui.windows.dict_models_windows.address_dialog import AddressDialog
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, LayoutFactory, ButtonFactory,
)
from ui.factories.droplist_factory import DroplistFactory
from ui.factories.tooltip_factory import TooltipController
from ui.styles import ColorCalculator, WindowStyle

class CounterpartyNameDialog(BaseEditDialog):
    """Диалог наименования контрагента.

    Назначение:
        «Компания», тип организации, динамические поля:
        для ООО — «Наименование», для ИП — Фамилия/Имя/Отчество.

    Роль в программе:
        Открывается из CounterpartiesWindow по кликабельному
        лейблу и при добавлении. «Готово» активно только при
        валидном типе и заполненных обязательных полях.
    """

    LOGGER_SOURCE = "CounterpartyNameDialog.counterparty_dialogs"
    LOGGER_DOMAIN = "counterparties"

    def __init__(self, parent, counterparty: Counterparty,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — CounterpartiesWindow.
            counterparty — модель контрагента.
            log_manager_v2 — LogManagerV2 или None.
        """
        self.counterparty = counterparty
        self._syncing = False
        self._tooltip_controller = None
        self._current_org_type = ""

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        r_factor, b_factor = (
            (1.5, 1.0)
            if parent_bg[0] < parent_bg[1]
            else (1.0, 1.5)
        )
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * r_factor),
            g_fn=lambda g: int(g * 1.25),
            b_fn=lambda b: int(b * b_factor),
            alpha=0.95,
        )

        super().__init__(
            parent=parent, title="Наименование",
            bg_color=self.bg_color,
            close_button=True, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=True, center=True,
            on_close=None,
            width=460, height=420,
            log_manager_v2=log_manager_v2,
        )

        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._apply_model_to_fields()

    # ---------- Построение ----------

    def _build_content(self, layout) -> None:
        """Строит поля диалога."""
        self.company_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
        )
        self.org_type_dropdown = DroplistFactory.create_dropdown(
            self,
            config={
                "items": [
                    {"label": "Не опознан", "data": ""},
                    {"label": "ИП", "data": "ИП"},
                    {"label": "ООО", "data": "ООО"},
                ],
                "settings": {
                    "max_length": 200,
                    "editable": False,
                    "auto_select_first": False,
                },
            },
        )
        self.name_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
        )
        self.surname_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
        )
        self.given_name_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
        )
        self.patronymic_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
        )

        self.company_row = self._make_row(
            layout, "Компания:", self.company_edit,
        )
        self.type_row = self._make_row(
            layout, "Тип организации:", self.org_type_dropdown,
        )
        self.name_row = self._make_row(
            layout, "Наименование:", self.name_edit,
        )
        self.surname_row = self._make_row(
            layout, "Фамилия:", self.surname_edit,
        )
        self.given_name_row = self._make_row(
            layout, "Имя:", self.given_name_edit,
        )
        self.patronymic_row = self._make_row(
            layout, "Отчество:", self.patronymic_edit,
        )

        self.ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        self.ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, self.ok_btn)

        self.company_edit.textChanged.connect(self._on_company_text_changed)
        self.company_edit.editingFinished.connect(self._commit_company_tokens)
        self.company_edit.returnPressed.connect(self._commit_company_tokens)
        self.org_type_dropdown.selection_changed.connect(
            self._on_org_type_changed
        )
        self.name_edit.textChanged.connect(self._on_parts_changed)
        self.surname_edit.textChanged.connect(self._on_parts_changed)
        self.given_name_edit.textChanged.connect(self._on_parts_changed)
        self.patronymic_edit.textChanged.connect(self._on_parts_changed)

        self._tooltip_controller = TooltipController(
            self, self.bg_color, logger=self.logger,
        )
        for widget in (
                self.company_edit, self.name_edit, self.surname_edit,
                self.given_name_edit, self.patronymic_edit,
        ):
            self._tooltip_controller.install(widget)

    def _make_row(self, layout, label_text, widget):
        """Создаёт строку «лейбл + поле» и добавляет в layout."""
        label = LabelFactory.create_label(
            self, label_text, bg_color=(0, 0, 0, 0), text_color=None,
            fixed_width=130,
        )
        row = LayoutFactory.create_row(
            self, label, widget,
            alignment=Qt.AlignLeft | Qt.AlignVCenter, spacing=10,
        )
        layout.addWidget(row)
        return row

    # ---------- Заполнение из модели ----------

    def _apply_model_to_fields(self) -> None:
        """Заполняет поля из модели и обновляет видимость."""
        self._syncing = True
        self.company_edit.setText(self.counterparty.company)
        org_type = ""
        if self.counterparty.company.strip():
            org_type = self.counterparty.org_type
            if org_type not in ("ООО", "ИП"):
                org_type = ""

        self._current_org_type = org_type
        self.org_type_dropdown.blockSignals(True)
        self.org_type_dropdown.set_current_data(org_type)
        self.org_type_dropdown.blockSignals(False)

        self._fill_parts_from_company()
        self._syncing = False
        self._update_type_enabled()
        self._update_visibility()
        self._validate_all()

    def _fill_parts_from_company(self) -> None:
        """Разбирает текущую «Компанию» в динамические поля."""
        tokens = TextUtils.tokenize_legal_name(self.company_edit.text())
        match self._current_org_type:
            case "ООО":
                name_tokens = TextUtils.strip_org_type_tokens(tokens, "ООО")
                self._set_name_text(" ".join(name_tokens))
            case "ИП":
                name_tokens = TextUtils.strip_org_type_tokens(tokens, "ИП")
                self._set_fio_from_tokens(name_tokens)
            case _:
                self._set_name_text("")
                self._set_fio_parts("", "", "")

    # ---------- Программная установка полей ----------

    def _set_company_text(self, text: str) -> None:
        """Устанавливает «Компанию» без сигналов."""
        if self.company_edit.text() == text:
            self._update_type_enabled()
            return
        self.company_edit.blockSignals(True)
        self.company_edit.setText(text)
        self.company_edit.blockSignals(False)
        self._update_type_enabled()

    def _set_org_type(self, org_type: str) -> None:
        """Устанавливает тип в dropdown без сигналов."""
        self._current_org_type = org_type
        self.org_type_dropdown.blockSignals(True)
        self.org_type_dropdown.set_current_data(org_type)
        self.org_type_dropdown.blockSignals(False)

    def _set_name_text(self, text: str) -> None:
        """Устанавливает «Наименование» без сигналов."""
        if self.name_edit.text() == text:
            return
        self.name_edit.blockSignals(True)
        self.name_edit.setText(text)
        self.name_edit.blockSignals(False)

    def _set_fio_parts(self, surname: str, given_name: str,
                       patronymic: str) -> None:
        """Устанавливает части ФИО без сигналов."""
        for edit, value in (
            (self.surname_edit, surname),
            (self.given_name_edit, given_name),
            (self.patronymic_edit, patronymic),
        ):
            if edit.text() == value:
                continue
            edit.blockSignals(True)
            edit.setText(value)
            edit.blockSignals(False)

    def _set_fio_from_tokens(self, tokens: list[str]) -> None:
        """Раскладывает токены в Фамилия/Имя/Отчество."""
        surname = tokens[0] if len(tokens) > 0 else ""
        given_name = tokens[1] if len(tokens) > 1 else ""
        patronymic_tokens = tokens[2:] if len(tokens) > 2 else []
        self._set_fio_parts(
            TextUtils.sanitize_fio_part(surname),
            TextUtils.sanitize_fio_part(given_name),
            " ".join(
                TextUtils.sanitize_fio_part(part)
                for part in patronymic_tokens
            ),
        )

    # ---------- Обработчики ----------

    def _on_company_text_changed(self, text: str) -> None:
        """Реакция на ввод в «Компании»: транслит и разделители."""
        if self._syncing:
            return

        if TextUtils.is_latinic(text):
            text = TextUtils.to_cyrillic(text)
            self._set_company_text(text)

        if text and text[-1] in ".,":
            self._set_company_text(text[:-1] + " ")
            self._commit_company_tokens()
            return

        if text.endswith(" "):
            self._commit_company_tokens()

    def _commit_company_tokens(self, *args) -> None:
        """Распределяет токены «Компании» и обновляет поля."""
        if self._syncing:
            return

        text = self.company_edit.text()
        if TextUtils.is_latinic(text):
            text = TextUtils.to_cyrillic(text)
            self._set_company_text(text)

        self._update_type_enabled()

        if not text.strip():
            self._syncing = True
            self._set_org_type("")
            self._set_name_text("")
            self._set_fio_parts("", "", "")
            self._syncing = False
            self._update_visibility()
            self._validate_all()
            return

        tokens = TextUtils.tokenize_legal_name(text)
        detected = Validations.detect_org_type(tokens)

        self._syncing = True
        self._set_org_type(detected)
        match detected:
            case "ООО":
                name_tokens = TextUtils.strip_org_type_tokens(
                    tokens, "ООО",
                )
                self._set_name_text(" ".join(name_tokens))
            case "ИП":
                name_tokens = TextUtils.strip_org_type_tokens(
                    tokens, "ИП",
                )
                self._set_fio_from_tokens(name_tokens)
            case _:
                self._set_name_text("")
                self._set_fio_parts("", "", "")
        self._syncing = False

        self._update_visibility()
        self._validate_all()

    def _on_org_type_changed(self, data) -> None:
        """Реакция на смену типа организации в dropdown."""
        if self._syncing:
            return

        new_type = data if data in ("ООО", "ИП") else ""
        previous = self._current_org_type
        if new_type == previous:
            self._update_visibility()
            self._validate_all()
            return

        self._syncing = True

        match new_type:
            case "":
                match previous:
                    case "ООО":
                        raw = self.name_edit.text().strip()
                    case "ИП":
                        raw = " ".join(
                            part for part in (
                                self.surname_edit.text().strip(),
                                self.given_name_edit.text().strip(),
                                self.patronymic_edit.text().strip(),
                            ) if part
                        )
                    case _:
                        raw = self.company_edit.text().strip()
                self._set_company_text(raw)
                self._set_org_type("")
                self._set_name_text("")
                self._set_fio_parts("", "", "")

            case "ООО":
                match previous:
                    case "ООО":
                        name = self.name_edit.text().strip()
                    case "ИП":
                        name = " ".join(
                            part for part in (
                                self.surname_edit.text().strip(),
                                self.given_name_edit.text().strip(),
                                self.patronymic_edit.text().strip(),
                            ) if part
                        )
                    case _:
                        tokens = TextUtils.tokenize_legal_name(
                            self.company_edit.text()
                        )
                        name = " ".join(tokens).strip()

                name = TextUtils.strip_quotes(name)
                self._set_org_type("ООО")
                self._set_name_text(name)
                self._set_fio_parts("", "", "")
                self._set_company_text(
                    TextUtils.compose_legal_name("ООО", {"name": name})
                )

            case "ИП":
                match previous:
                    case "ИП":
                        surname = self.surname_edit.text().strip()
                        given_name = self.given_name_edit.text().strip()
                        patronymic = self.patronymic_edit.text().strip()
                    case "ООО":
                        tokens = TextUtils.tokenize_legal_name(
                            self.name_edit.text()
                        )
                        surname = tokens[0] if len(tokens) > 0 else ""
                        given_name = tokens[1] if len(tokens) > 1 else ""
                        patronymic = (
                            " ".join(tokens[2:]) if len(tokens) > 2 else ""
                        )
                    case _:
                        tokens = TextUtils.tokenize_legal_name(
                            self.company_edit.text()
                        )
                        surname = tokens[0] if len(tokens) > 0 else ""
                        given_name = tokens[1] if len(tokens) > 1 else ""
                        patronymic = (
                            " ".join(tokens[2:]) if len(tokens) > 2 else ""
                        )

                self._set_org_type("ИП")
                self._set_name_text("")
                self._set_fio_parts(
                    TextUtils.sanitize_fio_part(surname),
                    TextUtils.sanitize_fio_part(given_name),
                    " ".join(
                        TextUtils.sanitize_fio_part(part)
                        for part in TextUtils.split_fio(patronymic)
                    ),
                )
                self._set_company_text(
                    TextUtils.compose_legal_name(
                        "ИП",
                        {
                            "surname": surname,
                            "given_name": given_name,
                            "patronymic": patronymic,
                        },
                    )
                )

        self._syncing = False
        self._update_type_enabled()
        self._update_visibility()
        self._validate_all()

    def _on_parts_changed(self, *args) -> None:
        """Реакция на ввод в динамических полях."""
        if self._syncing:
            return

        for edit in (
            self.name_edit, self.surname_edit,
            self.given_name_edit, self.patronymic_edit,
        ):
            current = edit.text()
            if TextUtils.is_latinic(current):
                edit.blockSignals(True)
                edit.setText(TextUtils.to_cyrillic(current))
                edit.blockSignals(False)

        match self._current_org_type:
            case "ООО":
                name = self.name_edit.text().strip()
                self._set_company_text(
                    TextUtils.compose_legal_name("ООО", {"name": name})
                )
            case "ИП":
                self._set_company_text(
                    TextUtils.compose_legal_name(
                        "ИП",
                        {
                            "surname": self.surname_edit.text().strip(),
                            "given_name": self.given_name_edit.text().strip(),
                            "patronymic": self.patronymic_edit.text().strip(),
                        },
                    )
                )

        self._validate_all()

    # ---------- Видимость и доступность ----------

    def _update_visibility(self) -> None:
        """Показывает только строки текущего типа."""
        is_ooo = self._current_org_type == "ООО"
        is_ip = self._current_org_type == "ИП"
        self.name_row.setVisible(is_ooo)
        self.surname_row.setVisible(is_ip)
        self.given_name_row.setVisible(is_ip)
        self.patronymic_row.setVisible(is_ip)

    def _update_type_enabled(self) -> None:
        """Тип активен, если есть компания или уже выбран тип."""
        enabled = bool(self.company_edit.text().strip()) or (
            self._current_org_type in ("ООО", "ИП")
        )
        self.org_type_dropdown.setEnabled(enabled)

    # ---------- Валидация ----------

    def _validate_all(self) -> None:
        """Обновляет ошибки, tooltip и состояние «Готово»."""
        self._tooltip_controller.clear()

        company_text = self.company_edit.text().strip()
        company_error = ""
        if not company_text:
            company_error = "Введите компанию"
            InputWidgetFactory.set_error_state(self.company_edit, False)
        else:
            company_error = Validations.legal_name_error(company_text)
            InputWidgetFactory.set_error_state(
                self.company_edit, bool(company_error),
            )
            if company_error:
                self._tooltip_controller.set_text(
                    self.company_edit, company_error,
                )

        name_error = ""
        surname_error = ""
        given_name_error = ""
        patronymic_error = ""

        match self._current_org_type:
            case "ООО":
                name_text = self.name_edit.text().strip()
                name_error = "Введите наименование" if not name_text else ""
                if not name_error:
                    composed = TextUtils.compose_legal_name(
                        "ООО", {"name": name_text},
                    )
                    if Validations.legal_name_error(composed):
                        name_error = "Наименование содержит недопустимые символы"
                InputWidgetFactory.set_error_state(
                    self.name_edit, bool(name_error),
                )
                if name_error:
                    self._tooltip_controller.set_text(
                        self.name_edit, name_error,
                    )
            case "ИП":
                surname_error = Validations.fio_part_error(
                    self.surname_edit.text().strip(), "surname",
                )
                given_name_error = Validations.fio_part_error(
                    self.given_name_edit.text().strip(), "given_name",
                )
                patronymic_error = Validations.fio_part_error(
                    self.patronymic_edit.text().strip(), "patronymic",
                )
                for edit, error in (
                    (self.surname_edit, surname_error),
                    (self.given_name_edit, given_name_error),
                    (self.patronymic_edit, patronymic_error),
                ):
                    InputWidgetFactory.set_error_state(edit, bool(error))
                    if error:
                        self._tooltip_controller.set_text(edit, error)
            case _:
                for edit in (
                    self.name_edit, self.surname_edit,
                    self.given_name_edit, self.patronymic_edit,
                ):
                    InputWidgetFactory.set_error_state(edit, False)

        valid = (
            not company_error
            and self._current_org_type in ("ООО", "ИП")
            and (
                (self._current_org_type == "ООО" and not name_error)
                or (
                    self._current_org_type == "ИП"
                    and not surname_error
                    and not given_name_error
                    and not patronymic_error
                )
            )
        )
        self.ok_btn.setEnabled(valid)
        if self.logger is not None:
            self.logger.debug(
                f"tooltip validate: ok={self.ok_btn.isEnabled()}"
            )

    def _validate(self) -> bool:
        """Разрешает accept только при валидном состоянии."""
        self._validate_all()
        return self.ok_btn.isEnabled()

    def _collect_result(self) -> Counterparty:
        """Переносит «Компанию», тип и директора в модель."""
        self.counterparty.company = self.company_edit.text().strip()
        self.counterparty.org_type = self._current_org_type
        if self._current_org_type == "ИП":
            tokens = TextUtils.tokenize_legal_name(
                self.counterparty.company,
            )
            fio_tokens = TextUtils.strip_org_type_tokens(tokens, "ИП")
            self.counterparty.director = " ".join(fio_tokens)
        return self.counterparty

class CounterpartyCompanyDialog(BaseEditDialog):
    """Диалог компании контрагента.

    Назначение:
        ИНН, ОГРН/ОГРНИП, КПП (только ООО), адрес.

    Роль в программе:
        Открывается из CounterpartiesWindow по кнопке «Компания».
        Без блокирующей валидации: «Готово» всегда активно.
    """

    LOGGER_SOURCE = "CounterpartyCompanyDialog.counterparty_dialogs"
    LOGGER_DOMAIN = "counterparties"
    LABEL_WIDTH = 90
    def __init__(self, parent, counterparty: Counterparty,
                 log_manager_v2=None):
        """Конструктор."""
        self.counterparty = counterparty
        self.is_ooo = counterparty.org_type == "ООО"

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 1.1),
            g_fn=lambda g: int(g * 1.1),
            b_fn=lambda b: int(b * 1.2),
            alpha=0.95,
        )
        height = 240 if self.is_ooo else 220

        super().__init__(
            parent=parent, title="Компания",
            bg_color=self.bg_color,
            close_button=True, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=True, center=True,
            on_close=None,
            width=420, height=height,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _build_content(self, layout) -> None:
        """Строит поля компании и адрес."""
        self.director_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self._director_text(),
        )
        if not self.is_ooo:
            self.director_edit.setReadOnly(True)
            self.director_edit.setFocusPolicy(Qt.NoFocus)

        self.inn_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.inn,
        )

        rows = [
            (
                LabelFactory.create_label(
                    self, "Директор:", bg_color=(0, 0, 0, 0),
                    text_color=None, fixed_width=self.LABEL_WIDTH,
                ),
                self.director_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "ИНН:", bg_color=(0, 0, 0, 0),
                    text_color=None, fixed_width=self.LABEL_WIDTH,
                ),
                self.inn_edit,
            ),
        ]

        form_container = LayoutFactory.create_form(
            self, rows=rows, alignment=Qt.AlignLeft, spacing=10,
        )
        layout.addWidget(form_container)

        self.address_field = InputWidgetFactory.create_default_line_edit(
            self, text=str(self.counterparty.address),
        )
        self.address_field.setReadOnly(True)
        self.address_field.setFocusPolicy(Qt.NoFocus)

        self.address_btn = ButtonFactory.create_button(
            self, "Адрес:", (80, 100, 120, 0.7), padding="6px 16px",
        )
        self.address_btn.setFixedWidth(self.LABEL_WIDTH)
        self.address_btn.setFixedHeight(
            self.address_field.sizeHint().height()
        )
        self.address_btn.clicked.connect(self._on_edit_address)

        address_form = LayoutFactory.create_form(
            self,
            rows=[(self.address_btn, self.address_field)],
            alignment=Qt.AlignLeft,
            spacing=10,
        )
        layout.addWidget(address_form)

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _on_edit_address(self) -> None:
        """Открывает AddressDialog."""
        dialog = AddressDialog(
            self, model=self.counterparty.address,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.accepted.connect(self._on_address_accepted)
        dialog.show()

    def _on_address_accepted(self) -> None:
        """Обновляет адрес после подтверждения."""
        dialog = self.sender()
        new_address = dialog.get_result()
        self.counterparty.address = new_address
        self.address_field.setText(str(new_address))

    def _director_text(self) -> str:
        """Возвращает директора: для ИП — ФИО из компании."""
        if self.is_ooo:
            return self.counterparty.director
        tokens = TextUtils.tokenize_legal_name(self.counterparty.company)
        fio_tokens = TextUtils.strip_org_type_tokens(tokens, "ИП")
        return " ".join(fio_tokens)

    def _collect_result(self) -> Counterparty:
        """Переносит директора и ИНН в модель."""
        self.counterparty.inn = self.inn_edit.text().strip()
        self.counterparty.director = self.director_edit.text().strip()
        return self.counterparty

    def _validate(self) -> bool:
        """Без блокирующей валидации."""
        return True

class CounterpartyRequisitesDialog(BaseEditDialog):
    """Диалог реквизитов контрагента.

    Назначение:
        ЭДО ID и ОКТМО.

    Роль в программе:
        Открывается из CounterpartiesWindow по кнопке «Реквизиты».
        Без блокирующей валидации: «Готово» всегда активно.
    """

    LOGGER_SOURCE = "CounterpartyRequisitesDialog.counterparty_dialogs"
    LOGGER_DOMAIN = "counterparties"

    def __init__(self, parent, counterparty: Counterparty,
                 log_manager_v2=None):
        """Конструктор."""
        self.counterparty = counterparty
        self.is_ooo = counterparty.org_type == "ООО"

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 1.1),
            g_fn=lambda g: int(g * 1.1),
            b_fn=lambda b: int(b * 1.2),
            alpha=0.95,
        )
        height = 320 if self.is_ooo else 280

        super().__init__(
            parent=parent, title="Реквизиты",
            bg_color=self.bg_color,
            close_button=True, ok_cancel=False,
            draggable=False, close_on_click_outside=True,
            modal=True, center=True,
            on_close=None,
            width=400, height=height,
            log_manager_v2=log_manager_v2,
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _build_content(self, layout) -> None:
        """Строит поля реквизитов."""
        self.phone_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.phone,
        )
        self.mail_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.mail,
        )
        self.edo_id_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.edo_id,
        )
        self.ogrn_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.ogrn,
        )
        self.oktmo_edit = InputWidgetFactory.create_default_line_edit(
            self, text=self.counterparty.oktmo,
        )

        ogrn_label = "ОГРН:" if self.is_ooo else "ОГРНИП:"
        rows = [
            (
                LabelFactory.create_label(
                    self, "Телефон:", bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.phone_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "Почта:", bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.mail_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "ЭДО ID:", bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.edo_id_edit,
            ),
            (
                LabelFactory.create_label(
                    self, ogrn_label, bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.ogrn_edit,
            ),
            (
                LabelFactory.create_label(
                    self, "ОКТМО:", bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.oktmo_edit,
            ),
        ]

        self.kpp_edit = None
        if self.is_ooo:
            self.kpp_edit = InputWidgetFactory.create_default_line_edit(
                self, text=self.counterparty.kpp,
            )
            rows.append((
                LabelFactory.create_label(
                    self, "КПП:", bg_color=(0, 0, 0, 0),
                    text_color=None,
                ),
                self.kpp_edit,
            ))

        form_container = LayoutFactory.create_form(
            self, rows=rows, alignment=Qt.AlignLeft, spacing=10,
        )
        layout.addWidget(form_container)

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _collect_result(self) -> Counterparty:
        """Переносит реквизиты, невалидные поля не пишет."""
        self.counterparty.edo_id = self.edo_id_edit.text().strip()
        self.counterparty.oktmo = self.oktmo_edit.text().strip()

        phone = self.phone_edit.text().strip()
        phone_error = Validations.phone_error(phone)
        InputWidgetFactory.set_error_state(
            self.phone_edit, bool(phone_error),
        )
        if not phone_error:
            self.counterparty.phone = phone

        mail = self.mail_edit.text().strip()
        mail_ok = (mail == "") or ("@" in mail)
        InputWidgetFactory.set_error_state(self.mail_edit, not mail_ok)
        if mail_ok:
            self.counterparty.mail = mail

        ogrn = self.ogrn_edit.text().strip()
        ogrn_ok = (
            (ogrn == "") or (ogrn.isdigit() and len(ogrn) in (13, 15))
        )
        InputWidgetFactory.set_error_state(self.ogrn_edit, not ogrn_ok)
        if ogrn_ok:
            self.counterparty.ogrn = ogrn

        if self.kpp_edit is not None:
            kpp = self.kpp_edit.text().strip()
            kpp_ok = (kpp == "") or (kpp.isdigit() and len(kpp) == 9)
            InputWidgetFactory.set_error_state(self.kpp_edit, not kpp_ok)
            if kpp_ok:
                self.counterparty.kpp = kpp

        return self.counterparty

    def _validate(self) -> bool:
        """Без блокирующей валидации."""
        return True