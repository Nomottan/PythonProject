"""
Общие диалоги приложения.

Содержит пять классов:
    StringListDialog          — редактирование списка строк.
    AveragePriceInputDialog   — ввод средней цены продавца.
    PricesEditWindow          — массовое редактирование цен.
    BrandsUnknownDialog       — мастер разрешения неизвестных брендов.
    BrandPickerDialog         — выбор существующего бренда из списка.

Роль в программе:
    Диалоги, используемые несколькими окнами. Все пять переведены
    на BaseEditDialog: каркас — в базовом классе, содержимое —
    в _build_content.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    LabelFactory, InputWidgetFactory,
    ListWidgetFactory, ButtonFactory, LayoutFactory,
)
from ui.widgets.editable_list_widget import EditableListWidget
from ui.styles import ColorCalculator, WindowStyle
from utils.parsers import NumberParser
from utils.text_utils import TextUtils
from models.models import Brand
from ui.base.base_edit_dialog import BaseEditDialog
from ui.windows.message_dialog import NotificationDialog
from ui.windows.brands_window import BrandEditDialog


class StringListDialog(BaseEditDialog):
    """Диалог редактирования списка строк.

    Назначение:
        Показывает EditableListWidget и кнопку «Готово». По нажатию
        сохраняет изменения в переданный снаружи список (мутация
        in-place — публичный контракт сохранён).

    Роль в программе:
        Открывается из SellersWindow по кнопке «Ключи» через show().
        Наследник BaseEditDialog: каркас — из базового класса.
    """

    def __init__(self, parent=None, title="Редактирование", strings=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок диалога.
            strings — список строк для редактирования. Мутируется
                      in-place при сохранении.

        Роль: сохраняет ссылку на список и заголовок до super(),
              чтобы _build_content мог их использовать.
        """
        self.strings = strings if strings is not None else []
        # Сохраняем заголовок — он используется в _build_content
        # для лейбла.
        self._title = title

        super().__init__(
            parent=parent,
            title=title,
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            ok_cancel=False,      # своя кнопка «Готово» в _build_content
            draggable=True,
            close_on_click_outside=True,
            # modal=False: диалог открывается через show() без exec(),
            # как и раньше.
            modal=False,
            center=True,
            width=400,
            height=350,
        )

    def _build_content(self, layout) -> None:
        """Строит содержимое: заголовок, список, кнопка «Готово».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        layout.addWidget(LabelFactory.create_header_label(self, self._title))

        self.list_widget = EditableListWidget(
            self, initial_items=self.strings,
        )
        layout.addWidget(self.list_widget)

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        # Кнопка вызывает accept: базовый класс вызовет
        # _validate → _collect_result → super().accept().
        ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _collect_result(self):
        """Сохраняет изменения в self.strings (мутация in-place).

        Выход: None.
        Роль: использует срез [:] — чтобы не подменять ссылку,
              которую держит вызывающий код.
        """
        self.strings[:] = self.list_widget.get_items()
        return None


class AveragePriceInputDialog(BaseEditDialog):
    """Модальное окно для ввода средней цены для продавца.

    Назначение:
        Запрашивает у пользователя среднюю цену. Используется как
        fallback, если у продавца нет сохранённой цены.

    Роль в программе:
        Открывается из FinalizePricesService при отсутствии цены.
        Наследник BaseEditDialog: контент — label + input,
        кнопка «Сохранить», валидация в _validate.
    """

    def __init__(self, parent=None, seller_name=""):
        """Конструктор.

        Вход:
            parent — родитель.
            seller_name — имя продавца (для текста подсказки).
        """
        self._seller_name = seller_name
        super().__init__(
            parent=parent,
            title="Ввод средней цены",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            ok_cancel=False,
            draggable=False,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=400,
            height=200,
        )

    def _build_content(self, layout) -> None:
        """Label-подсказка, поле ввода и кнопка «Сохранить».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        self._label = LabelFactory.create_label(
            self,
            text=(
                f"Не установлена средняя цена для продавца "
                f"{self._seller_name}\nУкажите цену"
            ),
            bg_color=(0, 0, 0, 0),
            text_color=None,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        layout.addWidget(self._label)

        self._input_edit = InputWidgetFactory.create_default_line_edit(
            self, placeholder="Введите число",
        )
        layout.addWidget(self._input_edit)

        save_btn = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
        )
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)

    def _validate(self) -> bool:
        """Проверяет, что введено число.

        Выход: True — можно закрывать; False — остаться.
        Роль: при невалидном вводе дописывает ошибку в label,
              очищает поле и ставит фокус. Кнопка «Сохранить»
              вызывает accept → _validate.
        """
        text = self._input_edit.text().strip()
        if NumberParser.to_float(text) is None:
            current = self._label.text()
            if "Данные не подходят" not in current:
                self._label.setText(
                    current + "\nДанные не подходят. Введите число"
                )
            self._input_edit.clear()
            self._input_edit.setFocus()
            return False
        return True

    def _collect_result(self):
        """Возвращает введённую цену как int."""
        return NumberParser.to_int(self._input_edit.text().strip())

    def get_price(self):
        """Возвращает введённую цену (после exec() == Accepted)."""
        return self.get_result()


class PricesEditWindow(BaseEditDialog):
    """Окно для просмотра и редактирования сохранённых цен продавцов.

    Назначение:
        Список строк «имя продавца — поле цены». Кнопка «Сохранить»
        пишет цены в MainConfig по ключу "seller_prices".

    Роль в программе:
        Открывается из ChzMPWindow по кнопке «Цены». Работает
        через sellers_brands_service (продавцы) и main_config
        (цены).
    """

    def __init__(self, parent, sellers_brands_service, main_config):
        """Конструктор.

        Вход:
            parent — родитель.
            sellers_brands_service — SellersBrandsService: список продавцов.
            main_config — MainConfig: ключ "seller_prices".
        """
        self._sellers_brands = sellers_brands_service
        self._main_config = main_config
        self.sellers = sellers_brands_service.get_sellers_objects()
        self.saved_prices = main_config.get("seller_prices", {})
        # Ссылки на поля ввода цен — заполняются в _build_content.
        self.price_edits = {}
        # Фон — сохраняем до super(): используется в _build_content.
        self.bg_color = (40, 30, 50, 0.95)

        super().__init__(
            parent=parent,
            title="Цены продавцов",
            bg_color=self.bg_color,
            close_button=True,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            width=500,
            height=500,
        )

    def _build_content(self, layout) -> None:
        """Строит список строк «продавец — поле цены».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Цены продавцов",
        ))

        scroll, _, content_layout2 = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll)

        for seller in self.sellers:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(4)

            name_label = LabelFactory.create_label(
                self, seller.name,
                bg_color=(0, 0, 0, 0), text_color=None,
                alignment=Qt.AlignLeft | Qt.AlignVCenter,
            )
            row_layout.addWidget(name_label, stretch=1)

            price_edit = InputWidgetFactory.create_default_line_edit(
                self,
                text=str(self.saved_prices.get(seller.name, "")),
            )
            row_layout.addWidget(price_edit, stretch=1)

            self.price_edits[seller.name] = price_edit
            content_layout2.addWidget(row_widget)

        save_btn = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
        )
        save_btn.clicked.connect(self.accept)
        layout.addWidget(save_btn)

    def _collect_result(self):
        """Сохраняет отредактированные цены в MainConfig.

        Выход: None.
        Роль: собирает значения из полей. Невалидные строки
              пропускаются — как и раньше.
        """
        updated_prices = {}
        for seller_name, edit in self.price_edits.items():
            text = edit.text().strip()
            if text and NumberParser.to_float(text) is not None:
                updated_prices[seller_name] = NumberParser.to_int(text)
        self._main_config.set("seller_prices", updated_prices)
        return None

class BrandsUnknownDialog(BaseEditDialog):
    """Мастер разрешения неизвестных брендов.

    Назначение:
        Для каждого неизвестного бренда пользователь выбирает:
        привязать к существующему (BrandPickerDialog) или создать
        новый (BrandEditDialog). Мастер жёсткий — Esc и клик вне
        окна не закрывают, обход строго последовательный.

    Роль в программе:
        Открывается из ChzMPWindow по callback от
        FilterPreFinalService. Возвращает агрегаты для лога.
    """

    LOGGER_SOURCE = "BrandsUnknownDialog.shared_dialogs"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent=None, brands_unknown: dict = None,
                 sellers_brands_service=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (обычно ChzMPWindow).
            brands_unknown — {норм_ключ: [сырая_1, ...]}.
            sellers_brands_service — SellersBrandsService. Нужен для
                add_key_to_brand / create_brand / get_brands_objects /
                get_sellers_with_brands.
            log_manager_v2 — LogManagerV2 или None.

        Роль: сохраняет данные, читает продавцов один раз, строит
              каркас. Если неизвестных брендов нет — сразу accept().
        """
        self._brands_unknown: dict = brands_unknown or {}
        self._keys_list: list = list(self._brands_unknown.keys())
        self._current_index: int = 0
        self._stats: dict = {
            "total": len(self._keys_list),
            "resolved": 0,
            "skipped": 0,
        }
        self._service = sellers_brands_service
        self._main_window = (
            parent.main_window
            if parent is not None and hasattr(parent, "main_window")
            else None
        )
        # Продавцы читаются один раз — не дёргать сервис на каждой
        # итерации (пользователь правит данные параллельно, но в
        # рамках одного мастера список фиксирован).
        self._sellers = (
            self._service.get_sellers_with_brands() if self._service
            else []
        )

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 5,
            g_fn=lambda g: g - 15,
            b_fn=lambda b: b + 20,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Неизвестные бренды",
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            modal=True,
            draggable=True,
            close_on_click_outside=False,
            center=True,
            width=500,
            height=320,
            log_manager_v2=log_manager_v2,
            on_close=None,
        )

        # Пустой вход — мастер нечего показывать.
        if self._stats["total"] == 0:
            self.accept()

    def reject(self) -> None:
        """Запрещает закрытие мастера через Esc / программный reject.

        Вход: нет.
        Выход: нет.
        Роль: мастер обходится только accept() после прохода всех
              брендов. Закрытие пользователем — через выбор
              «Существующий» / «Новый» на каждой итерации.
        """
        pass

    def _build_content(self, layout) -> None:
        """Строит счётчик, лейбл сырого бренда и две кнопки.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: при пустом brands_unknown ничего не строим —
              __init__ вызовет accept() сразу после super().__init__.
        """
        if self._stats["total"] == 0:
            return

        self._counter_label = LabelFactory.create_header_label(
            self,
            f"Нераспознанный бренд: "
            f"{self._current_index + 1} из {self._stats['total']}",
        )
        layout.addWidget(self._counter_label)

        raw_first = self._brands_unknown[
            self._keys_list[self._current_index]
        ][0]
        self._brand_label = LabelFactory.create_label(
            self, raw_first,
            bg_color=(0, 0, 0, 0),
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        layout.addWidget(self._brand_label)

        btns_layout = QHBoxLayout()
        self._btn_existing = ButtonFactory.create_button(
            self, "Существующий", (100, 80, 120, 0.7),
            padding="6px 12px",
        )
        self._btn_existing.clicked.connect(self._on_existing)
        btns_layout.addWidget(self._btn_existing)

        self._btn_new = ButtonFactory.create_button(
            self, "Новый", (70, 120, 90, 0.8),
            padding="6px 12px",
        )
        self._btn_new.clicked.connect(self._on_new)
        btns_layout.addWidget(self._btn_new)

        layout.addLayout(btns_layout)

    def _on_existing(self) -> None:
        """Открывает BrandPickerDialog, привязывает сырой ключ.

        Вход: нет.
        Выход: нет.

        Роль: список брендов читается свежим перед каждым открытием.
              Пикер открывается модально относительно главного окна
              (self._main_window), если оно доступно, — иначе
              относительно самого мастера. Отмена выбора (selected
              is None) — возврат на текущий шаг без изменений:
              индекс не двигается, обе кнопки остаются активны.
              Успешный add_key_to_brand — _resolve, вперёд. Ошибка
              сервиса — уведомление, остаёмся на текущем бренде.
        """
        brands = self._service.get_brands_objects()
        dialog = BrandPickerDialog(
            parent=self._main_window if self._main_window is not None else self,
            brands=brands,
            bg_color=self.bg_color,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        selected = dialog.get_selected()
        if selected is None:
            return

        raw = self._brands_unknown[
            self._keys_list[self._current_index]
        ][0]
        ok = self._service.add_key_to_brand(selected.name, raw)
        if ok:
            self._resolve()
            return

        NotificationDialog.notify(
            self,
            f"Не удалось привязать ключ к бренду '{selected.name}'",
            title_text="Ошибка",
            bg_color=self.bg_color,
        )

    def _on_new(self) -> None:
        """Открывает BrandEditDialog для создания нового бренда.

        Вход: нет.
        Выход: нет.

        Роль: стартовый Brand предзаполнен сырыми вариантами текущей
              группы — name = raw_variants[0], keys = list(raw_variants).
              Пользователь видит осмысленные данные и может их править.
              Отмена (was_deleted / пустое имя) — возврат на текущий
              шаг без изменений. Успешный create_brand — _resolve,
              вперёд. Ошибка сервиса — уведомление, остаёмся.
        """
        raw_variants = self._brands_unknown[
            self._keys_list[self._current_index]
        ]
        new_brand = Brand(name=raw_variants[0], keys=list(raw_variants))
        dialog = BrandEditDialog(
            parent=self,
            brand=new_brand,
            sellers=self._sellers,
            main_window=self._main_window,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()

        if dialog.was_deleted():
            return
        if (not new_brand.name
                or TextUtils.normalize(new_brand.name) == ""):
            return

        ok = self._service.create_brand(
            new_brand.name,
            new_brand.keys,
            new_brand.requires_saving,
        )
        if ok:
            self._resolve()
            return

        NotificationDialog.notify(
            self,
            f"Не удалось создать бренд '{new_brand.name}'",
            title_text="Ошибка",
            bg_color=self.bg_color,
        )

    def _resolve(self) -> None:
        """Считает текущий бренд разрешённым и переходит к следующему."""
        self._stats["resolved"] += 1
        self._advance()

    def _advance(self) -> None:
        """Переходит к следующему бренду или закрывает мастер.

        Вход: нет.
        Выход: нет.
        Роль: индекс +1. За пределами списка — accept(). Иначе
              обновляет счётчик и лейбл сырого бренда.
        """
        self._current_index += 1
        if self._current_index >= self._stats["total"]:
            self.accept()
            return

        self._counter_label.setText(
            f"Нераспознанный бренд: "
            f"{self._current_index + 1} из {self._stats['total']}"
        )
        raw_first = self._brands_unknown[
            self._keys_list[self._current_index]
        ][0]
        self._brand_label.setText(raw_first)

    def get_stats(self) -> dict:
        """Возвращает агрегаты обхода для лога.

        Выход: {"total", "resolved", "skipped"}.
        Роль: skipped всегда 0 — в текущем мастер-флоу пропуск
              бренда невозможен: отмена действия на любом шаге
              возвращает пользователя на тот же бренд, продвижение
              только через успешный resolve. Инвариант
              resolved + skipped == total не заявлен: если
              пользователь не завершил обход (не может — мастер
              жёсткий), resolved может быть меньше total.
        """
        return dict(self._stats)


class BrandPickerDialog(BaseEditDialog):
    """Выбор существующего бренда из списка с поиском.

    Назначение:
        Показать список Brand, отфильтровать по подстроке,
        вернуть выбранный элемент или None при отмене.

    Роль в программе:
        Открывается из BrandsUnknownDialog по кнопке «Существующий».
        Возвращает Brand через get_selected().
    """

    LOGGER_SOURCE = "BrandPickerDialog.shared_dialogs"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent=None, brands: list = None,
                 bg_color=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (BrandsUnknownDialog).
            brands — list[Brand] — список для отображения.
            bg_color — базовый цвет от родителя; None — берётся
                через WindowStyle.resolve_parent_bg(parent).
            log_manager_v2 — LogManagerV2 или None.

        Роль: сохраняет список, выставляет self._brand_selected = None,
              строит каркас.
        """
        self._brands: list = brands or []
        self._brand_selected = None

        if bg_color is None:
            bg_color = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            bg_color,
            r_fn=lambda r: r + 15,
            g_fn=lambda g: g - 5,
            b_fn=lambda b: b - 10,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Выбор бренда",
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            modal=True,
            draggable=True,
            close_on_click_outside=False,
            center=True,
            width=450,
            height=500,
            log_manager_v2=log_manager_v2,
            on_close=None,
        )

    def _build_content(self, layout) -> None:
        """Строит подсказку, поле поиска, список и две кнопки.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Выберите бренд",
        ))

        self._search_edit = InputWidgetFactory.create_default_line_edit(
            self, placeholder="Введите текст для фильтрации...",
        )
        self._search_edit.textChanged.connect(self._filter_list)
        layout.addWidget(self._search_edit)

        self._list_widget = ListWidgetFactory.create_list_widget(
            self,
            bg_color=self.bg_color,
            text_color=None,
            selection_mode=QListWidget.SelectionMode.SingleSelection,
        )
        self._list_widget.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        self._populate_list()
        layout.addWidget(self._list_widget)

        bottom = QHBoxLayout()

        back_btn = ButtonFactory.create_button(
            self, "Вернуться", (140, 70, 70, 0.8),
            fixed_size=(150, 35),
        )
        back_btn.clicked.connect(self._on_back)
        bottom.addWidget(back_btn)

        self._btn_confirm = ButtonFactory.create_button(
            self, "Подтвердить", (70, 160, 90, 0.8),
            fixed_size=(150, 35),
        )
        self._btn_confirm.clicked.connect(self._on_confirm)
        self._btn_confirm.setEnabled(False)
        bottom.addWidget(self._btn_confirm)

        layout.addLayout(bottom)

    def _populate_list(self) -> None:
        """Заполняет QListWidget брендами.

        Роль: brand сохраняется в item.data(Qt.UserRole) — чтобы
              _on_confirm отдал наружу объект Brand, а не строку.
        """
        for brand in self._brands:
            item = QListWidgetItem(brand.name)
            item.setData(Qt.ItemDataRole.UserRole, brand)
            self._list_widget.addItem(item)

    def _filter_list(self, text: str) -> None:
        """Скрывает строки, не содержащие text.

        Вход: text — текст из поля поиска.
        Роль: сравнение по нормализованной подстроке. Пустой текст
              (норм. строка) не скрывает ничего.
        """
        norm = TextUtils.normalize(text)
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item.setHidden(norm not in TextUtils.normalize(item.text()))

    def _on_selection_changed(self) -> None:
        """Активирует «Подтвердить» при наличии выбранной строки."""
        selected = self._list_widget.currentItem()
        self._btn_confirm.setEnabled(selected is not None)

    def _on_confirm(self) -> None:
        """Сохраняет выбранный Brand и закрывает диалог."""
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        self._brand_selected = selected.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_back(self) -> None:
        """Возвращает None и закрывает диалог (как «Вернуться»)."""
        self._brand_selected = None
        self.reject()

    def get_selected(self):
        """Возвращает выбранный Brand или None.

        Выход: Brand | None.
        Роль: вызывающий код после exec() получает результат без
              завязки на внутренние поля.
        """
        return self._brand_selected

class SaleDuplicatePickerDialog(BaseEditDialog):
    """Диалог выбора файла-получателя КИЗа при дубле в продажах.

    Назначение:
        Показать, в каких файлах продаж встречается один и тот же
        КИЗ, и дать пользователю выбрать, в каком файле оставить
        КИЗ, а из остальных удалить.

    Роль в программе:
        Открывается из ChzMPWindow по callback от
        GenerateSalesService. Возвращает Path выбранного файла
        или None (тогда сервис использует file_paths[0]).
    """

    LOGGER_SOURCE = "SaleDuplicatePickerDialog.shared_dialogs"
    LOGGER_DOMAIN = "chz_mp"

    def __init__(self, parent=None, kiz: str = "",
                 file_to_receiver: dict = None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (ChzMPWindow).
            kiz — 31-символьный КИЗ.
            file_to_receiver — dict[Path, str]: путь → имя получателя.
                Порядок итерации = порядок обнаружения КИЗа в файлах.
            log_manager_v2 — LogManagerV2 или None.

        Роль: сохраняет данные и строит каркас. Кнопки создаются
              в _build_content по одной на файл.
        """
        self._kiz = kiz
        self._file_to_receiver: dict = file_to_receiver or {}
        self._selected_path: Path | None = None
        self._buttons: list = []

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 5,
            g_fn=lambda g: g + 10,
            b_fn=lambda b: b - 15,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Выбор получателя",
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            modal=True,
            draggable=True,
            close_on_click_outside=False,
            center=True,
            width=450,
            height=250,
            log_manager_v2=log_manager_v2,
            on_close=None,
        )

    def reject(self) -> None:
        """Запрещает закрытие через Esc / программный reject.

        Вход: нет.
        Выход: нет.
        Роль: пользователь обязан выбрать получателя кликом
              по кнопке. При аварийном reject _selected_path
              остаётся None — сервис трактует это как fallback
              на file_paths[0].
        """
        pass

    def _build_content(self, layout) -> None:
        """Строит заголовок и кнопки по одной на каждый файл.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: подпись кнопки — имя получателя. Цвет — производный
              от self.bg_color через ColorCalculator.derive.
              Порядок кнопок совпадает с порядком file_to_receiver.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Найдено повторение, выбери на ком оставить:",
        ))

        btn_color = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: min(255, r + 30),
            g_fn=lambda g: min(255, g + 30),
            b_fn=lambda b: min(255, b + 30),
            alpha=0.9,
        )

        for path, receiver_name in self._file_to_receiver.items():
            btn = ButtonFactory.create_button(
                self, receiver_name, btn_color,
                padding="6px 12px",
            )
            btn.clicked.connect(
                lambda checked=False, p=path: self._on_pick(p)
            )
            self._buttons.append(btn)
            layout.addWidget(btn)

    def _on_pick(self, path) -> None:
        """Сохраняет выбранный путь и закрывает диалог.

        Вход: path — Path выбранного файла.
        Выход: нет.
        """
        self._selected_path = path
        self.accept()

    def get_selected_path(self):
        """Возвращает Path выбранного файла или None.

        Выход: Path | None.
        Роль: сервис при None использует fallback file_paths[0].
        """
        return self._selected_path