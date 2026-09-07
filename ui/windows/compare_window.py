from PySide6.QtWidgets import (
    QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QTableWidget, QHeaderView, QTableWidgetItem, QCheckBox,
    QTextEdit, QApplication, QSizePolicy
)
from PySide6.QtCore import Qt
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory, ListWidgetFactory,
    LayoutFactory, WindowFactory, FileDialogFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.widgets.path_selector import PathSelector
from pathlib import Path
from services.compare_service import CompareService

class CompareWindow(QMainWindow):
    """Окно сравнения листа поставки с фактическими поставками."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

        # Переменные состояния
        self.target_dir = parent.config.get("target_dir", None)
        self.supply_file = None          # путь к файлу листа поставки
        self.supply_files = []           # список путей к файлам поставок

        # Сервис сравнения (передаём лог-функцию и множество брендов)
        brands = parent.config.get_brands_objects()
        brands_set = set()
        for b in brands:
            brands_set.add(b.name.lower())
            for key in b.keys:
                brands_set.add(key.lower())

        self.service = CompareService(
            log_callback=self.log,
            brands_set=brands_set
        )

        # Настройка окна через WindowFactory
        main_layout = WindowFactory.setup_child_window(
            self, "Сравнение поставок",
            bg_color=(80, 70, 90, 0.95)
        )

        # ============================================================
        # ИНИЦИАЛИЗАЦИЯ ЭЛЕМЕНТОВ
        # ============================================================

        # ---- Текстовая инструкция ----
        self.instruction_label = LabelFactory.create_label(
            self,
            text="Подготовка к сравнению поставок\n"
                 "Шаг 1: Выберите папку для сохранения результатов\n"
                 "Шаг 2: Выберите файл листа поставки (один Excel-файл)\n"
                 "Шаг 3: Добавьте файлы с фактическими поставками (можно несколько)\n"
                 "Шаг 4: Нажмите 'Подготовить для работы' – данные будут загружены\n"
                 "Шаг 5: Последовательно выполняйте этапы 1→2→3\n"
                 "Шаг 6: Сформируйте отчёт",
            bg_color=(0, 0, 0, 0),
            text_color="#c2c2c2",
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True
        )
        main_layout.addWidget(self.instruction_label)

        # ---- Виджет выбора пути ----
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите папку для результатов"
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)
        main_layout.addWidget(self.path_selector)

        # ---- Строка выбора файла листа поставки ----
        self.btn_choose_file = ButtonFactory.create_button(
            self, "Выбрать Лист сверки", (100, 120, 100, 0.8)
        )
        self.btn_choose_file.clicked.connect(self.select_supply_file)

        self.file_label = LabelFactory.create_label(
            self, "Файл не выбран",
            bg_color=(64, 48, 66, 128),
            text_color="#d4d4d4",
            padding="4px 8px",
            border_radius=5,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_family="Consolas, monospace",
            font_size=10
        )

        file_row = LayoutFactory.create_row(
            self, self.btn_choose_file, self.file_label, spacing=5
        )
        main_layout.addWidget(file_row)

        # ---- ДВЕ КОЛОНКИ ----
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)

        # Левая колонка (кнопки)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.step_label = LabelFactory.create_label(
            self, "Текущий шаг: Ожидание",
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_size=12,
            font_weight="bold"
        )
        left_layout.addWidget(self.step_label)

        # Кнопки действий
        self.btn_prepare = ButtonFactory.create_button(
            self, "Подготовить для работы", (70, 120, 160, 0.8),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_prepare.clicked.connect(self.on_prepare)
        left_layout.addWidget(self.btn_prepare)

        self.btn_stage1 = ButtonFactory.create_button(
            self, "Этап 1 (жёсткая сверка)", (70, 140, 200, 0.8),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_stage1.clicked.connect(self.on_stage1)
        self.btn_stage1.setEnabled(False)
        left_layout.addWidget(self.btn_stage1)

        self.btn_stage2 = ButtonFactory.create_button(
            self, "Этап 2 (мягкая сверка)", (140, 140, 70, 0.8),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_stage2.clicked.connect(self.on_stage2)
        self.btn_stage2.setEnabled(False)
        left_layout.addWidget(self.btn_stage2)

        self.btn_stage3 = ButtonFactory.create_button(
            self, "Этап 3 (ручной выбор)", (200, 140, 70, 0.8),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_stage3.clicked.connect(self.on_stage3)
        self.btn_stage3.setEnabled(False)
        left_layout.addWidget(self.btn_stage3)

        self.btn_report = ButtonFactory.create_button(
            self, "Сформировать отчёт", (70, 160, 200, 0.8),
            padding="8px 16px", fixed_size=(220, 35)
        )
        self.btn_report.clicked.connect(self.on_generate_report)
        self.btn_report.setEnabled(False)

        left_layout.addWidget(self.btn_report)
        left_layout.addStretch()

        # Правая колонка (список файлов поставок)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        self.btn_add_supply = ButtonFactory.create_button(
            self, "Добавить файлы поставок", (70, 120, 160, 0.8),
            padding="6px 12px", fixed_size=(220, 30)
        )
        self.btn_add_supply.clicked.connect(self.select_supply_files)
        right_layout.addWidget(self.btn_add_supply)

        self.list_supply = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=220,
            fixed_height=200,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10
        )
        right_layout.addWidget(self.list_supply)
        right_layout.addStretch()

        columns_layout.addWidget(left_widget)
        columns_layout.addWidget(right_widget)
        main_layout.addLayout(columns_layout)

        btn_mappings = ButtonFactory.create_button(
            self, "Сохранённые сопоставления", (70, 120, 160, 0.8),
            padding="8px 16px", fixed_size=(200, 30)
        )
        btn_mappings.clicked.connect(self._open_mappings_window)
        mappings_row = LayoutFactory.create_row(
            self, btn_mappings,
            alignment=Qt.AlignCenter
        )
        self.btn_mappings = btn_mappings
        main_layout.addWidget(mappings_row)

        # ---- Лог-область ----
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(30, 20, 35, 0.3);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 5px;
                padding: 5px;
                font-family: Consolas, monospace;
                font-size: 10px;
            }
        """)
        self.status_display.setMaximumHeight(200)
        self.status_display.setMinimumHeight(100)
        main_layout.addWidget(self.status_display)

        # Инициализация
        self.log("Окно сравнения поставок готово к работе.")

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================

    def _on_target_dir_changed(self, new_path):
        self.target_dir = new_path
        self.parent().config.set("target_dir", new_path)
        self.log("Целевая папка обновлена: " + new_path)

    def log(self, msg):
        self.status_display.append(msg)

    # ============================================================
    # ОБРАБОТЧИКИ ВЫБОРА ФАЙЛОВ
    # ============================================================

    def select_supply_file(self):
        start_dir = self.parent().config.get("last_compare_supply_dir", None) or self.target_dir or str(Path.home())
        file_path = FileDialogFactory.open_file_dialog(
            self, "Выберите Excel-файл листа поставки",
            default_dir=start_dir,
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER
        )
        if file_path:
            self.supply_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.parent().config.set("last_compare_supply_dir", str(Path(file_path).parent))
            self.log(f"Выбран файл поставки: {Path(file_path).name}")

    def select_supply_files(self):
        start_dir = self.parent().config.get("last_compare_supplies_dir", None) or self.target_dir or str(Path.home())
        files = FileDialogFactory.open_files_dialog(
            self, "Выберите файлы с поставками",
            default_dir=start_dir,
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER
        )
        if files:
            for f in files:
                if f not in self.supply_files:
                    self.supply_files.append(f)
                    self.list_supply.addItem(Path(f).name)
            if files:
                first_file = Path(files[0])
                self.parent().config.set("last_compare_supplies_dir", str(first_file.parent))
            self.log(f"Добавлено {len(files)} файлов поставок. Всего: {len(self.supply_files)}")

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК ДЕЙСТВИЙ
    # ============================================================

    def on_prepare(self):
        if not self.target_dir:
            self.log("Сначала выберите целевую папку.")
            return
        if not self.supply_file:
            self.log("Сначала выберите файл листа поставки.")
            return
        if not self.supply_files:
            self.log("Добавьте хотя бы один файл с поставками.")
            return

        self.log("=== ПОДГОТОВКА ДАННЫХ ===")
        try:
            # 1. Копирование листа поставки
            self.log("Шаг 1: Копирование листа поставки...")
            copied_path = self.service.copy_supply_sheet(self.supply_file, self.target_dir)
            self.log(f"  Копия создана: {copied_path}")

            # 2. Сборный файл поставок
            self.log("Шаг 2: Формирование сборного файла поставок...")
            consolidated_path = self.service.build_consolidated_supply(self.supply_files, self.target_dir)
            self.log(f"  Сборный файл создан: {consolidated_path}")

            # 3. Загрузка данных в сервис
            self.log("Шаг 3: Загрузка данных...")
            self.service.load_data()
            self.log(f"Загружено товаров: {len(self.service.supply_items)}, кандидатов: {len(self.service.candidates)}")
        except Exception as e:
            import traceback
            self.log(f"Ошибка подготовки: {e}")
            self.log("=" * 60)
            self.log(traceback.format_exc())
            self.log("=" * 60)
            return

        self.btn_stage1.setEnabled(True)
        self.btn_stage2.setEnabled(False)
        self.btn_stage3.setEnabled(False)
        self.btn_report.setEnabled(False)
        self.step_label.setText("Текущий шаг: Подготовка завершена. Нажмите Этап 1")
        self.log("Подготовка завершена. Можно переходить к Этапу 1.")

    def on_stage1(self):
        if not self.service.supply_items or not self.service.candidates:
            self.log("Данные не загружены. Выполните подготовку.")
            return
        self.log("=== ЗАПУСК ЭТАПА 1 ===")
        try:
            self.service.run_stage1(parent_widget=self)
        except Exception as e:
            self.log(f"Ошибка на этапе 1: {e}")
            return

        # Проверяем, есть ли ещё товары И кандидаты для следующих этапов
        if not self.service.supply_items or not self.service.candidates:
            self.btn_report.setEnabled(True)
            self.step_label.setText("Текущий шаг: Все товары сопоставлены или нет кандидатов. Сформируйте отчёт.")
            self.log("Все товары найдены или нет кандидатов. Можно формировать отчёт.")
        else:
            self.btn_stage2.setEnabled(True)
            self.step_label.setText("Текущий шаг: Этап 1 завершён. Нажмите Этап 2")
            self.log(
                f"Этап 1 завершён. Осталось товаров: {len(self.service.supply_items)}, кандидатов: {len(self.service.candidates)}")

    def on_stage2(self):
        if not self.service.supply_items or not self.service.candidates:
            self.log("Данные не загружены. Выполните подготовку.")
            return
        self.log("=== ЗАПУСК ЭТАПА 2 ===")
        try:
            self.service.run_stage2(self)
        except Exception as e:
            self.log(f"Ошибка на этапе 2: {e}")
            return

        if not self.service.supply_items or not self.service.candidates:
            self.btn_report.setEnabled(True)
            self.step_label.setText("Текущий шаг: Все товары сопоставлены или нет кандидатов. Сформируйте отчёт.")
            self.log("Все товары найдены или нет кандидатов. Можно формировать отчёт.")
        else:
            self.btn_stage3.setEnabled(True)
            self.step_label.setText("Текущий шаг: Этап 2 завершён. Нажмите Этап 3")
            self.log(
                f"Этап 2 завершён. Осталось товаров: {len(self.service.supply_items)}, кандидатов: {len(self.service.candidates)}")

    def on_stage3(self):
        if not self.service.supply_items or not self.service.candidates:
            self.log("Данные не загружены. Выполните подготовку.")
            return
        self.log("=== ЗАПУСК ЭТАПА 3 ===")
        try:
            self.service.run_stage3(self)
        except Exception as e:
            self.log(f"Ошибка на этапе 3: {e}")
            return

        self.btn_report.setEnabled(True)
        self.step_label.setText("Текущий шаг: Все этапы завершены. Сформируйте отчёт")
        self.log("Этап 3 завершён. Можно формировать отчёт.")

    def on_generate_report(self):
        if not self.service.final_items:
            self.log("Нет финальных данных. Выполните все этапы.")
            return
        self.log("=== ФОРМИРОВАНИЕ ОТЧЁТА ===")
        try:
            self.service.generate_report(self.target_dir)
            self.service.save_mappings()  # <- сохранение маппингов
            self.log("Отчёт и сопоставления сохранены.")
        except Exception as e:
            self.log(f"Ошибка при формировании отчёта: {e}")
            return

    def _open_mappings_window(self):
        """Открывает окно редактирования сохранённых сопоставлений."""
        from ui.windows.mappings_window import BrandMappingsWindow
        window = BrandMappingsWindow(
            parent=self,
            service=self.service,
            config=self.main_window.config
        )
        window.exec()



    # ============================================================
    # ЗАКРЫТИЕ ОКНА
    # ============================================================

    def cleanup(self):
        self.supply_file = None
        self.supply_files = []
        self.list_supply.clear()

    def closeEvent(self, event):
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()

class ConfirmMatchDialog(QDialog):
    """Диалог подтверждения совпадения на этапе 2 (мягкая сверка)."""

    def __init__(self, parent, supply_item, candidate_item, similarity_score, total_remaining):
        super().__init__(parent)
        self.supply_item = supply_item
        self.candidate_item = candidate_item
        self.similarity_score = similarity_score
        self.total_remaining = total_remaining
        self.result = None

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=f"Подтверждение совпадения (осталось {total_remaining})",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            modal=True,
            center=True,
            return_content_layout=True,
            default_width=500,
            default_height=450
        )

        # Товар из листа
        content_layout.addWidget(LabelFactory.create_label(
            self, "Товар из листа поставки:",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, supply_item['name'],
            bg_color=(0,0,0,0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {supply_item.get('count', '?')}",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))

        # Разделитель
        content_layout.addWidget(LabelFactory.create_label(
            self, "-" * 50, bg_color=(0,0,0,0), text_color="#888888"
        ))

        # Кандидат из поставки
        content_layout.addWidget(LabelFactory.create_label(
            self, "Найденный кандидат в поставках:",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, candidate_item['name'],
            bg_color=(0,0,0,0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {candidate_item.get('count', '?')}",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))

        # Схожесть
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Схожесть: {int(similarity_score * 100)}%",
            bg_color=(0,0,0,0), text_color="#88dd88", alignment=Qt.AlignLeft
        ))

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        confirm_btn = ButtonFactory.create_button(
            self, "Подтвердить", (70, 160, 90, 0.8), fixed_size=(150, 35)
        )
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)

        reject_btn = ButtonFactory.create_button(
            self, "Отклонить", (160, 70, 70, 0.8), fixed_size=(150, 35)
        )
        reject_btn.clicked.connect(self._on_reject)
        btn_layout.addWidget(reject_btn)
        content_layout.addLayout(btn_layout)

    def _on_confirm(self):
        self.result = "confirmed"
        self.accept()

    def _on_reject(self):
        self.result = "rejected"
        self.accept()

    def get_result(self):
        return self.result

class ManualMatchDialog(QDialog):
    """Диалог ручного выбора на этапе 3."""

    def __init__(self, parent, supply_item, candidates, total_remaining):
        super().__init__(parent)
        print(f"ManualMatchDialog: supply_item = {supply_item}")
        print(f"ManualMatchDialog: candidates = {candidates[:2] if candidates else []}")
        self.supply_item = supply_item
        self.candidates = candidates
        self.total_remaining = total_remaining
        self.selected_candidate = None
        self.skip_all = False

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=f"Ручной выбор (осталось {total_remaining})",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            modal=True,
            center=True,
            draggable=True,
            return_content_layout=True,
            default_width=700,
            default_height=900
        )

        # Товар из листа
        content_layout.addWidget(LabelFactory.create_label(
            self, "Товар из листа поставки:",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, supply_item['name'],
            bg_color=(0,0,0,0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {supply_item.get('count', '?')}",
            bg_color=(0,0,0,0), text_color="#d4d4d4", alignment=Qt.AlignLeft
        ))

        # Разделитель
        content_layout.addWidget(LabelFactory.create_label(
            self, "-" * 50, bg_color=(0,0,0,0), text_color="#888888"
        ))

        # Поле поиска
        search_layout = QHBoxLayout()
        search_layout.addWidget(LabelFactory.create_label(
            self, "Поиск:", bg_color=(0,0,0,0), text_color="#d4d4d4"
        ))
        self.search_edit = InputWidgetFactory.create_default_line_edit(
            self, placeholder="Введите текст для фильтрации..."
        )
        self.search_edit.textChanged.connect(self._filter_list)
        search_layout.addWidget(self.search_edit)
        content_layout.addLayout(search_layout)

        # Список кандидатов
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: rgba(30, 20, 35, 0.3);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 5px;
                padding: 5px;
                font-size: 10px;
            }
            QListWidget::item:selected {
                background-color: rgba(100, 80, 120, 0.8);
            }
        """)
        self._populate_list(candidates)
        content_layout.addWidget(self.list_widget)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_select = ButtonFactory.create_button(
            self, "Выбрать", (70, 160, 90, 0.8), fixed_size=(150, 35)
        )
        self.btn_select.clicked.connect(self._on_select)
        self.btn_select.setEnabled(False)
        btn_layout.addWidget(self.btn_select)

        self.btn_skip = ButtonFactory.create_button(
            self, "Пропустить", (160, 140, 70, 0.8), fixed_size=(150, 35)
        )
        self.btn_skip.clicked.connect(self._on_skip)
        btn_layout.addWidget(self.btn_skip)

        self.btn_skip_all = ButtonFactory.create_button(
            self, "Отложить", (140, 70, 70, 0.8), fixed_size=(150, 35)
        )
        self.btn_skip_all.clicked.connect(self._on_skip_all)
        btn_layout.addWidget(self.btn_skip_all)

        content_layout.addLayout(btn_layout)

        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.repaint()
        QApplication.processEvents()

    def _populate_list(self, candidates):
        self.list_widget.clear()
        for item in candidates:
            display_text = item.get('name', 'Без названия')
            if item.get('count') is not None:
                display_text += f" (Кол-во: {item['count']})"
            self.list_widget.addItem(display_text)
            # Сохраняем весь словарь кандидата
            self.list_widget.item(self.list_widget.count() - 1).setData(Qt.UserRole, item)

    def _filter_list(self, text):
        text = text.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def _on_selection_changed(self):
        selected = self.list_widget.currentItem()
        self.btn_select.setEnabled(selected is not None)

    def _on_select(self):
        selected = self.list_widget.currentItem()
        if selected:
            self.selected_candidate = selected.data(Qt.UserRole)
            self.accept()

    def _on_skip(self):
        self.selected_candidate = None
        self.accept()

    def _on_skip_all(self):
        self.selected_candidate = None
        self.skip_all = True
        self.accept()

    def get_result(self):
        return self.selected_candidate, self.skip_all


class Stage1ReviewDialog(QDialog):
    """Диалог для подтверждения жёстких совпадений (этап 1)."""

    def __init__(self, parent, matches: list):
        super().__init__(parent)
        self.matches = matches
        self.keep = [True] * len(matches)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Подтверждение жёстких совпадений (этап 1)",
            bg_color=(40, 30, 50, 0.95),
            close_button=False,
            modal=True,
            center=True,
            draggable=True,
            return_content_layout=True,
            default_width=850,
            default_height=550
        )

        info_label = LabelFactory.create_label(
            self,
            text=f"Найдено {len(matches)} жёстких совпадений.\nСнимите галочку, чтобы исключить сопоставление.",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4", alignment=Qt.AlignCenter
        )
        content_layout.addWidget(info_label)

        # Таблица с переносом текста
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["№", "Товар из листа", "Кандидат из поставки", "Оставить"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(True)  # Включаем перенос текста
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Настройка столбцов
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)

        # Настройка вертикальных заголовков (автоподбор высоты строк)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        # Стиль с переносом текста
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(30, 20, 35, 0.3);
                color: #d4d4d4;
                border: 1px solid #5a4a5c;
                border-radius: 5px;
                padding: 2px;
                font-size: 10px;
            }
            QTableWidget::item {
                padding: 4px;
                white-space: normal;  /* Перенос текста */
            }
            QHeaderView::section {
                background-color: rgba(60, 50, 70, 0.6);
                color: #d4d4d4;
                padding: 4px;
                border: none;
            }
        """)
        self._populate_table()
        content_layout.addWidget(self.table)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        apply_btn = ButtonFactory.create_button(
            self, "Применить", (70, 160, 90, 0.8), fixed_size=(150, 35)
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        cancel_btn = ButtonFactory.create_button(
            self, "Отменить", (160, 70, 70, 0.8), fixed_size=(150, 35)
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        content_layout.addLayout(btn_layout)

    def _populate_table(self):
        self.table.setRowCount(len(self.matches))
        for i, (item, candidate) in enumerate(self.matches):
            # №
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, num_item)

            # Товар из листа
            name_item = QTableWidgetItem(item.name)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, name_item)

            # Кандидат из поставки
            cand_item = QTableWidgetItem(candidate.name)
            cand_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            cand_item.setFlags(cand_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, cand_item)

            # Чекбокс "Оставить"
            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(lambda state, row=i: self._on_checkbox_changed(row, state))
            self.table.setCellWidget(i, 3, cb)

        # Автоподстройка высоты строк после заполнения всей таблицы
        self.table.resizeRowsToContents()

    def _on_checkbox_changed(self, row, state):
        self.keep[row] = (state == Qt.Checked)

    def _on_apply(self):
        self.accept()

    def get_keep_flags(self):
        return self.keep