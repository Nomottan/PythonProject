"""Диалог редактирования адреса."""

import os

from PySide6.QtCore import Qt


from models.models import AddressModel
from utils.input_validators import CPValid
from utils.regions import Regions
from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.input_factory import InputWidgetFactory
from ui.factories.button_factory import ButtonFactory
from ui.factories.layout_factory import LayoutFactory
from ui.factories.element_factory import LabelFactory
from ui.factories.base_factory import BaseWidgetFactory
from ui.styles import ColorCalculator
from ui.factories.droplist_factory import DroplistFactory
from ui.windows.message_dialog import MessageDialog


class AddressDialog(BaseEditDialog):
    """Диалог редактирования адреса."""

    def __init__(self, parent=None, model: AddressModel = None,
                 title: str = "Адрес", bg_color: tuple = None,
                 log_manager_v2=None):
        """Конструктор."""
        self._model = model or AddressModel()

        if bg_color is None:
            parent_bg = parent.bg_color if parent and hasattr(parent, "bg_color") else (40, 50, 60, 1.0)
            bg_color = ColorCalculator.derive(
                parent_bg,
                r_fn=lambda r: r + 20,
                g_fn=lambda g: g + 20,
                b_fn=lambda b: b + 20,
                alpha=1.0,
            )

        Regions.reload()

        super().__init__(
            parent=parent, title=title, bg_color=bg_color,
            width=460, height=520, ok_cancel=False, modal=True,
            log_manager_v2=log_manager_v2,
        )
        self._populate_from_model()

    def _build_content(self, layout) -> None:
        """Строит интерфейс диалога."""
        element_bg = BaseWidgetFactory.resolve_element_bg(self)

        layout.addWidget(
            LabelFactory.create_header_label(self, self.windowTitle())
        )

        def add_row(label_text, widget):
            row = LayoutFactory.create_row(
                self,
                LabelFactory.create_header_label(
                    self, label_text,
                    fixed_width=110, alignment=Qt.AlignRight | Qt.AlignVCenter,
                ),
                widget,
                alignment=Qt.AlignLeft | Qt.AlignVCenter, spacing=6,
            )
            layout.addWidget(row)

        self.index_edit = InputWidgetFactory.create_line_edit(
            self, placeholder="Индекс", bg_color=element_bg
        )
        self.index_edit.editingFinished.connect(self._validate_index)
        add_row("Индекс", self.index_edit)

        self.code_edit = InputWidgetFactory.create_line_edit(
            self, placeholder="Код региона", bg_color=element_bg
        )
        self.code_edit.editingFinished.connect(self._on_code_finished)
        add_row("Код региона", self.code_edit)

        region_items = [
            {"label": name, "data": code}
            for code, name in Regions.get_all().items()
        ]
        self.region_dropdown = DroplistFactory.create_dropdown(
            self,
            config={
                "items": region_items,
                "settings": {
                    "editable": True,
                    "auto_select_first": False,
                    "completer_filter_mode": "contains",
                    "completer_case_sensitive": False,
                    "popup_bg_color": element_bg,
                },
            },
        )
        self.region_dropdown.editing_finished.connect(self._on_region_finished)
        self.region_dropdown.selection_changed.connect(
            lambda _data: self._on_region_finished()
        )

        # Кликабельный лейбл вместо кнопки для открытия файла
        region_label = LabelFactory.create_header_label(
            self, "Регионы",
            fixed_width=110, alignment=Qt.AlignRight | Qt.AlignVCenter,
            clickable=True, on_click=self._on_open_regions_file
        )
        region_label.setToolTip("Открыть файл справочника регионов")

        region_row = LayoutFactory.create_row(
            self, region_label, self.region_dropdown,
            alignment=Qt.AlignLeft | Qt.AlignVCenter, spacing=6,
        )
        layout.addWidget(region_row)

        self.city_edit = InputWidgetFactory.create_line_edit(self, bg_color=element_bg)
        add_row("Город", self.city_edit)

        self.settlement_edit = InputWidgetFactory.create_line_edit(self, bg_color=element_bg)
        add_row("Насел. пункт", self.settlement_edit)

        self.street_edit = InputWidgetFactory.create_line_edit(self, bg_color=element_bg)
        add_row("Улица", self.street_edit)

        self.house_edit = InputWidgetFactory.create_line_edit(self, bg_color=element_bg)
        add_row("Дом", self.house_edit)

        self.building_edit = InputWidgetFactory.create_line_edit(self, bg_color=element_bg)
        add_row("Корпус", self.building_edit)

        save_btn = ButtonFactory.create_button(
            self, "Сохранить", bg_color=(70, 120, 90)
        )
        save_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, save_btn)

    def _populate_from_model(self) -> None:
        """Заполняет поля значениями модели."""
        self.index_edit.setText(self._model.index)
        self.code_edit.setText(self._model.region_code)

        self.region_dropdown.blockSignals(True)
        self.region_dropdown.setCurrentText(self._model.region_name)
        self.region_dropdown.blockSignals(False)

        self.city_edit.setText(self._model.city)
        self.settlement_edit.setText(self._model.settlement)
        self.street_edit.setText(self._model.street)
        self.house_edit.setText(self._model.house)
        self.building_edit.setText(self._model.building)

    def _on_code_finished(self) -> None:
        """Обработчик завершения ввода кода региона."""
        code = self.code_edit.text().strip()
        if not code:
            self.region_dropdown.blockSignals(True)
            self.region_dropdown.setCurrentText("")
            self.region_dropdown.blockSignals(False)
            InputWidgetFactory.set_error_state(self.code_edit, True)
            return

        name = Regions.get_region_name(code)
        if not name:
            InputWidgetFactory.set_error_state(self.code_edit, True)
            return

        InputWidgetFactory.set_error_state(self.code_edit, False)
        self.region_dropdown.blockSignals(True)
        self.region_dropdown.setCurrentText(name)
        self.region_dropdown.blockSignals(False)

    def _on_region_finished(self) -> None:
        """Обработчик завершения ввода/выбора названия региона."""
        text = self.region_dropdown.currentText().strip()
        found = Regions.find_region(text)

        if found is None:
            self.region_dropdown.set_error_state(True)
            return

        code, name = found
        self.region_dropdown.set_error_state(False)

        self.code_edit.blockSignals(True)
        self.code_edit.setText(code)
        self.code_edit.blockSignals(False)

        self.region_dropdown.blockSignals(True)
        self.region_dropdown.setCurrentText(name)
        self.region_dropdown.blockSignals(False)

    def _validate_index(self) -> None:
        """Валидация индекса по завершении ввода."""
        v = self.index_edit.text().strip()
        ok = v.isdigit() and len(v) == 6
        InputWidgetFactory.set_error_state(self.index_edit, not ok)

    def _on_open_regions_file(self) -> None:
        """Открывает файл справочника регионов."""
        path = Regions.file_path()
        try:
            os.startfile(str(path))
        except Exception:
            MessageDialog.warning(self, text="Не удалось открыть файл")

    def _collect_result(self) -> AddressModel:
        """Собирает модель адреса из полей."""
        self._model.index = self.index_edit.text().strip()
        self._model.region_code = self.code_edit.text().strip()
        self._model.region_name = self.region_dropdown.currentText().strip()
        self._model.city = self.city_edit.text().strip()
        self._model.settlement = self.settlement_edit.text().strip()
        self._model.street = self.street_edit.text().strip()
        self._model.house = self.house_edit.text().strip()
        self._model.building = self.building_edit.text().strip()
        return self._model

    def _validate(self) -> bool:
        """Подсвечивает невалидные поля, но не блокирует сохранение."""
        tmp = AddressModel(
            index=self.index_edit.text().strip(),
            region_code=self.code_edit.text().strip(),
            region_name=self.region_dropdown.currentText().strip(),
            city=self.city_edit.text().strip(),
            settlement=self.settlement_edit.text().strip(),
            street=self.street_edit.text().strip(),
            house=self.house_edit.text().strip(),
            building=self.building_edit.text().strip(),
        )

        errors = CPValid.validate_address(tmp)

        InputWidgetFactory.set_error_state(self.index_edit, "index" in errors)
        InputWidgetFactory.set_error_state(self.code_edit, "region_code" in errors)
        self.region_dropdown.set_error_state("region_name" in errors)

        # Всегда разрешаем закрыть диалог и сохранить то, что есть
        return True
