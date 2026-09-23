"""
Общие диалоги приложения.

Содержит три класса:
    StringListDialog          — редактирование списка строк.
    AveragePriceInputDialog   — ввод средней цены продавца.
    PricesEditWindow          — массовое редактирование цен.

Роль в программе:
    Диалоги, используемые несколькими окнами. Все три переведены
    на BaseEditDialog: каркас — в базовом классе, содержимое —
    в _build_content.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt

from ui.factories.factories import (
    LabelFactory, InputWidgetFactory,
    ListWidgetFactory, ButtonFactory, LayoutFactory,
)
from ui.widgets.editable_list_widget import EditableListWidget
from utils.validation import ValidationNumb
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
            text_color="#d4d4d4",
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
        if not ValidationNumb.is_number(text):
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
        return ValidationNumb.to_int(self._input_edit.text().strip())

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
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
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
            if text and ValidationNumb.is_number(text):
                updated_prices[seller_name] = ValidationNumb.to_int(text)
        self._main_config.set("seller_prices", updated_prices)
        return None