"""
Общие диалоги приложения.

Содержит четыре класса:
    StringListDialog          — редактирование списка строк.
    AveragePriceInputDialog   — ввод средней цены продавца.
    PricesEditWindow          — массовое редактирование цен.
    SaleDuplicatePickerDialog — выбор файла-получателя при дубле КИЗа.

Роль в программе:
    Диалоги, используемые несколькими окнами. Все четыре переведены
    на BaseEditDialog: каркас — в базовом классе, содержимое —
    в _build_content. Мастер разрешения неизвестных (BrandsUnknownDialog,
    BrandPickerDialog) удалён — заменён на UnknownResolverDialog и
    ObjectPickerDialog в ui/windows/unknown_resolver_dialog.py.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    LabelFactory, InputWidgetFactory,
    ListWidgetFactory, ButtonFactory, LayoutFactory,
)
from ui.widgets.editable_list_widget import EditableListWidget
from ui.styles import ColorCalculator, WindowStyle
from utils.parsers import NumberParser
from ui.base.base_edit_dialog import BaseEditDialog


class StringListDialog(BaseEditDialog):
    """Диалог редактирования списка строк.

    Назначение:
        Показывает EditableListWidget и кнопку «Готово». По нажатию
        сохраняет изменения в переданный снаружи список (мутация
        in-place — публичный контракт сохранён).

    Роль в программе:
        Открывается из SellersWindow по кнопке «Ключи» через show().
        Наследник BaseEditDialog: каркас — из базового класса.
        При seller is not None дополнительно показывает приоритет
        продавца (combo 1/2/3) и сохраняет его в модель.
    """

    LOGGER_SOURCE = "StringListDialog.shared_dialogs"
    LOGGER_DOMAIN = "sellers_brands"

    def __init__(self, parent=None, title="Редактирование",
                 strings=None, seller=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок диалога.
            strings — список строк для редактирования. Мутируется
                      in-place при сохранении.
            seller — Seller или None. Если задан, диалог показывает
                     блок приоритета (label + combo) и сохраняет
                     выбранный приоритет в seller.priority.
            log_manager_v2 — LogManagerV2 или None. Прокидывается
                     в BaseEditDialog; без него self.logger = None.

        Роль: сохраняет ссылки до super(), чтобы _build_content
              мог их использовать. Фон диалога — производный от
              родителя.
        """
        self.strings = strings if strings is not None else []
        self._title = title
        self._seller = seller

        # Фон диалога — производный от родителя по формуле пользователя
        # (r//2, g//1.5, b//1.3). Fallback (40, 30, 50) — если у родителя
        # нет bg_color. Заменяет прежний хардкод (40, 30, 50, 0.95).
        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r // 2,
            g_fn=lambda g: int(g // 1.5),
            b_fn=lambda b: int(b // 1.3),
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title=title,
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=True,
            modal=False,
            center=True,
            width=400,
            height=350,
            log_manager_v2=log_manager_v2,
        )

        if self.logger:
            seller_name = self._seller.name if self._seller else "—"
            self.logger.debug(
                f"StringListDialog.__init__: seller={seller_name}, "
                f"строк={len(self.strings)}"
            )

    def _build_content(self, layout) -> None:
        """Строит содержимое диалога.

        Вход: layout — QVBoxLayout из BaseEditDialog.

        Роль: заголовок; при seller — второй заголовок и блок
              приоритета; список ключей; кнопка «Готово».
              Порядок виджетов строго сверху вниз.
        """
        layout.addWidget(LabelFactory.create_header_label(self, self._title))

        if self._seller is not None:
            layout.addWidget(
                LabelFactory.create_header_label(
                    self, "Ключи для распознавания",
                )
            )

        self.list_widget = EditableListWidget(
            self, initial_items=self.strings,
        )
        layout.addWidget(self.list_widget)

        if self._seller is not None:
            layout.addWidget(
                LabelFactory.create_label(
                    self, "Приоритет",
                    bg_color=(0, 0, 0, 0), text_color=None,
                )
            )
            element_bg = ColorCalculator.derive(
                self.bg_color,
                r_fn=lambda r: r - r // 5,
                g_fn=lambda g: g - g // 5,
                b_fn=lambda b: b - b // 5,
                alpha=1.0,
            )
            # current_index = priority - 1 (1 → 0, 2 → 1, 3 → 2).
            self._combo = InputWidgetFactory.create_combo_box(
                self,
                items=["Низкий", "Средний", "Высокий"],
                current_index=self._seller.priority - 1,
                bg_color=element_bg,
            )
            self._combo.currentIndexChanged.connect(
                self._on_priority_changed,
            )
            layout.addWidget(self._combo)

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        # Кнопка вызывает accept: базовый класс вызовет
        # _validate → _collect_result → super().accept().
        ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    def _on_priority_changed(self, index: int) -> None:
        """Debug-лог смены приоритета.

        Вход: index — новый индекс combo (0..2).

        Роль: модель не трогаем — она пишется только при
              _collect_result.
        """
        if self.logger:
            self.logger.debug(
                f"Выбран приоритет: {index + 1}"
            )

    def _collect_result(self):
        """Сохраняет изменения в self.strings (мутация in-place).

        Выход: None.

        Роль:
            Список строк пишется всегда. Если задан seller и combo
            создан — обновляется seller.priority. Проверка
            hasattr(self, "_combo") защищает ветку seller is None
            и случай отсутствия combo. Запись в модель — только
            через accept() (кнопка «Готово»).
        """
        self.strings[:] = self.list_widget.get_items()
        if self._seller is not None and hasattr(self, "_combo"):
            new_priority = self._combo.currentIndex() + 1
            self._seller.priority = new_priority
            if self.logger:
                self.logger.debug(
                    f"Сохранение: seller={self._seller.name}, "
                    f"priority={new_priority}, "
                    f"строк={len(self.strings)}"
                )
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
        Открывается из SellsFBSWindow по кнопке «Цены». Работает
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



class SaleDuplicatePickerDialog(BaseEditDialog):
    """Диалог выбора файла-получателя КИЗа при дубле в продажах.

    Назначение:
        Показать, в каких файлах продаж встречается один и тот же
        КИЗ, и дать пользователю выбрать, в каком файле оставить
        КИЗ, а из остальных удалить.

    Роль в программе:
        Открывается из SellsFBSWindow по callback от
        GenerateSalesService. Возвращает Path выбранного файла
        или None (тогда сервис использует file_paths[0]).
    """

    LOGGER_SOURCE = "SaleDuplicatePickerDialog.shared_dialogs"
    LOGGER_DOMAIN = "chz_mp"

    def __init__(self, parent=None, kiz: str = "",
                 file_to_receiver: dict = None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (SellsFBSWindow).
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
        """Строит заголовок и кнопки-получатели в скролл-контейнере.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: заголовок — в основном layout диалога. Кнопки лежат
              в content_layout скролл-контейнера: при 2–3 файлах
              скроллбар не появляется, при 4+ — вертикальный
              скролл. Подпись кнопки — имя получателя, цвет —
              производный от self.bg_color через ColorCalculator.
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

        scroll, _, content_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=4, bg_color=self.bg_color,
            )
        )

        layout.addWidget(scroll)

        for path, receiver_name in self._file_to_receiver.items():
            btn = ButtonFactory.create_button(
                self, receiver_name, btn_color,
                padding="6px 12px",
            )
            btn.clicked.connect(
                lambda checked=False, p=path: self._on_pick(p)
            )
            self._buttons.append(btn)
            content_layout.addWidget(btn)

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