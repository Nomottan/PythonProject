"""
Окно сохранённых сопоставлений артикулов.

Содержит два класса:
    BrandMappingsWindow  — список брендов с сохранёнными сопоставлениями.
    BrandDetailWindow    — сопоставления одного бренда.

Роль в программе:
    Открывается из CompareWindow. Оба окна переведены на
    BaseEditDialog, кнопка «Сохранить» — в _build_content.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QDialog

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory, LayoutFactory,
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.windows.message_dialog import MessageDialog
from ui.base.base_edit_dialog import BaseEditDialog


class BrandMappingsWindow(BaseEditDialog):
    """Окно просмотра и редактирования сохранённых сопоставлений (бренды).

    Назначение:
        Список брендов, каждый с кнопкой удаления и кнопкой
        «открыть детали». Кнопка «Удалить всё» очищает весь словарь.

    Роль в программе:
        Открывается из CompareWindow. Работает через CompareService
        (mappings) и SellersBrandsService (бренды для подсказок).
    """

    def __init__(self, parent, service, sellers_brands_service,
                 mappings=None):
        """Конструктор.

        Вход:
            parent — CompareWindow.
            service — CompareService: load_mappings / save_mappings.
            sellers_brands_service — SellersBrandsService: список брендов.
            mappings — словарь сопоставлений. Если None — грузим из service.
        """
        self.parent_window = parent
        self.service = service
        self.sellers_brands_service = sellers_brands_service
        self.mappings = (
            mappings if mappings is not None
            else self.service.load_mappings()
        )
        self.brands_list = self._get_brands_from_config()
        self.bg_color = (40, 30, 100, 0.95)

        super().__init__(
            parent=parent,
            title="Сохранённые бренды",
            bg_color=self.bg_color,
            close_button=True,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=500,
            height=700,
        )

    # ---------- Публичный API ----------

    def _get_brands_from_config(self):
        """Возвращает список брендов через сервис."""
        return self.sellers_brands_service.get_brands_objects()

    def refresh_data(self) -> None:
        """Перечитывает mappings из сервиса и перерисовывает список."""
        self.mappings = self.service.load_mappings()
        self._populate_list()

    # ---------- Наполнение ----------

    def _build_content(self, layout) -> None:
        """Заголовок, «Удалить всё», скролл с брендами, «Сохранить».

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Сохранённые бренды",
        ))

        btn_delete_all = ButtonFactory.create_button(
            self, "Удалить всё", (180, 60, 60, 0.8),
        )
        btn_delete_all.clicked.connect(self._delete_all)
        layout.addWidget(btn_delete_all, alignment=Qt.AlignLeft)

        scroll, _, self.list_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=4, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll)

        btn_save = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
            padding="8px 16px", fixed_size=(200, 40),
        )
        btn_save.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, btn_save)

        self._populate_list()

    def _collect_result(self):
        """Сохраняет mappings через сервис.

        Выход: None.
        """
        self.service.save_mappings(self.mappings)
        return None

    # ---------- Отрисовка списка ----------

    def _populate_list(self) -> None:
        """Перестраивает список брендов."""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sorted_brands = sorted(self.mappings.keys(), key=str.lower)
        for brand_name in sorted_brands:
            row = self._create_brand_row(brand_name)
            self.list_layout.addWidget(row)

    def _create_brand_row(self, brand_name: str) -> QWidget:
        """Строка бренда: ✕ + кнопка с именем."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda checked, b=brand_name: self._delete_brand(b),
        )
        row_layout.addWidget(del_btn)

        brand_btn = ButtonFactory.create_button(
            self, brand_name, (100, 80, 130, 0.8),
            padding="6px 12px", alignment='left',
        )
        brand_btn.clicked.connect(
            lambda checked, b=brand_name: self._open_brand_details(b)
        )
        row_layout.addWidget(brand_btn, stretch=1)

        return row_widget

    # ---------- Действия ----------

    def _delete_brand(self, brand_name: str) -> None:
        """Удаляет бренд и все его сопоставления с подтверждением."""
        if brand_name not in self.mappings:
            return
        reply = MessageDialog.question(
            self,
            f"Вы уверены, что хотите удалить бренд '{brand_name}' "
            f"и все его сопоставления?",
            title_text="Подтверждение удаления",
            bg_color=self.bg_color,
        )
        if reply == QDialog.Accepted:
            del self.mappings[brand_name]
            self._populate_list()

    def _delete_all(self) -> None:
        """Очищает все сопоставления с подтверждением."""
        if not self.mappings:
            return
        reply = MessageDialog.question(
            self,
            "Вы уверены, что хотите удалить все сохранённые сопоставления?",
            title_text="Подтверждение удаления",
            bg_color=self.bg_color,
        )
        if reply == QDialog.Accepted:
            self.mappings.clear()
            self._populate_list()

    def _open_brand_details(self, brand_name: str) -> None:
        """Открывает окно деталей бренда."""
        if brand_name not in self.mappings:
            return
        brand_data = self.mappings[brand_name]
        detail_window = BrandDetailWindow(
            parent=self.parent_window,
            brand_name=brand_name,
            brand_data=brand_data,
            all_brands=self._get_brands_from_config(),
            parent_window=self,
        )
        detail_window.exec()


class BrandDetailWindow(BaseEditDialog):
    """Окно сопоставлений одного бренда.

    Назначение:
        Список сопоставлений «артикул → supply_name → candidate_name».
        Каждую строку можно удалить или переместить в другой бренд.

    Роль в программе:
        Открывается из BrandMappingsWindow по клику на бренд.
        Наследник BaseEditDialog: кнопка «Сохранить» в _build_content.
    """

    def __init__(self, parent, brand_name, brand_data, all_brands,
                 parent_window):
        """Конструктор.

        Вход:
            parent — родитель.
            brand_name — имя бренда.
            brand_data — словарь {article: {...}} этого бренда.
            all_brands — все бренды (для перемещения сопоставления).
            parent_window — BrandMappingsWindow: чтобы вызывать
                            refresh_data после сохранения.
        """
        self.brand_name = brand_name
        self.brand_data = brand_data
        self.all_brands = all_brands
        self.parent_window = parent_window
        self.original_brand_name = brand_name
        self.bg_color = (40, 80, 110, 0.95)

        super().__init__(
            parent=parent,
            title=f"Бренд: {brand_name}",
            bg_color=self.bg_color,
            close_button=True,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=800,
            height=900,
        )

    def _build_content(self, layout) -> None:
        """Заголовок, скролл с сопоставлениями, «Сохранить»."""
        layout.addWidget(LabelFactory.create_header_label(
            self, f"Сопоставления для бренда: {self.brand_name}",
        ))

        scroll, _, self.list_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=4, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll)

        btn_save = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
            padding="8px 16px", fixed_size=(200, 40),
        )
        btn_save.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, btn_save)

        self._populate_list()

    def _collect_result(self):
        """Сохраняет mappings родителя и обновляет его список.

        Выход: None.
        Роль: пишем общий словарь сопоставлений через сервис и просим
              родителя перечитать данные — на случай, если строки
              перемещались между брендами.
        """
        self.parent_window.service.save_mappings(
            self.parent_window.mappings,
        )
        self.parent_window.refresh_data()
        return None

    def _populate_list(self) -> None:
        """Перестраивает список сопоставлений."""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sorted_articles = sorted(
            self.brand_data.keys(),
            key=lambda a: self.brand_data[a].get('supply_name', '').lower(),
        )
        for article in sorted_articles:
            entry = self.brand_data[article]
            row = self._create_mapping_row(article, entry)
            self.list_layout.addWidget(row)

    def _create_mapping_row(self, article: str, entry: dict) -> QWidget:
        """Строка сопоставления: ✕ + ✎ + текст «supply → candidate»."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._delete_mapping(article),
        )
        row_layout.addWidget(del_btn)

        edit_btn = ButtonFactory.create_button(
            self, "✎", (100, 100, 120, 0.6),
            fixed_size=(25, 25), padding="0px",
        )
        edit_btn.clicked.connect(
            lambda checked, a=article: self._edit_brand_for_mapping(a)
        )
        row_layout.addWidget(edit_btn)

        supply_name = entry.get('supply_name', '')
        candidate_name = entry.get('candidate_name', '')
        label_text = f"{supply_name} → {candidate_name}"
        label = LabelFactory.create_label(
            self, label_text,
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        row_layout.addWidget(label, stretch=1)

        return row_widget

    def _delete_mapping(self, article: str) -> None:
        """Удаляет одно сопоставление с подтверждением."""
        if article not in self.brand_data:
            return
        reply = MessageDialog.question(
            self,
            "Удалить это сопоставление?",
            title_text="Подтверждение удаления",
            bg_color=self.bg_color,
        )
        if reply != QDialog.Accepted:
            return

        # Удаляем из локального словаря.
        del self.brand_data[article]
        # Удаляем из родительского словаря.
        if (self.brand_name in self.parent_window.mappings
                and article in self.parent_window.mappings[self.brand_name]):
            del self.parent_window.mappings[self.brand_name][article]

        # Если бренд стал пустым — убираем его из родителя и закрываемся.
        if not self.brand_data:
            del self.parent_window.mappings[self.brand_name]
            self.parent_window._populate_list()
            self.close()
        else:
            self._populate_list()

    def _edit_brand_for_mapping(self, article: str) -> None:
        """Открывает диалог перемещения сопоставления в другой бренд."""
        if article not in self.brand_data:
            return

        brand_names = [b.name for b in self.all_brands]
        if not brand_names:
            msg = ("Нет доступных брендов. Сначала добавьте бренды "
                   "в окне 'Бренды'.")
            reply = MessageDialog.question(
                self,
                msg + "\n\nПерейти в окно брендов?",
                title_text="Нет брендов",
                bg_color=self.bg_color,
            )
            if reply == QDialog.Accepted:
                main_window = self.parent_window.parent_window.main_window
                if hasattr(main_window, 'open_brands_window'):
                    main_window.open_brands_window()
            return

        # Простой inline-диалог выбора бренда — оставляем через
        # ExtendedWindowFactory, это не форма редактирования.
        parent_for_dialog = self.parent_window.parent_window
        dialog = QDialog(parent_for_dialog)
        dialog.setWindowTitle("Выбор бренда")
        dialog.setModal(True)
        dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setAttribute(Qt.WA_TranslucentBackground)

        content_layout = ExtendedWindowFactory.setup_window(
            window=dialog,
            parent=parent_for_dialog,
            title="Выбор бренда",
            bg_color=(90, 90, 120, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=300,
            default_height=150,
        )

        content_layout.addWidget(LabelFactory.create_label(
            dialog, "Выберите бренд для перемещения:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
        ))

        combo = InputWidgetFactory.create_combo_box(
            dialog, items=brand_names, current_index=0,
        )
        combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(60, 50, 70, 0.9);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #d4d4d4;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(60, 50, 70, 0.95);
                color: #d4d4d4;
                selection-background-color: rgba(100, 80, 120, 0.8);
                selection-color: #ffffff;
                border: 1px solid #5a4a5c;
            }
        """)
        content_layout.addWidget(combo)

        btn_layout = QHBoxLayout()
        btn_ok = ButtonFactory.create_button(
            dialog, "Переместить", (70, 120, 90, 0.8), fixed_size=(120, 30),
        )
        btn_cancel = ButtonFactory.create_button(
            dialog, "Отмена", (150, 80, 80, 0.8), fixed_size=(120, 30),
        )
        btn_ok.clicked.connect(
            lambda: self._move_mapping(article, combo.currentText(), dialog)
        )
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        content_layout.addLayout(btn_layout)

        dialog.exec()

    def _move_mapping(self, article: str, new_brand_name: str,
                      dialog: QDialog) -> None:
        """Перемещает сопоставление в другой бренд."""
        try:
            if new_brand_name == self.brand_name:
                dialog.reject()
                return

            entry = self.brand_data.pop(article, None)
            if entry is None:
                dialog.reject()
                return

            parent_mappings = self.parent_window.mappings
            if new_brand_name not in parent_mappings:
                parent_mappings[new_brand_name] = {}
            parent_mappings[new_brand_name][article] = entry

            # Если текущий бренд стал пустым — удаляем его из родителя.
            if not self.brand_data:
                del parent_mappings[self.brand_name]

            self._populate_list()
            self.parent_window._populate_list()
            dialog.accept()
        except Exception as e:
            print(f"Ошибка в _move_mapping: {e}")
            dialog.reject()