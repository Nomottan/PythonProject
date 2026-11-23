"""
Композитный выпадающий список (DropdownComposite).

Содержит DropdownComposite — виджет, состоящий из кнопки-триггера
и выпадающей панели (popup), которая позиционируется как отдельное
окно (Qt.Popup) и не обрезается границами родителя. Ограничение
позиции происходит только по границам экрана.
"""

from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QTimer, QStringListModel
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QApplication,
    QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect, QLayoutItem,
    QLineEdit, QCompleter,
)

from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory, ListWidgetFactory,
    InputWidgetFactory,
)
from ui.styles import (
    WidgetStyle, ColorCalculator, IconRenderer,
    GeometryCalculator, BackgroundResolver,
)


class _DropdownRow(QWidget):
    """Строка выпадающего списка с поддержкой hover и press."""

    def __init__(self, parent, bg_color):
        super().__init__(parent)
        self.bg_color = bg_color
        self._bg_color = bg_color
        self._hover = False
        self._pressed = False
        self.is_selected = False
        self.setAttribute(Qt.WA_StyledBackground, True)

    def enterEvent(self, e):
        self._hover = True
        self._update_style()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = False
        self._update_style()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = True
            self._update_style()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = False
            self._update_style()
        super().mouseReleaseEvent(e)

    def _update_style(self):
        if self._pressed:
            bg = ColorCalculator.pressed(self._bg_color)
        elif self._hover or self.is_selected:
            bg = ColorCalculator.hover(self._bg_color)
        else:
            bg = (0, 0, 0, 0)
        self.setStyleSheet(
            f"background-color: {ColorCalculator.to_str(bg)}; border-radius: 4px;"
        )


class DropdownComposite(QWidget):
    """Композитный выпадающий список.

    Представляет собой кнопку-триггер и выпадающую панель (popup),
    которая позиционируется как отдельное окно (Qt.Popup).
    """

    selection_changed = Signal(object)
    item_clicked = Signal(int)
    opened = Signal()
    edit_text_changed = Signal(str)
    editing_finished = Signal()

    _DEFAULT_SETTINGS = {
        "multi_select": False,
        "close_on_select": None,
        "placeholder": "Выберите...",
        "auto_update_button": True,
        "allow_multiple_open": False,
        "close_on_scroll": True,
        "select_on_interactive_click": False,
        "popup_bg_color": None,
        "popup_border": "none",
        "popup_border_radius": 6,
        "popup_shadow": False,
        "max_length": None,
        "row_style": "default",
        "arrow_position": "right",
        "auto_select_first": True,
        "item_separators": False,
        "trigger_items": None,
        "layout_direction": "vertical",
        "preferred_direction": "auto",
        "sync_checkboxes": False,
        "is_category": False,
        "debug": False,
        "editable": False,
        "completer_case_sensitive": False,
        "completer_filter_mode": "contains",
    }

    def __init__(self, parent, config: dict = None, **kwargs):
        """Конструктор выпадающего списка."""
        super().__init__(parent)

        if config is None:
            config = {}

        self.settings = self._DEFAULT_SETTINGS.copy()
        self.settings.update(kwargs)
        self.settings.update(config.get("settings", {}))

        # Поднимаемся по родителям, чтобы найти main_config и взять флаг debug
        p = self.parent()
        while p is not None:
            if hasattr(p, "main_config"):
                if p.main_config.get("debug", False):
                    self.settings["debug"] = True
                break
            p = p.parent()

        if self.settings["close_on_select"] is None:
            self.settings["close_on_select"] = not self.settings["multi_select"]

        self._rows = []
        self._row_datas = []
        self._row_texts = []
        self._row_disabled = []
        self._row_is_separator = []

        self._current_index = -1
        self._selected_indices = set()
        self._popup = None
        self._popup_direction = "down"

        if self.settings["popup_bg_color"] is None:
            parent_bg = BackgroundResolver.resolve_parent_bg(
                self.parent(), None,
            )
            if parent_bg is None:
                parent_bg = BackgroundResolver.resolve_bg_color(self, None)
            if parent_bg is None:
                parent_bg = (63, 63, 63, 1.0)
            self._popup_bg = ColorCalculator.element_bg_for(parent_bg)
        else:
            self._popup_bg = self.settings["popup_bg_color"]



        # Сборка триггера (ВСЕГДА)
        self._build_trigger()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._trigger)

    # ---------- Сборка триггера ----------

    def _build_trigger(self) -> None:
        """Собирает кнопку-триггер (стандартную или кастомную)."""
        trigger_widgets = []
        stretch_factors = []

        if self.settings["trigger_items"] is not None:
            for item in self.settings["trigger_items"]:
                match item:
                    case {"widget": w}:
                        trigger_widgets.append(w)
                        stretch_factors.append(0)
                    case {"label": text}:
                        lbl = LabelFactory.create_label(
                            None, text,
                            bg_color=(0, 0, 0, 0),
                            text_color=ColorCalculator.text_for(self._popup_bg),
                        )
                        trigger_widgets.append(lbl)
                        stretch_factors.append(1)
                    case {"button": btn_text, **kw}:
                        btn = ButtonFactory.create_button(None, btn_text, bg_color=self._popup_bg)
                        trigger_widgets.append(btn)
                        stretch_factors.append(0)
                    case {"spacer": True}:
                        trigger_widgets.append(
                            QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
                        )
                        stretch_factors.append(0)
        else:
            if self.settings.get("editable", False):
                _trigger_text_color = ColorCalculator.text_for(self._popup_bg)
                self._text_label = InputWidgetFactory.create_line_edit(
                    None,
                    text="",
                    placeholder=self.settings["placeholder"],
                    bg_color=(0, 0, 0, 0),
                    text_color=_trigger_text_color,
                    border="none",
                    border_radius=0,
                    padding="0px",
                )
                self._text_label._style_kwargs = {
                    "bg_color": (0, 0, 0, 0),
                    "text_color": _trigger_text_color,
                    "border": "none",
                    "border_radius": 0,
                    "padding": "0px",
                    "font_size": None,
                    "font_family": None,
                    "extra_style": "",
                }
                self._text_label.textEdited.connect(self.edit_text_changed.emit)
                self._text_label.editingFinished.connect(self.editing_finished.emit)
            else:
                self._text_label = LabelFactory.create_label(
                    None, text=self.settings["placeholder"],
                    bg_color=(0, 0, 0, 0),
                    text_color=ColorCalculator.text_for(self._popup_bg),
                )
                self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            trigger_widgets.append(self._text_label)
            stretch_factors.append(1)

        arrow_bg = ColorCalculator.element_bg_for(self._popup_bg)
        self._arrow_btn = ButtonFactory.create_button(
            None, text="", bg_color=arrow_bg,
            fixed_size=(24, 24), padding="0px",
            border_radius=max(2, self.settings["popup_border_radius"] - 2)
        )
        self._arrow_btn.clicked.connect(self.toggle)

        if self.settings.get("arrow_position") == "left":
            trigger_widgets.insert(0, self._arrow_btn)
            stretch_factors.insert(0, 0)
        else:
            trigger_widgets.append(self._arrow_btn)
            stretch_factors.append(0)

        self._trigger = LayoutFactory.create_row(
            self, *trigger_widgets, spacing=4, margins=(8, 4, 4, 4),
            stretch_factors=stretch_factors
        )
        self._trigger.setObjectName(f"dropdown_trigger_{id(self)}")
        WidgetStyle.apply_panel(
            self._trigger, self._popup_bg,
            border_radius=self.settings["popup_border_radius"]
        )

        def trigger_mouse_press(event):
            if event.button() == Qt.LeftButton:
                self.toggle()
            else:
                event.ignore()

        self._trigger.mousePressEvent = trigger_mouse_press

        self._update_button_icon()

    def _update_trigger_style(self):
        """Меняет фон триггера при открытии/закрытии."""
        is_open = self._popup and self._popup.isVisible()
        bg = self._popup_bg

        extra = ""
        if is_open:
            sep_color = ColorCalculator.to_str(ColorCalculator.hover(self._popup_bg))
            extra = (
                f"border-bottom: 1px solid {sep_color};"
                "border-bottom-left-radius: 0px;"
                "border-bottom-right-radius: 0px;"
            )

        WidgetStyle.apply_panel(
            self._trigger, bg,
            border=None,
            border_radius=self.settings["popup_border_radius"],
            extra_style=extra
        )

    def _update_button_icon(self):
        """Обновляет иконку стрелки на кнопке."""
        is_open = self._popup and self._popup.isVisible()
        pos = self.settings.get("arrow_position", "right")

        if is_open:
            direction = self._popup_direction
        else:
            direction = "left" if pos == "right" else "right"

        self._arrow_btn.setIcon(
            IconRenderer.make_arrow(direction, self._arrow_btn, bg_color=self._popup_bg)
        )


    # ---------- Публичный API ----------

    def add_item(self, config: dict) -> int:
        """Добавляет новую строку в выпадающий список."""

        index = len(self._rows)
        row_widget, data, text, is_sep = self._build_row(config, index)
        if row_widget is None:
            return -1

        self._rows.append(row_widget)
        self._row_datas.append(data)
        self._row_texts.append(text)
        self._row_disabled.append(config.get("disabled", False))
        self._row_is_separator.append(is_sep)

        if self.settings.get("editable", False):
            self._sync_completer()

        if (index == 0
                and self.settings["auto_select_first"]
                and not self.settings["multi_select"]
                and not self._row_disabled[index]):
            self.set_current_index(0)
        else:
            self._update_button_text()

        return index

    def add_separator(self) -> int:
        """Добавляет горизонтальный разделитель в список вручную."""
        index = len(self._rows)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        WidgetStyle.apply_dropdown_separator(line, self._popup_bg)

        self._rows.append(line)
        self._row_datas.append(None)
        self._row_texts.append("")
        self._row_disabled.append(True)
        self._row_is_separator.append(True)



        return index

    def clear_items(self) -> None:
        """Очищает список полностью."""


        if self._popup:
            self._popup.deleteLater()
            self._popup = None
        self._rows.clear()
        self._row_datas.clear()
        self._row_texts.clear()
        self._row_disabled.clear()
        self._row_is_separator.clear()
        self._selected_indices.clear()
        self._current_index = -1
        if self.settings["auto_update_button"] and hasattr(self, "_text_label"):
            if self.settings.get("editable", False) and isinstance(self._text_label, QLineEdit):
                self._text_label.setText("")
            else:
                self._text_label.setText(self.settings["placeholder"])
        if self.settings.get("editable", False):
            self._sync_completer()

    def set_current_index(self, index: int) -> None:
        """Программный выбор строки по её индексу."""


        if 0 <= index < len(self._rows) and not self._row_disabled[index] and not self._row_is_separator[index]:
            if not self.settings["multi_select"]:
                self._selected_indices.clear()
            self._selected_indices.add(index)
            self._current_index = index
            self._update_row_styles()
            if self.settings["auto_update_button"]:
                self._update_button_text()
            self._emit_selection()


    def current_index(self) -> int:
        """Возвращает индекс текущей выбранной строки."""
        result = self._current_index
        return result

    def set_current_data(self, data) -> None:
        """Программный выбор строки по связанным с ней данным."""

        for i, d in enumerate(self._row_datas):
            if d == data:
                self.set_current_index(i)
                return

    def _get_child_dropdowns(self) -> list:
        """Возвращает список вложенных DropdownComposite."""
        children = []
        for row in self._rows:
            for child in row.findChildren(DropdownComposite):
                if child is not self and child not in children:
                    children.append(child)
        return children

    def select_all(self) -> None:
        """Выбирает все элементы. Только для multi_select=True."""
        if not self.settings["multi_select"]:
            return

        self._selected_indices.clear()
        for i in range(len(self._rows)):
            if not self._row_disabled[i] and not self._row_is_separator[i]:
                self._selected_indices.add(i)

        if self._selected_indices:
            self._current_index = list(self._selected_indices)[-1]

        self._update_row_styles()

        if self.settings.get("is_category") and hasattr(self, "_child_dropdowns"):
            for child in self._child_dropdowns:
                child.select_all()

        if self.settings["auto_update_button"]:
            self._update_button_text()
        self._emit_selection()

    def clear_selection(self) -> None:
        """Снимает выбор со всех элементов."""
        if not self.settings["multi_select"]:
            return

        self._selected_indices.clear()
        self._current_index = -1
        self._update_row_styles()

        if self.settings.get("is_category") and hasattr(self, "_child_dropdowns"):
            for child in self._child_dropdowns:
                child.clear_selection()

        if self.settings["auto_update_button"]:
            self._update_button_text()
        self._emit_selection()

    def current_data(self):
        """Возвращает данные выбранных строк."""
        if self.settings["multi_select"]:
            result = [self._row_datas[i] for i in sorted(self._selected_indices)]
        elif self._current_index >= 0:
            result = self._row_datas[self._current_index]
        else:
            result = None

        return result

    def set_placeholder(self, text: str) -> None:
        """Динамически меняет placeholder."""
        self.settings["placeholder"] = text
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(text)
        elif not self._selected_indices and self.settings["auto_update_button"] and hasattr(self, "_text_label"):
            self._text_label.setText(text)

    def open(self) -> None:
        """Открывает выпадающий список."""

        if not self._rows:
            return

        if self._popup is None:
            self._build_popup()

        self._position_popup()
        self._update_row_styles()
        self._popup.show()
        self.opened.emit()
        self._update_button_icon()
        self._update_trigger_style()

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def close(self) -> None:
        """Закрывает выпадающий список."""
        # Принудительно закрываем дочерние попапы
        if hasattr(self, "_child_dropdowns"):
            for child in self._child_dropdowns:
                child.close()

        if self._popup and self._popup.isVisible():
            self._popup.hide()
            self._update_button_icon()
            self._update_trigger_style()
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def toggle(self) -> None:
        """Переключает состояние списка."""
        if self._popup and self._popup.isVisible():
            self.close()
        else:
            # Задержка, чтобы Qt.Popup успел обработать текущий клик
            QTimer.singleShot(0, self.open)

    # ---------- Editable-режим (ленивая настройка) ----------

    def lineEdit(self):
        """Возвращает QLineEdit editable-режима или None.

        Выход: QLineEdit, если editable=True и триггер собран как
               стандартный; иначе None.

        Роль:
            Аналог QComboBox.lineEdit(). Нужен для set_error_state
            и для ручной работы с полем ввода из вызывающего кода.
        """
        if not self.settings.get("editable", False):
            return None
        if not hasattr(self, "_text_label"):
            return None
        if isinstance(self._text_label, QLineEdit):
            return self._text_label
        return None

    def completer(self):
        """Возвращает QCompleter editable-режима или None.

        Выход: QCompleter, если editable=True и completer уже создан
               (после первого add_item); иначе None.

        Роль:
            Аналог QComboBox.completer(). Ленивое создание: пока не
            добавлен ни один элемент, completer ещё не существует.
        """
        return getattr(self, "_completer", None)

    def currentText(self) -> str:
        """Возвращает текущий текст поля (editable) или выбранной строки.

        Выход: строка. Пустая, если ничего не выбрано и поле пустое.

        Роль:
            Аналог QComboBox.currentText(). В editable-режиме
            читает QLineEdit (включая ручной ввод), иначе — текст
            выбранной строки по _current_index.
        """
        line_edit = self.lineEdit()
        if line_edit is not None:
            return line_edit.text()
        if 0 <= self._current_index < len(self._row_texts):
            return self._row_texts[self._current_index]
        return ""

    def setCurrentText(self, text: str) -> None:
        """Устанавливает текст поля (editable) или выбирает строку по тексту.

        Вход: text — строка.

        Роль:
            Аналог QComboBox.setCurrentText(). В editable-режиме
            пишет текст в QLineEdit (без эмита edit_text_changed,
            потому что QLineEdit.setText не даёт textEdited).
            Если text совпал с одной из строк — выделяет её через
            set_current_index (эмитит selection_changed). Пустая
            строка сбрасывает выбор (_current_index = -1).
        """
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setText(text)

        if text == "":
            self._selected_indices.clear()
            self._current_index = -1
            self._update_row_styles()
            return

        if text in self._row_texts:
            idx = self._row_texts.index(text)
            self.set_current_index(idx)

    def set_error_state(self, is_error: bool) -> None:
        """Подсвечивает поле ввода (editable) при ошибке.

        Вход: is_error — bool.

        Роль:
            В editable-режиме вызывает InputWidgetFactory.set_error_state
            для QLineEdit. В остальных режимах — no-op.
        """
        line_edit = self.lineEdit()
        if line_edit is None:
            return
        InputWidgetFactory.set_error_state(line_edit, is_error)

    def _sync_completer(self) -> None:
        """Лениво создаёт и обновляет completer для editable-режима.

        Роль:
            Вызывается при изменении списка (add_item, clear_items).
            При первом вызове создаёт QCompleter, привязывает его к
            QLineEdit и настраивает caseSensitivity / filterMode /
            completionMode по settings. При последующих — только
            обновляет список строк модели completer'а.
            Если editable=False или _text_label не QLineEdit — no-op.
        """
        line_edit = self.lineEdit()
        if line_edit is None:
            return  # QLineEdit ещё не создан

        completer = getattr(self, "_completer", None)
        if completer is None:
            completer = QCompleter(line_edit)
            if self.settings.get("completer_case_sensitive", False):
                completer.setCaseSensitivity(Qt.CaseSensitive)
            else:
                completer.setCaseSensitivity(Qt.CaseInsensitive)

            mode = self.settings.get("completer_filter_mode", "contains")
            _mode_map = {"starts_with": Qt.MatchStartsWith,
                         "exact": Qt.MatchExactly}
            completer.setFilterMode(_mode_map.get(mode, Qt.MatchContains))

            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.activated.connect(self._on_completer_activated)
            line_edit.setCompleter(completer)
            self._completer = completer
            self._completer_model = QStringListModel()
            completer.setModel(self._completer_model)

        self._completer_model.setStringList(list(self._row_texts))

    def _on_completer_activated(self, text: str) -> None:
        """Слот completer.activated — выбирает строку по тексту из completer.

        Вход: text — выбранная в completer строка.

        Роль:
            Синхронизирует выбор из completer с внутренним состоянием
            (_current_index, _selected_indices, стили строк). Эмитит
            editing_finished, чтобы вызывающий код (например,
            AddressDialog) среагировал так же, как на потерю фокуса.
        """
        if text not in self._row_texts:
            return
        idx = self._row_texts.index(text)
        self.set_current_index(idx)
        self.editing_finished.emit()
        if self.settings.get("close_on_select", True) and self._popup and self._popup.isVisible():
            self.close()
    # ---------- Внутренние методы ----------

    def _build_row(self, config: dict, index: int) -> tuple:
        """Собирает одну строку для popup."""
        is_separator = config.get("separator", False)
        if is_separator:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            WidgetStyle.apply_dropdown_separator(line, self._popup_bg)
            return line, None, "", True

        items = config.get("items")
        if items is None:
            items = [config]

        widgets = []
        first_text = ""
        row_data = config.get("data")

        for item in items:
            match item:
                case {"widget": w}:
                    if not hasattr(self, "_child_dropdowns"):
                        self._child_dropdowns = []

                    # Если это сам дропдаун
                    if isinstance(w, DropdownComposite):
                        if w not in self._child_dropdowns:
                            self._child_dropdowns.append(w)
                    # Если это контейнер (например, _categories_row), ищем дропдауны внутри него
                    elif isinstance(w, QWidget):
                        for child in w.findChildren(DropdownComposite):
                            if child not in self._child_dropdowns:
                                self._child_dropdowns.append(child)

                    widgets.append(w)
                case {"label": lbl_text}:
                    if self.settings["row_style"] == "chip":
                        lbl = LabelFactory.create_label(None, lbl_text, bg_color=(0, 0, 0, 0))
                        WidgetStyle.apply_dropdown_chip(lbl, self._popup_bg)
                    else:
                        text_color = ColorCalculator.text_for(self._popup_bg)
                        lbl = LabelFactory.create_label(
                            None, lbl_text, bg_color=(0, 0, 0, 0),
                            text_color=text_color, padding="4px 8px", border_radius=0
                        )
                    lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    widgets.append(lbl)
                    if not first_text:
                        first_text = lbl_text
                case {"button": btn_text, **kwargs}:
                    btn = ButtonFactory.create_button(
                        None, btn_text, bg_color=self._popup_bg,
                        icon_type=kwargs.get("icon_type")
                    )
                    if "callback" in kwargs:
                        btn.clicked.connect(kwargs["callback"])
                    widgets.append(btn)
                    if not first_text:
                        first_text = btn_text
                case {"spacer": True}:
                    widgets.append(QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))

        row = _DropdownRow(None, self._popup_bg)
        row_layout = QHBoxLayout(row)
        if self.settings.get("layout_direction") == "vertical":
            row_layout.setContentsMargins(0, 2, 0, 2)  # <--- Возвращаем вертикальные отступы
        else:
            row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)
        row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for w in widgets:
            if isinstance(w, QWidget):
                row_layout.addWidget(w)
            elif isinstance(w, QLayoutItem):
                row_layout.addItem(w)

        if config.get("disabled", False):
            row.setEnabled(False)

        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        row_checkboxes = []
        if self.settings.get("sync_checkboxes", False):
            from ui.widgets.checkbox import CheckBox
            row_checkboxes = row.findChildren(CheckBox)
            for cb in row_checkboxes:
                cb.toggled.connect(
                    lambda checked, idx=index: self._on_row_checkbox_toggled(idx, checked)
                )

        original_mouse_press = row.mousePressEvent

        def mouse_press(event, idx=index):
            if event.button() == Qt.LeftButton:
                if self.settings.get("sync_checkboxes", False) and row_checkboxes:
                    # Проверяем, не кликнули ли мы прямо по чекбоксу
                    from ui.widgets.checkbox import CheckBox
                    child = row.childAt(event.position().toPoint())
                    while child:
                        if isinstance(child, CheckBox):
                            return  # Чекбокс сам обработает клик
                        child = child.parent()
                    # Если клик по пустому месту строки — программно нажимаем чекбокс
                    row_checkboxes[0].toggle()
                    return
                self.item_clicked.emit(idx)
                if self.settings["select_on_interactive_click"] or not config.get("interactive", False):
                    self.set_current_index(idx)
                    if self.settings["close_on_select"]:
                        self.close()
            original_mouse_press(event)

        row.mousePressEvent = mouse_press

        return row, row_data, first_text, False

    def _build_popup(self) -> None:
        """Создает и собирает выпадающее окно."""
        self._popup = QWidget(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._popup.setAttribute(Qt.WA_TranslucentBackground)
        self._popup.setAttribute(Qt.WA_DeleteOnClose, False)

        container = QWidget(self._popup)
        container.setObjectName("dropdown_popup_container")
        container.mousePressEvent = lambda e: e.accept()
        self._popup.mousePressEvent = lambda e: e.accept()

        WidgetStyle.apply_panel(
            container, self._popup_bg,
            border_radius=self.settings["popup_border_radius"],
            border=self.settings["popup_border"]
        )

        if self.settings["popup_shadow"]:
            shadow = QGraphicsDropShadowEffect(container)
            shadow.setBlurRadius(10)
            shadow.setColor(QColor(0, 0, 0, 100))
            shadow.setOffset(0, 4)
            container.setGraphicsEffect(shadow)

        popup_layout = QVBoxLayout(self._popup)
        margin = 10 if self.settings["popup_shadow"] else 0
        popup_layout.setContentsMargins(margin, margin, margin, margin)
        popup_layout.addWidget(container)

        if self.settings.get("layout_direction") == "horizontal":
            from PySide6.QtWidgets import QScrollArea
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            # Отключаем вертикальный скролл, чтобы элементы не ездили вверх-вниз
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setStyleSheet("background: transparent;")
            content_widget = QWidget()
            content_widget.setStyleSheet("background: transparent;")
            scroll_layout = QHBoxLayout(content_widget)
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setSpacing(4)
            scroll_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            scroll.setWidget(content_widget)
            self._scroll = scroll
        else:
            scroll, content_widget, scroll_layout = ListWidgetFactory.create_scroll_container(
                container, bg_color=self._popup_bg, rounded=False
            )
            self._scroll = scroll

        radius = self.settings["popup_border_radius"]
        scroll.setStyleSheet(f"QScrollArea {{ border-radius: {radius}px; background: transparent; border: none; }}")
        scroll.viewport().setStyleSheet(f"border-radius: {radius}px; background: transparent;")
        content_widget.setStyleSheet(f"border-radius: {radius}px; background: transparent;")

        for i, row in enumerate(self._rows):
            row.setParent(content_widget)
            scroll_layout.addWidget(row)

            if self.settings.get("item_separators", False) and i < len(self._rows) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                WidgetStyle.apply_dropdown_separator(line, self._popup_bg)
                line.setParent(content_widget)
                scroll_layout.addWidget(line)

        inner_layout = QVBoxLayout(container)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.addWidget(scroll)

    def _position_popup(self) -> None:
        """Позиционирует popup с учетом экрана."""
        if not self._popup:
            return

        debug = self.settings.get("debug", False)
        prefix = "[DEBUG/ui.widgets.dropdown_composite/DropdownComposite/_position_popup]"

        # Сбрасываем все предыдущие ограничения
        self._scroll.setMaximumHeight(16777215)
        self._scroll.setMaximumWidth(16777215)
        self._popup.setMinimumSize(0, 0)
        self._popup.setMaximumSize(16777215, 16777215)

        # 1. Получаем координаты триггера и вычисляем динамический max_length
        trigger_global = self._trigger.mapToGlobal(QPoint(0, 0))
        window = self.window()
        win_rect = window.geometry() if window else None
        preferred_dir = self.settings.get("preferred_direction", "auto")

        max_len = GeometryCalculator.calculate_max_popup_length(
            trigger_global,
            self._trigger.width(),
            self._trigger.height(),
            preferred_dir,
            win_rect,
            self.settings.get("max_length")
        )

        if self.settings.get("layout_direction") == "vertical":
            w = max(self._trigger.width(), 100)
            self._popup.setFixedWidth(w)
            self._scroll.setMaximumHeight(max_len)
            self._scroll.setMinimumHeight(0)
            self._scroll.setFixedWidth(w)  # <--- фиксируем ширину скролла тоже

            # Вычисляем реальную высоту контента
            scroll_widget = self._scroll.widget()
            if scroll_widget and scroll_widget.layout():
                scroll_widget.layout().activate()
                content_h = scroll_widget.layout().sizeHint().height()
            else:
                content_h = 100

            final_h = min(content_h, max_len)
            self._scroll.setFixedHeight(final_h)

        else:
            # Горизонтальный режим
            scroll_widget = self._scroll.widget()
            if scroll_widget:
                content_width = scroll_widget.sizeHint().width()
            else:
                content_width = 400

            # 1. Вычисляем ширину попапа
            w = min(content_width, max_len)

            # 2. Вычисляем высоту с учетом скроллбара
            will_scroll = content_width > w
            hbar_h = 0
            if will_scroll:
                hbar_h = self._scroll.horizontalScrollBar().sizeHint().height()

            final_h = self._trigger.height() + hbar_h
            self._scroll.setFixedHeight(final_h)

            # 3. ФИКСИРУЕМ ширину ДО adjustSize, чтобы он не растянул попап
            self._popup.setFixedWidth(w)
            self._scroll.setFixedWidth(w)

        self._popup.layout().activate()
        self._popup.adjustSize()

        h = self._popup.height()  # <--- убрали перезапись w

        margin = 10 if self.settings["popup_shadow"] else 0
        self._popup.setFixedSize(w, final_h + margin * 2)
        h = self._popup.height()

        trigger_global = self._trigger.mapToGlobal(QPoint(0, 0))
        # 4. Вычисляем координаты и направление
        x, y, direction = GeometryCalculator.calculate_popup_position(
            trigger_global, w, h, self._trigger.height(), self._trigger.width(),
            preferred_dir=self.settings.get("preferred_direction", "auto")
        )
        self._popup_direction = direction

        # 5. Применяем тень
        margin = 10 if self.settings["popup_shadow"] else 0
        final_x = x - margin
        final_y = y - margin


        # 6. Применяем позицию
        self._popup.move(final_x, final_y)

    def _on_row_checkbox_toggled(self, index, checked):
        """Слот для синхронизации чекбоксов в строке."""


        if self.settings["multi_select"]:
            if checked:
                self._selected_indices.add(index)
            else:
                self._selected_indices.discard(index)
            self._current_index = index if checked else -1
        else:
            if checked:
                self._selected_indices = {index}
                self._current_index = index
            else:
                self._selected_indices.clear()
                self._current_index = -1

        self._update_row_styles()
        self._update_button_text()
        self._emit_selection()

    def _update_button_text(self) -> None:
        if not hasattr(self, "_text_label"):
            return

        is_editable = (
            self.settings.get("editable", False)
            and isinstance(self._text_label, QLineEdit)
        )

        if not self._selected_indices:
            if is_editable:
                # В editable-режиме placeholder — это placeholderText QLineEdit.
                # Текст не трогаем: пользователь мог ввести его вручную.
                return
            if self.settings.get("placeholder") is not None:
                self._text_label.setText(self.settings["placeholder"])
            elif self._rows:
                self._text_label.setText(self._row_texts[0])
            else:
                self._text_label.setText("")
            return

        if self.settings["multi_select"]:
            self._text_label.setText(f"Выбрано: {len(self._selected_indices)}")
        else:
            idx = self._current_index
            text = self._row_texts[idx] if idx >= 0 and idx < len(self._row_texts) else ""
            if is_editable:
                if text:
                    self._text_label.setText(text)
                return
            self._text_label.setText(text if text else self.settings["placeholder"])

    def _update_row_styles(self) -> None:
        for i, row in enumerate(self._rows):
            if self._row_is_separator[i]:
                continue
            if isinstance(row, _DropdownRow):
                row.is_selected = (i in self._selected_indices)
                row._update_style()

                if self.settings.get("sync_checkboxes", False):
                    from ui.widgets.checkbox import CheckBox
                    checkboxes = row.findChildren(CheckBox)
                    for cb in checkboxes:
                        cb.blockSignals(True)
                        cb.setChecked(i in self._selected_indices)
                        cb.blockSignals(False)

    def _on_scroll(self, value: int = 0) -> None:
        """Закрывает вложенные списки при скролле."""
        if self.settings.get("close_on_scroll", True):
            if hasattr(self, "_child_dropdowns"):
                for child in self._child_dropdowns:
                    child.close()

    def _emit_selection(self) -> None:
        """Генерирует сигнал об изменении выбора."""
        data = self.current_data()
        self.selection_changed.emit(data)

    def eventFilter(self, obj, event) -> bool:
        """Закрывает popup при клике вне его границ."""
        if event.type() == QEvent.MouseButtonPress and self._popup and self._popup.isVisible():
            pos = event.globalPosition().toPoint()

            # 1. Клик внутри текущего popup — не закрываем
            if self._popup.geometry().contains(pos):
                return False

            # 2. Клик внутри дочерних попапов — не закрываем мастер
            if hasattr(self, "_child_dropdowns"):
                for child_dd in self._child_dropdowns:
                    if child_dd._popup and child_dd._popup.isVisible() and child_dd._popup.geometry().contains(pos):
                        return False

            # 3. Клик по кнопке-триггеру
            if self._trigger.rect().contains(self._trigger.mapFromGlobal(pos)):
                from ui.widgets.checkbox import CheckBox
                clicked_widget = self._trigger.childAt(self._trigger.mapFromGlobal(pos))
                while clicked_widget:
                    if isinstance(clicked_widget, CheckBox):
                        # Программно кликаем по чекбоксу и поглощаем клик.
                        # Popup останется открытым, а тристейт сработает.
                        clicked_widget._toggle()
                        return True
                    clicked_widget = clicked_widget.parent()

                # Клик по пустому месту триггера или стрелке — закрываем и поглощаем.
                # (Поглощение предотвращает вызов trigger_mouse_press, который вызвал бы мерцание).
                self.close()
                return True

            # 4. Клик вне — закрываем и НЕ ПОГЛОЩАЕМ
            self.close()
            return False

        return super().eventFilter(obj, event)