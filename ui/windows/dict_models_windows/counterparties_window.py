"""
Окно справочника контрагентов.

Содержит CounterpartiesWindow — базовое окно справочника юрлиц.
Каркас окна, скролл, строки, удаление, сохранение по закрытию
и вычисление цветов — здесь. SellersWindow наследует это окно.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout

from models.models import Counterparty
from services.counterparties_service import CounterpartiesService
from utils.text_utils import TextUtils
from ui.factories.factories import (
    LabelFactory, LayoutFactory, ListWidgetFactory, ButtonFactory,
    InputWidgetFactory,
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.styles import ColorCalculator, WindowStyle, WidgetStyle
from ui.windows.dict_models_windows.counterparty_dialogs import (
    CounterpartyNameDialog, CounterpartyCompanyDialog,
    CounterpartyRequisitesDialog,
)
from ui.windows.shared_dialogs import StringListDialog

class CounterpartiesWindow(QMainWindow):
    """Базовое окно справочника контрагентов.

    Назначение:
        Список контрагентов: удаление, свободное имя, юр. наименование,
        «Компания», «Реквизиты», «Доп».

    Роль в программе:
        Уровень 1, fill_parent=True. Открывается из MainWindow.
        Данные — CounterpartiesService, ключ "counterparties".
        SellersWindow наследует это окно и добавляет «Бренды»,
        приоритет ключей и НДС.
    """

    LOGGER_SOURCE = "CounterpartiesWindow.dict_models_windows"
    LOGGER_DOMAIN = "counterparties"
    WINDOW_TITLE = "Контрагенты"
    DEFAULT_WIDTH = 580
    DEFAULT_HEIGHT = 450
    ROW_BG_DIVIDERS = (1, 1, 1)
    WINDOW_NAME = "counterparties"
    objectName = "counterparties_window"

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None.
        """
        super().__init__(parent)
        self.main_window = parent
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )

        self.service_window = self
        self.service = None
        self.items = self._load_items()
        self.bg_color = self._resolve_bg_color()
        self.setObjectName(self.objectName)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=self.WINDOW_TITLE,
            bg_color=self.bg_color,
            close_button=True,
            draggable=False,
            close_on_click_outside=False,
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=self.DEFAULT_WIDTH,
            default_height=self.DEFAULT_HEIGHT,
        )

        if parent is not None and hasattr(parent, "window_manager"):
            parent.window_manager.register_window(
                self, parent=parent, fill_parent=True, modal=False,
            )

        content_layout.addWidget(
            LabelFactory.create_header_label(self, self.WINDOW_TITLE)
        )

        scroll, self.items_widget, self.items_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        content_layout.addWidget(scroll)

        add_btn = ButtonFactory.create_add_button(self, self._on_add)
        LayoutFactory.add_centered_widget(content_layout, add_btn)

        for item in self.items:
            self._add_row(item)

    # ---------- Сервис и данные ----------

    def _create_service(self):
        """Создаёт CounterpartiesService."""
        return CounterpartiesService(
            self.main_window.main_config,
            self.log_manager_v2,
        )

    def _load_items(self) -> list:
        """Загружает контрагентов из сервиса."""
        if self.service is None:
            self.service = self._create_service()
        counterparties = self.service.get_counterparties_objects()
        if not isinstance(counterparties, list):
            if self.logger is not None:
                self.logger.critical(
                    "CounterpartiesWindow: get_counterparties_objects "
                    "вернул не список",
                    can_influence=False,
                )
            counterparties = []
        return counterparties

    def _save_items(self) -> None:
        """Сохраняет контрагентов через сервис."""
        if self.service is None:
            self.service = self._create_service()
        if not isinstance(self.items, list):
            if self.logger is not None:
                self.logger.critical(
                    "CounterpartiesWindow: self.items не список, "
                    "сохранение отменено",
                    can_influence=False,
                )
            return
        self.service.set_counterparties_objects(self.items)

    def _create_new_item(self) -> Counterparty:
        """Создаёт пустого контрагента."""
        return Counterparty()

    def _on_add(self) -> None:
        """Добавляет контрагента и перестраивает список."""
        item = self._create_new_item()
        self.items.append(item)
        self._save_items()
        self._rebuild_rows()

    # ---------- Цвета ----------

    def _resolve_bg_color(self):
        """Вычисляет фон окна от MainWindow и BG_MODIFIER."""
        parent = self.main_window
        if parent is None:
            parent_bg = (0, 0, 0, 0)
        else:
            parent_bg = WindowStyle.resolve_parent_bg(
                parent, getattr(parent, "bg_color", (0, 0, 0, 0)),
            )
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: int(r * 0.9),
            g_fn=lambda g: int(g * 0.4),
            b_fn=lambda b: int(b * 0.9),
        )
        return self.bg_color

        dr, dg, db = modifier[:3]
        return ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: ColorCalculator.clamp(r + dr),
            g_fn=lambda g: ColorCalculator.clamp(g + dg),
            b_fn=lambda b: ColorCalculator.clamp(b + db),
        )

    def _row_bg_color(self):
        """Цвет строки от вычисленного bg_color окна."""
        r_div, g_div, b_div = self.ROW_BG_DIVIDERS
        return ColorCalculator.element_bg_for(
            self.bg_color,
            r_div=r_div,
            g_div=g_div,
            b_div=b_div,
            divisor=10,
        )

    def _button_bg_color(self, row_bg):
        """Цвет кнопок строки от фона строки."""
        return ColorCalculator.element_bg_for(row_bg)

    # ---------- Построение строк ----------

    def _add_row(self, item: Counterparty) -> None:
        """Добавляет строку контрагента."""
        row = QWidget()
        row.setObjectName("counterparty_row")

        row_bg = self._row_bg_color()
        name_bg = self._button_bg_color(row_bg)
        button_bg = self._button_bg_color(name_bg)
        WidgetStyle.apply_panel(row, (0, 0, 0, 0), border_radius=6)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.addStretch()

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._on_delete(row, item),
            size=(25, 25),
        )
        layout.addWidget(del_btn)

        layout.addWidget(
            self._create_name_widget(self, item, name_bg)
        )
        layout.addWidget(
            self._create_legal_name_widget(item, button_bg)
        )

        company_btn = ButtonFactory.create_button(
            self, "Компания", button_bg, fixed_size=(90, 30),
        )
        company_btn.clicked.connect(lambda: self._edit_company(item))
        layout.addWidget(company_btn)

        requisites_btn = ButtonFactory.create_button(
            self, "Реквизиты", button_bg, fixed_size=(90, 30),
        )
        requisites_btn.clicked.connect(
            lambda: self._edit_requisites(item)
        )
        layout.addWidget(requisites_btn)

        self._add_extra_buttons(layout, item, button_bg)
        layout.addStretch()

        self.items_layout.addWidget(row)

    def _add_extra_buttons(self, layout, item: Counterparty,
                           button_bg) -> None:
        """Добавляет кнопку «Доп» для ключей без приоритета."""
        extra_btn = ButtonFactory.create_button(
            self, "Доп", button_bg, fixed_size=(70, 30),
        )
        extra_btn.clicked.connect(lambda: self._edit_keys(item))
        layout.addWidget(extra_btn)

    # ---------- Обработчики ----------

    def _on_delete(self, row, item: Counterparty) -> None:
        """Удаляет контрагента, строку и сохраняет."""
        self._remove_item(row, item)
        self._save_items()

    def _edit_company(self, item: Counterparty) -> None:
        """Открывает диалог компании."""
        dialog = CounterpartyCompanyDialog(
            self, item, self.log_manager_v2,
        )
        dialog.accepted.connect(self._save_items)
        dialog.show()

    def _edit_requisites(self, item: Counterparty) -> None:
        """Открывает диалог реквизитов."""
        dialog = CounterpartyRequisitesDialog(
            self, item, self.log_manager_v2,
        )
        dialog.accepted.connect(self._save_items)
        dialog.show()

    def _edit_keys(self, item: Counterparty) -> None:
        """Открывает редактор ключей без приоритета."""
        dialog = StringListDialog(
            self,
            title=f"Дополнительно — {self._display_name(item)}",
            strings=item.keys,
            seller=None,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.accepted.connect(self._save_items)
        dialog.show()

    # ---------- Свободное имя ----------

    def _display_name(self, item: Counterparty) -> str:
        """Возвращает свободное имя или краткое юр. наименование."""
        if item.name.strip():
            return item.name
        return TextUtils.format_short_legal_name(
            item.company, item.org_type,
        )

    def _create_name_widget(self, parent, item: Counterparty, row_bg):
        """Создаёт кнопку свободного имени с inline-редактированием."""
        name_btn = ButtonFactory.create_button(
            parent, self._display_name(item), row_bg,
            fixed_size=(150, 30),
        )
        name_btn.clicked.connect(
            lambda: self._start_name_edit(item, name_btn)
        )
        return name_btn

    def _start_name_edit(self, item: Counterparty, name_btn) -> None:
        """Заменяет кнопку имени на поле ввода."""
        row = name_btn.parentWidget()
        layout = row.layout()
        edit = InputWidgetFactory.create_default_line_edit(
            self, text=item.name,
        )
        edit.setFixedSize(name_btn.size())
        layout.replaceWidget(name_btn, edit)
        name_btn.deleteLater()
        edit.setFocus()

        finished = False

        def finish() -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            item.name = edit.text().strip()
            self._save_items()
            self._rebuild_rows()

        edit.editingFinished.connect(finish)

    # ---------- Юридическое наименование ----------

    def _create_legal_name_widget(self, item: Counterparty,
                                  button_bg):
        """Создаёт кликабельный лейбл юр. наименования."""
        short_name = TextUtils.format_short_legal_name(
            item.company, item.org_type,
        )
        legal_btn = ButtonFactory.create_button(
            self, short_name, button_bg, fixed_size=(150, 30),
        )
        legal_btn.clicked.connect(lambda: self._edit_name(item))
        return legal_btn

    def _edit_name(self, item: Counterparty) -> None:
        """Открывает диалог юр. наименования."""
        dialog = CounterpartyNameDialog(
            self, item, self.log_manager_v2,
        )
        dialog.accepted.connect(
            lambda: self._on_name_accepted(item, dialog)
        )
        dialog.show()

    def _on_name_accepted(self, item, dialog) -> None:
        """Сохраняет изменения и перестраивает список."""
        self._save_items()
        self._rebuild_rows()

    # ---------- Обновление / сохранение ----------

    def _remove_item(self, row_widget, item) -> None:
        """Удаляет объект из списка и строку из layout."""
        if item in self.items:
            self.items.remove(item)
        self.items_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def _rebuild_rows(self) -> None:
        """Очищает и заново строит список строк."""
        while self.items_layout.count():
            layout_item = self.items_layout.takeAt(0)
            if layout_item.widget():
                layout_item.widget().deleteLater()
        for item in self.items:
            self._add_row(item)

    def refresh_ui(self) -> None:
        """Перестраивает UI с текущим составом self.items."""
        self._rebuild_rows()

    def save_and_close(self) -> None:
        """Сохраняет данные и закрывает окно."""
        try:
            self._save_items()
        except Exception as e:
            if self.logger is not None:
                self.logger.critical(
                    f"Ошибка сохранения: {e}",
                    can_influence=False,
                )
        finally:
            self.close()