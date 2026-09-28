"""
Диалоги сравнения поставок: этап 1, 2, 3.

Содержит три диалога:
    Stage1ReviewDialog  — подтверждение жёстких совпадений (этап 1).
    ConfirmMatchDialog  — подтверждение мягкого совпадения (этап 2).
    ManualMatchDialog   — ручной выбор кандидата (этап 3).

Роль в программе:
    Открываются из CompareWindow через callbacks CompareService.
    Диалоги не знают про CompareService и CompareWindow — циклов
    нет. Логика полностью перенесена из старого
    ui/windows/compare_window.py, поведение сохранено.
"""

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QTableWidget, QHeaderView, QTableWidgetItem,
    QCheckBox, QApplication, QSizePolicy,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
)
from ui.factories.window_factories import ExtendedWindowFactory


class Stage1ReviewDialog(QDialog):
    """Диалог подтверждения жёстких совпадений (этап 1).

    Роль:
        Показывает таблицу найденных пар, пользователь снимает
        галочки, чтобы исключить сопоставления. Результат —
        список флагов keep для каждой пары.
    """

    def __init__(self, parent, matches: list):
        """Конструктор.

        Вход:
            parent — родительское окно (CompareWindow).
            matches — список кортежей (SupplyItem, Candidate).

        Роль: сохраняет пары, инициализирует все флаги keep=True,
              строит раскладку.
        """
        super().__init__(parent)
        self.matches = matches
        self.keep = [True] * len(matches)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Подтверждение жёстких совпадений (этап 1)",
            bg_color=(40, 50, 60, 0.95),
            close_button=False,
            modal=True,
            center=True,
            draggable=True,
            return_content_layout=True,
            default_width=850,
            default_height=550,
        )

        info_label = LabelFactory.create_label(
            self,
            text=(
                f"Найдено {len(matches)} жёстких совпадений.\n"
                f"Снимите галочку, чтобы исключить сопоставление."
            ),
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignCenter,
        )
        content_layout.addWidget(info_label)

        # Таблица с переносом текста.
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["№", "Товар из листа", "Кандидат из поставки", "Оставить"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

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
                white-space: normal;
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

        # Кнопки.
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        apply_btn = ButtonFactory.create_button(
            self, "Применить", (70, 160, 90, 0.8), fixed_size=(150, 35),
        )
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        cancel_btn = ButtonFactory.create_button(
            self, "Отменить", (160, 70, 70, 0.8), fixed_size=(150, 35),
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        content_layout.addLayout(btn_layout)

    def _populate_table(self) -> None:
        """Заполняет таблицу парами."""
        self.table.setRowCount(len(self.matches))
        for i, (item, candidate) in enumerate(self.matches):
            num_item = QTableWidgetItem(str(i + 1))
            num_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, num_item)

            name_item = QTableWidgetItem(item.name)
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, name_item)

            cand_item = QTableWidgetItem(candidate.name)
            cand_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            cand_item.setFlags(cand_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, cand_item)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(
                lambda state, row=i: self._on_checkbox_changed(row, state)
            )
            self.table.setCellWidget(i, 3, cb)

        self.table.resizeRowsToContents()

    def _on_checkbox_changed(self, row: int, state: int) -> None:
        """Обновляет флаг keep[row] по состоянию чекбокса."""
        self.keep[row] = (state == Qt.Checked)

    def _on_apply(self) -> None:
        """Принимает диалог — пользователь согласился с выбором."""
        self.accept()

    def get_keep_flags(self) -> list:
        """Возвращает список флагов «оставить пару»."""
        return self.keep


class ConfirmMatchDialog(QDialog):
    """Диалог подтверждения мягкого совпадения (этап 2).

    Роль:
        Показывает пару «товар из листа» — «кандидат из поставки»
        и процент схожести. Пользователь подтверждает или отклоняет.
        Результат — строка "confirmed" или "rejected".
    """

    def __init__(self, parent, supply_item: dict, candidate_item: dict,
                 similarity_score: float, total_remaining: int):
        """Конструктор.

        Вход:
            parent — родитель.
            supply_item — {'name': ..., 'count': ...}.
            candidate_item — {'name': ..., 'count': ...}.
            similarity_score — float, схожесть 0..1.
            total_remaining — сколько товаров осталось на этапе.

        Роль: строит раскладку, сохраняет result=None.
        """
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
            default_height=450,
        )

        content_layout.addWidget(LabelFactory.create_label(
            self, "Товар из листа поставки:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, supply_item['name'],
            bg_color=(0, 0, 0, 0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {supply_item.get('count', '?')}",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))

        content_layout.addWidget(LabelFactory.create_label(
            self, "-" * 50, bg_color=(0, 0, 0, 0), text_color="#888888",
        ))

        content_layout.addWidget(LabelFactory.create_label(
            self, "Найденный кандидат в поставках:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, candidate_item['name'],
            bg_color=(0, 0, 0, 0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {candidate_item.get('count', '?')}",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))

        content_layout.addWidget(LabelFactory.create_label(
            self, f"Схожесть: {int(similarity_score * 100)}%",
            bg_color=(0, 0, 0, 0), text_color="#88dd88",
            alignment=Qt.AlignLeft,
        ))

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        confirm_btn = ButtonFactory.create_button(
            self, "Подтвердить", (70, 160, 90, 0.8), fixed_size=(150, 35),
        )
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)

        reject_btn = ButtonFactory.create_button(
            self, "Отклонить", (160, 70, 70, 0.8), fixed_size=(150, 35),
        )
        reject_btn.clicked.connect(self._on_reject)
        btn_layout.addWidget(reject_btn)
        content_layout.addLayout(btn_layout)

    def _on_confirm(self) -> None:
        """Сохраняет result="confirmed" и принимает диалог."""
        self.result = "confirmed"
        self.accept()

    def _on_reject(self) -> None:
        """Сохраняет result="rejected" и принимает диалог."""
        self.result = "rejected"
        self.accept()

    def get_result(self):
        """Возвращает "confirmed" / "rejected" / None."""
        return self.result


class ManualMatchDialog(QDialog):
    """Диалог ручного выбора кандидата (этап 3).

    Роль:
        Показывает товар из листа и список доступных кандидатов
        с поиском. Пользователь либо выбирает одного, либо
        «Пропустить», либо «Отложить» (вернуть в очередь позже).
    """

    def __init__(self, parent, supply_item: dict, candidates: list,
                 total_remaining: int):
        """Конструктор.

        Вход:
            parent — родитель.
            supply_item — {'name': ..., 'count': ...}.
            candidates — список dict {'name': ..., 'count': ...}.
            total_remaining — сколько товаров осталось в очереди.

        Роль: строит раскладку со списком кандидатов и поиском.
              self.selected_candidate и self.skip_all — результат.
        """
        super().__init__(parent)
        # REPLACE: удалены два print() из исходного compare_window.py —
        # отладочный мусор, при переносе не нужен.
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
            default_height=900,
        )

        content_layout.addWidget(LabelFactory.create_label(
            self, "Товар из листа поставки:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, supply_item['name'],
            bg_color=(0, 0, 0, 0), text_color="#ffffff", word_wrap=True,
            padding="4px", border="1px solid #5a4a5c", border_radius=3,
        ))
        content_layout.addWidget(LabelFactory.create_label(
            self, f"Количество: {supply_item.get('count', '?')}",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft,
        ))

        content_layout.addWidget(LabelFactory.create_label(
            self, "-" * 50, bg_color=(0, 0, 0, 0), text_color="#888888",
        ))

        # Поле поиска.
        search_layout = QHBoxLayout()
        search_layout.addWidget(LabelFactory.create_label(
            self, "Поиск:", bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
        ))
        self.search_edit = InputWidgetFactory.create_default_line_edit(
            self, placeholder="Введите текст для фильтрации...",
        )
        self.search_edit.textChanged.connect(self._filter_list)
        search_layout.addWidget(self.search_edit)
        content_layout.addLayout(search_layout)

        # Список кандидатов.
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

        # Кнопки.
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_select = ButtonFactory.create_button(
            self, "Выбрать", (70, 160, 90, 0.8), fixed_size=(150, 35),
        )
        self.btn_select.clicked.connect(self._on_select)
        self.btn_select.setEnabled(False)
        btn_layout.addWidget(self.btn_select)

        self.btn_skip = ButtonFactory.create_button(
            self, "Пропустить", (160, 140, 70, 0.8), fixed_size=(150, 35),
        )
        self.btn_skip.clicked.connect(self._on_skip)
        btn_layout.addWidget(self.btn_skip)

        self.btn_skip_all = ButtonFactory.create_button(
            self, "Отложить", (140, 70, 70, 0.8), fixed_size=(150, 35),
        )
        self.btn_skip_all.clicked.connect(self._on_skip_all)
        btn_layout.addWidget(self.btn_skip_all)

        content_layout.addLayout(btn_layout)

        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.repaint()
        QApplication.processEvents()

    def _populate_list(self, candidates: list) -> None:
        """Заполняет список кандидатов, сохраняя dict в UserRole."""
        self.list_widget.clear()
        for item in candidates:
            display_text = item.get('name', 'Без названия')
            if item.get('count') is not None:
                display_text += f" (Кол-во: {item['count']})"
            self.list_widget.addItem(display_text)
            self.list_widget.item(
                self.list_widget.count() - 1
            ).setData(Qt.UserRole, item)

    def _filter_list(self, text: str) -> None:
        """Скрывает элементы, не содержащие введённый текст."""
        text = text.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def _on_selection_changed(self) -> None:
        """Включает «Выбрать», если что-то выделено."""
        selected = self.list_widget.currentItem()
        self.btn_select.setEnabled(selected is not None)

    def _on_select(self) -> None:
        """Сохраняет выбранного кандидата."""
        selected = self.list_widget.currentItem()
        if selected:
            self.selected_candidate = selected.data(Qt.UserRole)
            self.accept()

    def _on_skip(self) -> None:
        """Пропустить текущего — идти дальше."""
        self.selected_candidate = None
        self.accept()

    def _on_skip_all(self) -> None:
        """Отложить — вернуть товар в очередь позже."""
        self.selected_candidate = None
        self.skip_all = True
        self.accept()

    def get_result(self):
        """Возвращает кортеж (selected_candidate | None, skip_all: bool)."""
        return self.selected_candidate, self.skip_all