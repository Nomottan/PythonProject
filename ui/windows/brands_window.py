"""
Окно управления брендами.

Содержит два класса:
    BrandsWindow    — сетка брендов, редактирование, добавление, удаление.
    BrandEditDialog — диалог редактирования одного бренда: имя, ключи, продавцы.

Роль в программе:
    Открывается из MainWindow по кнопке «Бренды».
    Работает через parent.sellers_brands_service — модели Seller/Brand
    восстанавливаются с двусторонними связями, изменения сохраняются
    в config.json.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QGridLayout, QHBoxLayout, QVBoxLayout,
    QInputDialog, QDialog,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    LabelFactory, ListWidgetFactory, ButtonFactory, LayoutFactory,
    InputWidgetFactory,
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.widgets.editable_list_widget import EditableListWidget
from ui.windows.message_dialog import NotificationDialog, MessageDialog
from models.models import Seller, Brand


class BrandsWindow(QMainWindow):
    """Окно со сеткой брендов.

    Назначение:
        Показать список брендов в виде сетки кнопок 4 в ряд.
        Позволяет открыть диалог редактирования бренда, добавить новый
        бренд. При закрытии окна изменения сохраняются в config.json.

    Роль в программе:
        Открывается из MainWindow. Работает через
        parent.sellers_brands_service — прямых обращений к config
        здесь больше нет.
    """

    def __init__(self, parent=None):
        """Конструктор.

        Вход: parent — MainWindow.
        Роль: читает бренды и продавцов через сервис, строит сетку.
        """
        super().__init__(parent)
        self.main_window = parent
        self.bg_color = (30, 30, 30, 0.9)

        # REPLACE: читаем бренды и продавцов через SellersBrandsService.
        # Восстанавливаем связи Brand.sellers ↔ Seller.brands, чтобы
        # BrandEditDialog мог показывать связанные сущности.
        self.brands = parent.sellers_brands_service.get_brands_objects()
        for b in self.brands:
            b.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        _ = parent.sellers_brands_service.get_sellers_objects(brands_dict=brands_dict)

        # --- Каркас окна ---
        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Бренды",
            bg_color=self.bg_color,
            close_button=True,
            draggable=False,
            close_on_click_outside=False,
            center=True,
            on_close=self.save_and_close,
            return_content_layout=True,
            default_width=580,
            default_height=500,
        )

        content_layout.addWidget(LabelFactory.create_header_label(self, "Бренды"))

        # --- Сетка брендов ---
        self.brands_widget = QWidget()
        self.grid_layout = QGridLayout(self.brands_widget)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        self.grid_layout.setSpacing(5)

        scroll = ListWidgetFactory.create_scroll_area(
            self, widget=self.brands_widget,
            widget_resizable=True, bg_color=self.bg_color,
        )
        content_layout.addWidget(scroll)

        self._refresh_grid()

        # --- Кнопка добавления ---
        add_btn = ButtonFactory.create_add_button(self, self._add_new_brand)
        LayoutFactory.add_centered_widget(content_layout, add_btn)

    # ---------- Отрисовка ----------

    def _refresh_grid(self) -> None:
        """Перерисовывает сетку брендов.

        Роль: очищает grid_layout и заново раскладывает кнопки
              отсортированные по имени. Вызывается при старте и после
              закрытия BrandEditDialog — чтобы отразить переименования.
        """
        # Очистка.
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        columns = 4
        sorted_brands = sorted(self.brands, key=lambda b: b.name.lower())

        for i, brand in enumerate(sorted_brands):
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)

            btn = ButtonFactory.create_button(
                self, brand.name, (30, 50, 80, 0.8),
                fixed_size=(130, 30),
                alignment='left',
            )
            btn.clicked.connect(
                lambda checked, b=brand: self._on_brand_click(b)
            )
            container_layout.addWidget(btn)

            self.grid_layout.addWidget(container, i // columns, i % columns)

    # ---------- Обработчики ----------

    def _on_brand_click(self, brand: Brand) -> None:
        """Открывает диалог редактирования бренда.

        Вход: brand — Brand, который редактируем.
        Роль: подтягивает связанных продавцов через сервис,
              открывает BrandEditDialog. После его закрытия —
              перерисовывает сетку (имя могло измениться).
        """
        brand.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        sellers = self.main_window.sellers_brands_service.get_sellers_objects(
            brands_dict=brands_dict,
        )
        dialog = BrandEditDialog(
            self, brand, sellers, main_window=self.main_window,
        )
        # После закрытия диалога — обновить сетку.
        original_close = dialog.closeEvent

        def new_close(event):
            original_close(event)
            self._refresh_grid()

        dialog.closeEvent = new_close
        dialog.show()

    def _add_new_brand(self) -> None:
        """Создаёт новый бренд и сразу открывает его редактор.

        Роль: добавляет Brand("Новый бренд") в self.brands, открывает
              BrandEditDialog для заполнения. Пользователь может
              переименовать или удалить бренд сразу.
        """
        new_brand = Brand("Новый бренд")
        self.brands.append(new_brand)
        self._refresh_grid()

        new_brand.sellers.clear()
        brands_dict = {b.name: b for b in self.brands}
        sellers = self.main_window.sellers_brands_service.get_sellers_objects(
            brands_dict=brands_dict,
        )
        dialog = BrandEditDialog(
            self, new_brand, sellers, main_window=self.main_window,
        )
        original_close = dialog.closeEvent

        def new_close(event):
            original_close(event)
            self._refresh_grid()

        dialog.closeEvent = new_close
        dialog.show()

    # ---------- Сохранение ----------

    def save_and_close(self) -> None:
        """Сохраняет бренды в config.json и закрывает окно.

        Роль: вызывается из ExtendedWindowFactory при закрытии окна
              (крестиком или кликом вне). Сериализует self.brands и
              пишет через SellersBrandsService.
        """
        self.main_window.sellers_brands_service.set_brands_objects(self.brands)
        self.close()


class BrandEditDialog(QMainWindow):
    """Диалог редактирования одного бренда.

    Назначение:
        Позволяет изменить имя бренда, список ключей (по которым
        бренд распознаётся в названиях товаров) и список связанных
        продавцов. Удалить бренд целиком.

    Роль в программе:
        Открывается из BrandsWindow по клику на бренд или при
        добавлении нового. Закрывается без кнопок «ОК»/«Отмена» —
        изменения применяются по мере редактирования, финальное
        сохранение — при закрытии.
    """

    def __init__(self, parent=None, brand: Brand = None,
                 sellers: list = None, main_window=None):
        """Конструктор.

        Вход:
            parent — BrandsWindow.
            brand — Brand, который редактируем.
            sellers — список всех Seller (для добавления в бренд).
            main_window — MainWindow, чтобы сохранять изменения через
                          sellers_brands_service.
        """
        super().__init__(parent)
        self.brand = brand
        self.sellers = sellers if sellers is not None else []
        self.main_window = main_window
        self.bg_color = (40, 30, 50, 0.95)
        # NEW: флаг «бренд удалён» — чтобы closeEvent не трогал уже
        # удалённый объект (имя/ключи).
        self._deleted = False

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=f"Редактирование бренда: {brand.name}",
            bg_color=self.bg_color,
            close_button=False,
            draggable=True,
            close_on_click_outside=True,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=550,
            default_height=500,
        )

        # --- Поле имени ---
        self.name_edit = InputWidgetFactory.create_default_line_edit(
            self, text=brand.name,
        )
        content_layout.addWidget(self.name_edit)

        # --- Две колонки: ключи и продавцы ---
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(10)

        # Левая колонка: ключи бренда.
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(LabelFactory.create_header_label(
            self, "Ключи:", alignment=Qt.AlignLeft,
        ))
        self.keys_list = EditableListWidget(
            self, initial_items=brand.keys, add_text="+ добавить ключ",
        )
        left_layout.addWidget(self.keys_list)
        cols_layout.addWidget(left_widget)

        # Правая колонка: связанные продавцы.
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.addWidget(LabelFactory.create_header_label(
            self, "Продавцы:", alignment=Qt.AlignLeft,
        ))
        self.sellers_widget = QWidget()
        self.sellers_layout = QVBoxLayout(self.sellers_widget)
        self.sellers_layout.setContentsMargins(0, 0, 0, 0)
        self.sellers_layout.setSpacing(2)
        scroll = ListWidgetFactory.create_scroll_area(
            self, widget=self.sellers_widget,
            widget_resizable=True, bg_color=self.bg_color,
        )
        right_layout.addWidget(scroll)
        add_seller_btn = ButtonFactory.create_button(
            self, "+ добавить продавца", (100, 80, 120, 0.7),
            padding="6px 12px",
        )
        add_seller_btn.clicked.connect(self._add_seller)
        right_layout.addWidget(add_seller_btn)
        cols_layout.addWidget(right_widget)

        content_layout.addLayout(cols_layout)

        # --- Нижние кнопки: «Готово» и «Удалить бренд» ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(400, 30),
        )
        ok_btn.clicked.connect(self.close)
        bottom_layout.addWidget(ok_btn)

        delete_btn = ButtonFactory.create_button(
            self, "Удалить бренд", (180, 60, 60, 0.8), fixed_size=(120, 30),
        )
        delete_btn.clicked.connect(self._delete_brand)
        bottom_layout.addWidget(delete_btn)
        content_layout.addLayout(bottom_layout)

        self._populate_sellers()

    # ---------- Продавцы бренда ----------

    def _populate_sellers(self) -> None:
        """Заполняет правую колонку связанными продавцами.

        Роль: очищает layout, дедуплицирует brand.sellers по имени
              (защита от повторного добавления), отрисовывает строки.
        """
        while self.sellers_layout.count():
            item = self.sellers_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Дедупликация по имени — на случай, если один seller
        # попал в brand.sellers дважды.
        seen = set()
        unique = []
        for s in self.brand.sellers:
            if s.name not in seen:
                seen.add(s.name)
                unique.append(s)
        self.brand.sellers = unique

        for seller in unique:
            self._add_seller_row(seller)

    def _add_seller_row(self, seller: Seller) -> None:
        """Добавляет строку продавца с кнопкой удаления.

        Вход: seller — Seller, связанный с брендом.
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        name_lbl = LabelFactory.create_label(
            self, seller.name,
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        row_layout.addWidget(name_lbl)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._remove_seller_row(row_widget, seller),
        )
        row_layout.addWidget(del_btn)

        self.sellers_layout.addWidget(row_widget)

    def _remove_seller_row(self, row_widget, seller: Seller) -> None:
        """Отвязывает продавца от бренда и удаляет строку.

        Вход: row_widget — виджет строки; seller — Seller.
        Роль: remove_seller разрывает двустороннюю связь. Затем
              удаляем строку и сохраняем изменения.
        """
        self.brand.remove_seller(seller)
        row_widget.deleteLater()
        self._save_sellers()

    def _add_seller(self) -> None:
        """Показывает диалог выбора продавца из ещё не связанных.

        Роль: фильтрует self.sellers, оставляя тех, у кого этого
              бренда ещё нет. Показывает QInputDialog.getItem.
              При выборе — добавляет связь и строку.
        """
        # Продавцы, у которых этого бренда ещё нет.
        available = [s for s in self.sellers if self.brand not in s.brands]
        if not available:
            NotificationDialog.notify(
                self,
                "Все продавцы уже привязаны к этому бренду.",
                title_text="Информация",
                bg_color=self.bg_color,
            )
            return

        names = [s.name for s in available]
        item, ok = QInputDialog.getItem(
            self, "Выбор продавца", "Продавец:", names, 0, False,
        )
        if ok and item:
            seller = next(s for s in available if s.name == item)
            self.brand.add_seller(seller)
            self._add_seller_row(seller)
            self._save_sellers()

    def _save_sellers(self) -> None:
        """Сохраняет список продавцов с обновлёнными связями.

        Роль: после add_seller / remove_seller модель Seller
              изменилась (поле brands). Записываем через
              sellers_brands_service — иначе изменения потеряются.
        """
        if self.main_window:
            self.main_window.sellers_brands_service.set_sellers_objects(
                self.sellers,
            )

    # ---------- Удаление бренда ----------

    def _delete_brand(self) -> None:
        """Удаляет бренд целиком с подтверждением.

        Роль:
            1. Спрашивает подтверждение через MessageDialog.
            2. Отвязывает бренд от всех связанных продавцов —
               сохраняет sellers через сервис.
            3. Убирает бренд из self.brands родителя (BrandsWindow).
            4. Сохраняет бренды через сервис.
            5. Перерисовывает сетку родителя и закрывает диалог.

        Флаг self._deleted нужен, чтобы closeEvent не пытался
        прочитать self.brand.name и self.keys_list — после удаления
        это уже неактуально.
        """
        reply = MessageDialog.question(
            self,
            f"Вы уверены, что хотите удалить бренд '{self.brand.name}'?\n"
            f"Он будет отвязан от всех продавцов.",
            title_text="Подтверждение удаления",
            bg_color=self.bg_color,
        )
        if reply != QDialog.Accepted:
            return

        # 1. Отвязываем бренд от всех продавцов.
        #    remove_seller сам обновляет обе стороны двусторонней связи.
        for seller in list(self.brand.sellers):
            self.brand.remove_seller(seller)

        # 2. Сохраняем продавцов с обновлёнными связями.
        if self.main_window:
            self.main_window.sellers_brands_service.set_sellers_objects(
                self.sellers,
            )

        # 3. Убираем бренд из списка родителя (BrandsWindow).
        parent = self.parent()
        if parent is not None and hasattr(parent, "brands"):
            if self.brand in parent.brands:
                parent.brands.remove(self.brand)

            # 4. Сохраняем обновлённый список брендов.
            if self.main_window:
                self.main_window.sellers_brands_service.set_brands_objects(
                    parent.brands,
                )

        # 5. Помечаем диалог как «удалён» — closeEvent больше не
        #    должен трогать объект brand.
        self._deleted = True
        self.close()

    # ---------- Сбор и закрытие ----------

    def _collect_keys(self) -> None:
        """Переносит ключи из EditableListWidget в модель Brand.

        Роль: вызывается перед закрытием — чтобы изменения ключей
              не потерялись.
        """
        self.brand.keys = self.keys_list.get_items()

    def closeEvent(self, event) -> None:
        """Применяет правки и закрывает диалог.

        Вход: event — событие закрытия.
        Роль: если бренд уже удалён — просто закрываемся. Иначе
              сохраняем введённое имя и ключи в модель. Сохранение
              в config.json произойдёт при закрытии BrandsWindow
              (через save_and_close) — здесь модель уже обновлена.
        """
        # Если бренд удалён — не трогаем уже отвязанный объект.
        if self._deleted:
            super().closeEvent(event)
            return

        self.brand.name = self.name_edit.text().strip()
        self._collect_keys()
        super().closeEvent(event)