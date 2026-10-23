"""
Виджет чек-листа задачи.

ChecklistWidget — список пунктов ChecklistItem с возможностью
отметки, изменения порядка, редактирования. Режимы:
    "view"  — только просмотр (клик по short → NotificationDialog).
    "edit"  — редактирование (кнопки ▲▼, ✏, + Добавить).

Роль в программе:
    Просмотр в PlannerTaskMainCommentary, редактирование в
    ChecklistDialog и inline.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QDialog

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory,
)
from ui.styles import ColorCalculator
from models.planner_task import ChecklistItem
from ui.windows.message_dialog import NotificationDialog


class ChecklistWidget(QWidget):
    """Виджет чек-листа задачи.

    Сигналы:
        changed(list, str) — список ChecklistItem и тип события:
            "toggle" / "reorder" / "add" / "edit" / "delete".
    """

    changed = Signal(list, str)

    _ICONS_DIR = Path(__file__).parent.parent / "styles" / "icons"

    def __init__(self, parent, items: list, mode: str, bg_color,
                 task_id: int = None):
        """Конструктор.

        Вход:
            parent — родитель.
            items — list[ChecklistItem].
            mode — "view" или "edit".
            bg_color — фон родителя (кортеж).
            task_id — опциональный task_id (для будущего).
        """
        super().__init__(parent)
        self._mode = mode
        self._task_id = task_id
        self._items: list = list(items)
        # REPLACE: было self.bg_color — атрибут ещё не определён.
        # Нужен параметр bg_color.
        parent_bg = bg_color if bg_color else (70, 80, 90, 0.95)
        alpha = bg_color[3] if len(bg_color) >= 4 else None
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r,
            g_fn=lambda g: g,
            b_fn=lambda b: b,
            alpha=alpha,
        )
        # Цвет элементов внутри виджета — на 20% темнее его фона.
        self._element_bg = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - 10,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b - 10,
            alpha=None,
        )
        self._arrow_bg = ColorCalculator.derive(
            self._element_bg,
            r_fn=lambda r: r+10,
            g_fn=lambda g: g+10,
            b_fn=lambda b: b+10,
            alpha=None,
        )
        self._build_ui()

    # ---------- Сборка ----------

    def _build_ui(self) -> None:
        """Строит скролл со строками и кнопку «+ Добавить»."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.setObjectName("checklist_widget_root")
        self.setStyleSheet(
            f"QWidget#checklist_widget_root {{ "
            f"background-color: "
            f"{ColorCalculator.to_str(self.bg_color)}; }}"
        )
        scroll, content_widget, self._rows_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self._element_bg, rounded=False,
            )
        )
        self._content_widget = content_widget
        solid_bg = self._element_bg
        content_widget.setAttribute(Qt.WA_StyledBackground, True)
        content_widget.bg_color = solid_bg

        # Красим только внутренний контейнер.
        # Стили QScrollArea и скроллбара заданы фабрикой ListWidgetFactory.
        content_widget.setStyleSheet(
            f"background-color: {ColorCalculator.to_str(solid_bg)};"
            f" border-radius: 6px;"
        )

        scroll.setMaximumHeight(250)
        scroll.setMinimumHeight(80)
        layout.addWidget(scroll)

        self._add_btn = ButtonFactory.create_button(
            self, "+ Добавить", self._element_bg, padding="6px 12px",
        )
        self._add_btn.clicked.connect(self._on_add)

        self._add_btn.setVisible(self._mode == "edit")
        layout.addWidget(self._add_btn, alignment=Qt.AlignHCenter)
        self._rebuild()
    # ---------- Публичный API ----------

    def get_items(self) -> list:
        """Возвращает отсортированный список (копии).

        Сортировка: невыполненные сверху, внутри — по order.
        """
        return [
            ChecklistItem(
                checked=i.checked,
                short=i.short,
                detail=i.detail,
                order=i.order,
            )
            for i in self._sorted_items()
        ]

    def set_items(self, items: list) -> None:
        """Перезаписывает список и перерисовывает."""
        self._items = list(items)
        self._rebuild()

    # ---------- Внутренние ----------

    def _sorted_items(self) -> list:
        """Сортировка: невыполненные сверху, внутри — по order."""
        return sorted(self._items, key=lambda i: (i.checked, i.order))

    def _resolve_dialog_parent(self):
        """Возвращает ближайший QDialog по цепочке parent()."""
        from PySide6.QtWidgets import QMainWindow
        w = self.parent()
        depth = 0
        while w is not None:
            if isinstance(w, QMainWindow):
                return w
            w = w.parent()
            depth += 1

    def _rebuild(self) -> None:
        """Очищает layout строк и перерисовывает."""
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        sorted_list = self._sorted_items()
        for idx, item in enumerate(sorted_list):
            row = self._make_row(item, idx, sorted_list)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch()

    def _make_row(self, item: ChecklistItem, index_in_sorted: int,
                  sorted_list: list) -> QWidget:
        """Собирает строку: ▲▼, чекбокс, short-лейбл, ✏ (edit)."""
        row = QWidget(self._content_widget)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # --- Колонка ▲▼ ---
        arrows = QWidget(row)
        arrows.setFixedWidth(18)
        arrows_layout = QVBoxLayout(arrows)
        arrows_layout.setContentsMargins(0, 0, 0, 0)
        arrows_layout.setSpacing(0)
        arrows_layout.setAlignment(Qt.AlignVCenter)

        up_btn = ButtonFactory.create_button(
            arrows, "",
            bg_color=self._arrow_bg,
            fixed_size=(14, 14), padding="0px",
            icon_path=(self._ICONS_DIR / "arrow_up.svg").as_posix(),
            icon_size=(16, 16),
        )
        up_btn.clicked.connect(
            lambda checked=False, i=item: self._on_move_up(i)
        )
        if (index_in_sorted == 0
                or sorted_list[index_in_sorted - 1].checked != item.checked):
            up_btn.setEnabled(False)
        arrows_layout.addWidget(up_btn)

        down_btn = ButtonFactory.create_button(
            arrows, "",
            bg_color=self._arrow_bg,
            fixed_size=(14, 14), padding="0px",
            icon_path=(self._ICONS_DIR / "arrow_down.svg").as_posix(),
            icon_size=(16, 16),
        )
        down_btn.clicked.connect(
            lambda checked=False, i=item: self._on_move_down(i)
        )
        if (index_in_sorted == len(sorted_list) - 1
                or sorted_list[index_in_sorted + 1].checked != item.checked):
            down_btn.setEnabled(False)
        arrows_layout.addWidget(down_btn)

        # --- Чекбокс ---
        cb = InputWidgetFactory.create_checkbox(
            row, text="", checked=item.checked,
            bg_color=self._element_bg,
        )
        if self._mode == "view":
            # В архиве чекбокс только для вида — игнорируем клики
            cb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        else:
            cb.clicked.connect(
                lambda checked, i=item: self._on_toggle(i, checked)
            )
        row_layout.addWidget(cb)

        # --- Short-лейбл (всегда кликабельный) ---
        lbl = LabelFactory.create_label(
            row, item.short,
            bg_color=(0, 0, 0, 0),
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            word_wrap=True,
            clickable=True,
            on_click=lambda i=item: self._on_show_detail(i),
        )
        row_layout.addWidget(lbl, 1)

        # --- ✏ — только в edit ---
        if self._mode == "edit":
            edit_btn = ButtonFactory.create_edit_button(
                row,
                callback=lambda checked=False, i=item: self._on_edit(i),
            )
            row_layout.addWidget(edit_btn)

        arrows.setVisible(self._mode == "edit")
        row_layout.addWidget(arrows)
        row_layout.addStretch()
        return row

    # ---------- Слоты ----------

    def _on_toggle(self, item: ChecklistItem, checked: bool) -> None:
        """Отметка чекбокса. Перерисовка + сигнал."""
        item.checked = checked
        self._rebuild()
        self.changed.emit(self.get_items(), "toggle")

    def _on_move_up(self, item: ChecklistItem) -> None:
        """Обмен order с предыдущим в группе (тот же checked)."""
        sorted_list = self._sorted_items()
        idx = sorted_list.index(item)
        if idx <= 0:
            return
        prev = sorted_list[idx - 1]
        if prev.checked != item.checked:
            return
        item.order, prev.order = prev.order, item.order
        self._rebuild()
        self.changed.emit(self.get_items(), "reorder")

    def _on_move_down(self, item: ChecklistItem) -> None:
        """Обмен order со следующим в группе."""
        sorted_list = self._sorted_items()
        idx = sorted_list.index(item)
        if idx >= len(sorted_list) - 1:
            return
        nxt = sorted_list[idx + 1]
        if nxt.checked != item.checked:
            return
        item.order, nxt.order = nxt.order, item.order
        self._rebuild()
        self.changed.emit(self.get_items(), "reorder")

    def _on_add(self) -> None:
        """Открывает ChecklistItemDialog для нового пункта.

        REPLACE: exec() → open() + finished. Вложенный exec()
        внутри WindowModal родителя зависает. open() не создаёт
        вложенный event loop.
        """
        from ui.windows.planner_checklist_dialogs import ChecklistItemDialog

        dialog = ChecklistItemDialog(parent=self.window(), item=None)
        dialog.finished.connect(
            lambda code, d=dialog: self._on_add_finished(d, code)
        )
        dialog.show()

    def _on_add_finished(self, dialog, code) -> None:
        """Обработка закрытия ChecklistItemDialog (создание)."""
        if code != QDialog.Accepted:
            return
        result = dialog.get_result()
        if not isinstance(result, dict):
            return
        new_order = max((i.order for i in self._items), default=-1) + 1
        self._items.append(ChecklistItem(
            checked=False,
            short=result["short"],
            detail=result["detail"],
            order=new_order,
        ))
        self._rebuild()
        self.changed.emit(self.get_items(), "add")

    def _on_edit(self, item: ChecklistItem) -> None:
        """Открывает ChecklistItemDialog для правки / удаления.

        REPLACE: exec() → open() + finished.
        """
        from ui.windows.planner_checklist_dialogs import ChecklistItemDialog
        dialog = ChecklistItemDialog(parent=self.window(), item=item)
        dialog.finished.connect(
            lambda code, d=dialog, i=item: self._on_edit_finished(d, i, code)
        )
        dialog.show()
        from PySide6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, dialog.raise_)
        _QTimer.singleShot(0, dialog.activateWindow)


    def _on_edit_finished(self, dialog, item, code) -> None:
        """Обработка закрытия ChecklistItemDialog (правка/удаление)."""
        if code != QDialog.Accepted:
            return
        result = dialog.get_result()
        if result == "deleted":
            self._items.remove(item)
            self._rebuild()
            self.changed.emit(self.get_items(), "delete")
            return
        if isinstance(result, dict):
            item.short = result["short"]
            item.detail = result["detail"]
            self._rebuild()
            self.changed.emit(self.get_items(), "edit")

    def _on_show_detail(self, item: ChecklistItem) -> None:
        """Показывает детали при клике на short (в любом режиме)."""
        text = item.detail.strip() or "Подробное описание отсутствует."
        NotificationDialog.notify(
            self.window(),
            text,
            title_text=item.short,
            bg_color=self.bg_color,
        )