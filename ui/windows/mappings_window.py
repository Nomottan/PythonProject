from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QMessageBox,
    QComboBox, QLabel
)
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory, LayoutFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from models.models import Brand


class BrandMappingsWindow(QDialog):
    """Окно просмотра и редактирования сохранённых сопоставлений (бренды)."""

    def __init__(self, parent, service, config, mappings=None):
        super().__init__(parent)
        self.parent_window = parent
        self.service = service
        self.config = config  # <-- переместите сюда
        self.service.set_brands_from_config(self._get_brands_from_config())
        self.mappings = mappings if mappings is not None else self.service.load_mappings()
        self.brands_list = self._get_brands_from_config()

        # Настройка окна
        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Сохранённые бренды",
            bg_color=(40, 30, 100, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=500,
            default_height=700
        )

        # Заголовок
        title_label = LabelFactory.create_header_label(self, "Сохранённые бренды")
        content_layout.addWidget(title_label)

        # Кнопка "Удалить всё"
        btn_delete_all = ButtonFactory.create_button(
            self, "Удалить всё", (180, 60, 60, 0.8)
        )
        btn_delete_all.clicked.connect(self._delete_all)
        content_layout.addWidget(btn_delete_all, alignment=Qt.AlignLeft)

        # Прокручиваемая область для списка брендов
        scroll, self.content_widget, self.list_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=4
        )
        content_layout.addWidget(scroll)

        # Кнопка "Сохранить"
        btn_save = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
            padding="8px 16px", fixed_size=(200, 40)
        )
        btn_save.clicked.connect(self._save_and_close)
        LayoutFactory.add_centered_widget(content_layout, btn_save)

        # Заполняем список
        self._populate_list()

    def set_brands_from_config(self, brands_list):
        """Сохраняет список брендов из конфига для нормализации имён."""
        self.brands_from_config = brands_list

    def _get_brands_from_config(self):
        """Возвращает список объектов Brand из конфига."""
        return self.config.get_brands_objects()

    def _populate_list(self):
        """Перестраивает список брендов на основе текущих данных."""
        # Очищаем
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Сортируем бренды по алфавиту
        sorted_brands = sorted(self.mappings.keys(), key=str.lower)

        for brand_name in sorted_brands:
            row = self._create_brand_row(brand_name)
            self.list_layout.addWidget(row)

    def _create_brand_row(self, brand_name):
        """Создаёт строку для одного бренда: кнопка удаления + кнопка бренда."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # Кнопка удаления бренда
        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda checked, b=brand_name: self._delete_brand(b)
        )
        row_layout.addWidget(del_btn)

        # Кнопка бренда (кликабельная)
        brand_btn = ButtonFactory.create_button(
            self, brand_name, (100, 80, 130, 0.8),
            padding="6px 12px", alignment='left'
        )
        brand_btn.clicked.connect(lambda checked, b=brand_name: self._open_brand_details(b))
        row_layout.addWidget(brand_btn, stretch=1)

        return row_widget

    def _delete_brand(self, brand_name):
        """Удаляет бренд и все его сопоставления."""
        if brand_name in self.mappings:
            reply = QMessageBox.question(
                self,
                "Подтверждение удаления",
                f"Вы уверены, что хотите удалить бренд '{brand_name}' и все его сопоставления?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del self.mappings[brand_name]
                self._populate_list()

    def _delete_all(self):
        """Удаляет все бренды и сопоставления (с предупреждением)."""
        if not self.mappings:
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение удаления",
            "Вы уверены, что хотите удалить все сохранённые сопоставления?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.mappings.clear()
            self._populate_list()

    def _open_brand_details(self, brand_name):
        if brand_name not in self.mappings:
            return
        brand_data = self.mappings[brand_name]
        detail_window = BrandDetailWindow(
            parent=self.parent_window,  # <-- CompareWindow
            brand_name=brand_name,
            brand_data=brand_data,
            all_brands=self._get_brands_from_config(),
            parent_window=self  # <-- BrandMappingsWindow для обновления
        )
        detail_window.exec()

    def refresh_data(self):
        """Перезагружает данные из файла и обновляет список."""
        self.mappings = self.service.load_mappings()
        self._populate_list()

    def _save_and_close(self):
        """Сохраняет изменения в файл и закрывает окно."""
        self.service.save_mappings(self.mappings)
        self.accept()

class BrandDetailWindow(QDialog):
    def __init__(self, parent, brand_name, brand_data, all_brands, parent_window):
        super().__init__(parent)           # parent – CompareWindow
        self.brand_name = brand_name
        self.brand_data = brand_data
        self.all_brands = all_brands
        self.parent_window = parent_window  # BrandMappingsWindow
        self.original_brand_name = brand_name

        # Настройка окна с центрированием относительно parent
        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,                  # <-- CompareWindow
            title=f"Бренд: {brand_name}",
            bg_color=(40, 80, 110, 0.95),
            close_button=True,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=800,
            default_height=900
        )

        # Заголовок
        title_label = LabelFactory.create_header_label(self, f"Сопоставления для бренда: {brand_name}")
        content_layout.addWidget(title_label)

        # Прокручиваемая область для списка сопоставлений
        scroll, self.content_widget, self.list_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=4
        )
        content_layout.addWidget(scroll)

        # Кнопка "Сохранить"
        btn_save = ButtonFactory.create_button(
            self, "Сохранить", (70, 120, 90, 0.8),
            padding="8px 16px", fixed_size=(200, 40)
        )
        btn_save.clicked.connect(self._save_and_close)
        LayoutFactory.add_centered_widget(content_layout, btn_save)

        # Заполняем список
        self._populate_list()

    def _populate_list(self):
        """Перестраивает список сопоставлений на основе текущих данных."""
        # Очищаем
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Сортируем по supply_name (можно и по другому)
        sorted_articles = sorted(self.brand_data.keys(), key=lambda a: self.brand_data[a].get('supply_name', '').lower())

        for article in sorted_articles:
            entry = self.brand_data[article]
            row = self._create_mapping_row(article, entry)
            self.list_layout.addWidget(row)

    def _create_mapping_row(self, article, entry):
        """Создаёт строку для одного сопоставления."""
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # Кнопка удаления
        del_btn = ButtonFactory.create_delete_button(
            self,
            callback=lambda: self._delete_mapping(article)
        )
        row_layout.addWidget(del_btn)

        # Кнопка редактирования бренда (карандаш)
        edit_btn = ButtonFactory.create_button(
            self, "✎", (100, 100, 120, 0.6),
            fixed_size=(25, 25), padding="0px"
        )
        edit_btn.clicked.connect(lambda checked, a=article: self._edit_brand_for_mapping(a))
        row_layout.addWidget(edit_btn)

        # Текст: supply_name - candidate_name
        supply_name = entry.get('supply_name', '')
        candidate_name = entry.get('candidate_name', '')
        label_text = f"{supply_name} → {candidate_name}"
        label = LabelFactory.create_label(
            self, label_text,
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        row_layout.addWidget(label, stretch=1)

        return row_widget

    def _delete_mapping(self, article):
        """Удаляет одно сопоставление."""
        if article in self.brand_data:
            reply = QMessageBox.question(
                self,
                "Подтверждение удаления",
                "Удалить это сопоставление?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del self.brand_data[article]
                self._populate_list()

    def _edit_brand_for_mapping(self, article):
        """Открывает диалог выбора бренда для перемещения записи."""
        if article not in self.brand_data:
            return

        # Список брендов из конфига (имена)
        brand_names = [b.name for b in self.all_brands]
        if not brand_names:
            msg = "Нет доступных брендов. Сначала добавьте бренды в окне 'Бренды'."
            reply = QMessageBox.question(
                self,
                "Нет брендов",
                msg + "\n\nПерейти в окно брендов?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                main_window = self.parent_window.parent_window.main_window
                if hasattr(main_window, 'open_brands_window'):
                    main_window.open_brands_window()
            return

        # Создаём диалог выбора с родителем CompareWindow
        parent_for_dialog = self.parent_window.parent_window  # CompareWindow
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
            default_height=150
        )

        content_layout.addWidget(LabelFactory.create_label(
            dialog, "Выберите бренд для перемещения:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4"
        ))

        combo = InputWidgetFactory.create_combo_box(
            dialog, items=brand_names, current_index=0
        )
        combo.setStyleSheet("""
            QComboBox {
                background-color: rgba(60, 50, 70, 0.9);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 3px;
                padding: 3px;
            }
            QComboBox::drop-down {
                border: none;
            }
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

        # ---- КНОПКИ ----
        btn_layout = QHBoxLayout()
        btn_ok = ButtonFactory.create_button(
            dialog, "Переместить", (70, 120, 90, 0.8), fixed_size=(120, 30)
        )
        btn_cancel = ButtonFactory.create_button(
            dialog, "Отмена", (150, 80, 80, 0.8), fixed_size=(120, 30)
        )
        btn_ok.clicked.connect(lambda: self._move_mapping(article, combo.currentText(), dialog))
        btn_cancel.clicked.connect(dialog.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        content_layout.addLayout(btn_layout)  # <-- ВАЖНО: добавляем кнопки в макет

        dialog.exec()

    def _move_mapping(self, article, new_brand_name, dialog):
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

            # Обновляем список в текущем окне
            self._populate_list()
            dialog.accept()
        except Exception as e:
            print(f"Ошибка в _move_mapping: {e}")
            dialog.reject()

    def _save_and_close(self):
        # 1. Сохраняем изменения в файл через сервис родительского окна
        self.parent_window.service.save_mappings(self.parent_window.mappings)
        # 2. Обновляем данные в родительском окне (перезагружаем из файла)
        self.parent_window.refresh_data()
        # 3. Закрываем текущее окно
        self.accept()