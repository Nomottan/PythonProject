"""
Панель фильтров: FilterCategory и FilterPanel.

FilterCategory — одна категория: тристейт-чекбокс, кликабельный
лейбл со счётчиком, стрелка раскрытия, список чекбоксов значений.
FilterPanel — набор категорий с мастер-кнопкой «Фильтры» и
сворачиванием по клику вне панели.

Роль в программе:
    Единая точка UI-фильтрации для окон (BrandsWindow и др.).
    Ядро фильтрации — utils/filter_utils.py. Панель только
    собирает выбор и отдаёт отфильтрованный список.
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication,
)

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory, LayoutFactory,
)
from ui.styles import ColorCalculator
from utils.filter_utils import FieldDef, FilterCore

class FilterCategory(QWidget):
    """Одна категория фильтра.

    Роль:
        Заголовок (тристейт + лейбл + стрелка) + раскрывающийся
        блок с чекбоксами значений. При изменении выбора
        эмитит selection_changed(name); FilterPanel пересобирает
        результирующий список.

    Сигналы:
        selection_changed(str) — имя категории (field_def.name).
    """

    selection_changed = Signal(str)

    _ICONS_DIR = Path(__file__).parent.parent / "styles" / "icons"

    def __init__(self, parent, field_def: FieldDef, bg_color):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            field_def — FieldDef (имя, подпись, extractor).
            bg_color — фон панели (кортеж).

        Роль: сохраняет параметры, строит UI. Значения
              чекбоксов появляются после set_values.
        """
        super().__init__(parent)
        self._field_def = field_def
        self._bg_color = bg_color
        self._values: list = []
        self._selected: set = set()
        self._expanded: bool = False
        self._checkboxes: dict = {}
        self._overlay_parent = None
        self._build_ui()

    # ---------- Сборка ----------

    def _build_ui(self) -> None:
        """Строит UI категории."""
        from ui.factories.filter_factory import FilterFactory

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # --- Строка заголовка ---
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)

        self._tristate_cb = FilterFactory.create_tristate_checkbox(
            self, self._bg_color,
        )
        self._tristate_cb.clicked.connect(self._on_tristate_clicked)
        header.addWidget(self._tristate_cb)

        self._label = LabelFactory.create_label(
            self, self._field_def.label,
            bg_color=(0, 0, 0, 0), text_color=None,
            clickable=True, on_click=self._toggle_expanded,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        header.addWidget(self._label)

        self._arrow_btn = ButtonFactory.create_button(
            self, "", self._bg_color,
            padding="0px", fixed_size=(20, 20),
            icon_path=(self._ICONS_DIR / "arrow_left.svg").as_posix(),
        )
        self._arrow_btn.clicked.connect(self._toggle_expanded)
        header.addWidget(self._arrow_btn)

        header.addStretch()
        layout.addLayout(header)

        # --- Раскрывающийся блок ---
        self._body = QWidget(None)
        self._body.setObjectName(
            f"filter_category_body_{self._field_def.name}"
        )
        body_bg = ColorCalculator.derive(
            self._bg_color,
            r_fn=lambda r: r + r // 4,
            g_fn=lambda g: g + g // 3,
            b_fn=lambda b: b + b // 2,
            alpha=None,
        )
        self._body.bg_color = body_bg
        self._body.setStyleSheet(
            f"QWidget#{self._body.objectName()} {{ "
            f"background: {ColorCalculator.to_str(body_bg)}; "
            f"border-radius: 6px; }}"
        )
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(8, 4, 8, 4)
        body_layout.setSpacing(2)

        btns_row = QHBoxLayout()
        btns_row.setContentsMargins(0, 0, 0, 0)
        btns_row.setSpacing(4)
        self._select_all_btn = FilterFactory.create_select_all_button(
            self._body, self._bg_color,
        )
        self._select_all_btn.clicked.connect(self._select_all)
        btns_row.addWidget(self._select_all_btn)
        self._clear_all_btn = FilterFactory.create_clear_all_button(
            self._body, self._bg_color,
        )
        self._clear_all_btn.clicked.connect(self._clear_all)
        btns_row.addWidget(self._clear_all_btn)
        btns_row.addStretch()
        body_layout.addLayout(btns_row)

        scroll, content_widget, self._values_layout = (
            ListWidgetFactory.create_scroll_container(
                self._body, spacing=2, bg_color=body_bg,
                rounded=False,
            )
        )
        # Публичный bg_color — для BackgroundResolver: дочерние
        # чекбоксы считают от него, а не идут выше к _body или окну.
        content_widget.bg_color = body_bg
        content_widget.setStyleSheet(
            f"background: {ColorCalculator.to_str(body_bg)};"
        )
        body_layout.addWidget(scroll)
        self._body.setVisible(False)

    def set_overlay_parent(self, parent) -> None:
        """Задаёт родителя для overlay-списка значений.

        Вход:
            parent — QWidget-родитель (обычно central widget окна).

        Роль: FilterPanel вызывает после создания категории и
              определения overlay-родителя. До этого раскрытие
              невозможно — _body остаётся скрытым.
        """
        self._overlay_parent = parent

    # ---------- Публичный API ----------

    def set_values(self, values: list) -> None:
        """Заполняет список чекбоксов значениями.

        Вход: values — список значений.
        Роль: очищает layout значений, создаёт по чекбоксу на
              каждое значение, подключает stateChanged.
        """
        from ui.factories.filter_factory import FilterFactory

        self._values = list(values)
        self._checkboxes = {}

        # Очистка layout.
        while self._values_layout.count():
            item = self._values_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for value in self._values:
            cb = FilterFactory.create_value_checkbox(
                self._body, str(value),
                checked=False, bg_color=(0, 0, 0, 0),
            )
            cb.toggled.connect(
                lambda checked, v=value: self._on_value_toggled(v, checked)
            )
            self._values_layout.addWidget(cb)
            self._checkboxes[value] = cb

    def set_selected(self, selected: set) -> None:
        """Устанавливает выбранные значения.

        Вход: selected — множество значений.
        Роль: перезаписывает self._selected, обновляет чекбоксы
              (без эмита), пересчитывает тристейт и счётчик.
        """
        self._selected = set(selected)
        for value, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(value in self._selected)
            cb.blockSignals(False)
        self._update_tristate()
        self.refresh_counter()

    def get_selected(self) -> set:
        """Возвращает копию выбранных значений."""
        return set(self._selected)

    def refresh_counter(self) -> None:
        """Обновляет подпись лейбла категории.

        Роль: счётчик выбранных значений не показываем — он
              растягивает лейбл. Текст всегда — имя категории.
        """
        self._label.setText(self._field_def.label)

    # ---------- Внутренние ----------

    def _toggle_expanded(self) -> None:
        """Раскрывает/сворачивает overlay-список значений.

        Роль: при раскрытии _body перепривязывается к overlay-
              родителю, показывается, позиционируется под
              заголовком категории и поднимается поверх соседей.
              При сворачивании — скрывается. Родитель сохраняется
              между вызовами.
        """
        from PySide6.QtGui import QIcon
        self._expanded = not self._expanded
        if self._expanded:
            if self._overlay_parent is None:
                # Overlay-родитель не задан — раскрытие невозможно.
                self._expanded = False
                return
            self._body.setParent(self._overlay_parent)
            self._body.show()
            self._position_body()
            self._body.raise_()
        else:
            self._body.hide()
        name = "arrow_down.svg" if self._expanded else "arrow_left.svg"
        self._arrow_btn.setIcon(
            QIcon((self._ICONS_DIR / name).as_posix())
        )

    def _position_body(self) -> None:
        """Позиционирует overlay-список под заголовком категории.

        Роль: считает позицию под нижним левым углом своей
              категории в глобальных координатах, переводит в
              систему родителя overlay. Зажимает в границы
              родителя, чтобы список не вылезал за пределы окна.
        """
        parent = self._body.parent()
        if parent is None:
            return
        pw = parent.width()
        ph = parent.height()
        if pw <= 0 or ph <= 0:
            return

        self._body.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        desired = parent.mapFromGlobal(pos)

        max_x = max(0, pw - self._body.width())
        max_y = max(0, ph - self._body.height())
        x = max(0, min(desired.x(), max_x))
        y = max(0, min(desired.y(), max_y))
        self._body.move(x, y)

    def collapse_body(self) -> None:
        """Сворачивает overlay-список, если он раскрыт.

        Роль: вызывает FilterPanel при общем collapse панели —
              чтобы раскрытые списки не оставались висеть поверх.
        """
        if not self._expanded:
            return
        self._expanded = False
        self._body.hide()
        from PySide6.QtGui import QIcon
        self._arrow_btn.setIcon(
            QIcon((self._ICONS_DIR / "arrow_left.svg").as_posix())
        )

    def is_body_open(self) -> bool:
        """Возвращает True, если overlay-список раскрыт."""
        return self._expanded

    def get_body_widget(self):
        """Возвращает QWidget overlay-списка (для eventFilter)."""
        return self._body

    def reposition_body_if_open(self) -> None:
        """Пересчитывает позицию _body, если он раскрыт.

        Роль: FilterPanel вызывает после смещения _categories_row —
              чтобы открытый список следовал за своей категорией.
        """
        if self._expanded:
            self._position_body()

    def _on_tristate_clicked(self, checked: bool) -> None:
        """Клик по тристейт-чекбоксу.

        Вход: checked — состояние после клика (Qt уже изменил его).

        Роль: интерпретирует клик по текущему _selected:
              всё выбрано или частично → очистить;
              ничего не выбрано → выбрать всё.
              Визуальная синхронизация — через _update_tristate.
        """
        if self._selected == set(self._values) and self._values:
            self._clear_all()
        elif self._selected:
            self._clear_all()
        else:
            self._select_all()

    def _update_tristate(self) -> None:
        """Синхронизирует состояние тристейт-чекбокса."""
        self._tristate_cb.blockSignals(True)
        if self._values and self._selected == set(self._values):
            self._tristate_cb.setCheckState(Qt.Checked)
        elif not self._selected:
            self._tristate_cb.setCheckState(Qt.Unchecked)
        else:
            self._tristate_cb.setCheckState(Qt.PartiallyChecked)
        self._tristate_cb.blockSignals(False)
        self._tristate_cb.style().unpolish(self._tristate_cb)
        self._tristate_cb.style().polish(self._tristate_cb)
        self._tristate_cb.update()

    def _select_all(self) -> None:
        """Отмечает все значения."""
        self._selected = set(self._values)
        for cb in self._checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._update_tristate()
        self.refresh_counter()
        self.selection_changed.emit(self._field_def.name)

    def _clear_all(self) -> None:
        """Снимает все отметки."""
        self._selected.clear()
        for cb in self._checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._update_tristate()
        self.refresh_counter()
        self.selection_changed.emit(self._field_def.name)

    def _on_value_toggled(self, value, checked: bool) -> None:
        """Реакция на переключение чекбокса значения.

        Вход:
            value — значение, которому соответствует чекбокс.
            checked — True, если чекбокс установлен, иначе False.

        Роль: синхронизирует _selected, обновляет тристейт и
              счётчик, эмитит selection_changed. Вызывается при
              каждом клике — и при установке, и при снятии.
        """
        if checked:
            self._selected.add(value)
        else:
            self._selected.discard(value)
        self._update_tristate()
        self.refresh_counter()
        self.selection_changed.emit(self._field_def.name)

class FilterPanel(QWidget):
    """Панель фильтров.

    Роль:
        Собирает набор FilterCategory, управляет раскрытием/
        сворачиванием, отдаёт отфильтрованный список через
        get_filtered. Сигнал filtered_changed эмитится при
        любом изменении выбора.
    """

    filtered_changed = Signal(list)

    def __init__(self, parent, field_defs: list, get_source, bg_color):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            field_defs — list[FieldDef].
            get_source — Callable[[], list] — источник объектов
                         для фильтрации.
            bg_color — фон панели (кортеж).
        """
        super().__init__(parent)
        self._field_defs = field_defs
        self._get_source = get_source
        self.bg_color = bg_color
        self._selected: dict = {fd.name: set() for fd in field_defs}
        self._is_open: bool = False
        self._categories: dict = {}
        self._scroll = None
        self._build_ui()

    # ---------- Сборка ----------
    def _resolve_overlay_parent(self):
        """Возвращает контейнер для overlay независимо от типа окна.

        Выход:
            QWidget — родитель для overlay-ряда.

        Роль:
            Обходит цепочку предков снизу вверх. Первый QMainWindow
            в цепочке отдаёт centralWidget() — видимую область без
            меню и статус-бара. Если такого нет — берётся top-level
            окно (QDialog, plain QWidget).
            `self.window()` не используется: на момент __init__
            FilterPanel ещё не вписан в иерархию окна, и window()
            может вернуть MainWindow вместо непосредственного
            QMainWindow-родителя (BrandsWindow).
        """
        # Обход предков: ищем первый QMainWindow.
        w = self
        while w is not None:
            if hasattr(w, "centralWidget"):
                cw = w.centralWidget()
                if cw is not None:
                    return cw
            w = w.parent()
        # Fallback — top-level.
        top = self.window()
        if top is not None:
            return top
        return self

    def _on_horizontal_scroll(self, value: int = 0) -> None:
        """Реакция на прокрутку ряда категорий.

        Вход: value — новая позиция скроллбара (не используется).

        Роль:
            Категории, целиком попадающие в viewport, едут за
            списком — их раскрытый _body пересчитывает позицию.
            Категории, касающиеся или пересекающие левый/правый
            край viewport, сворачивают свой _body — иначе overlay
            «прилипал» бы к краю и не читался.
            Автоматическое восстановление раскрытия после
            возврата категории в viewport НЕ делаем.
        """
        viewport = self._scroll.viewport()
        vw = viewport.width()
        for category in self._categories.values():
            pos = category.mapTo(viewport, QPoint(0, 0))
            if pos.x() < 0 or pos.x() + category.width() > vw:
                category.collapse_body()
            else:
                category.reposition_body_if_open()

    def _position_overlay(self) -> None:
        """Позиционирует _scroll справа от кнопки, зажимая в родителя.

        Роль:
            Ширина области — от правого края кнопки «Фильтры» +5
            до правого края родителя −10. Если natural-ширина ряда
            меньше — область сужается под содержимое. При
            переполнении (content шире области) появляется
            горизонтальный скроллбар, высота области увеличивается
            на его высоту. Позиция: под кнопкой, выровнена по её
            правому краю; зажимается в границы родителя.
        """
        parent = self._scroll.parent()
        if parent is None:
            return
        pw = parent.width()
        ph = parent.height()
        if pw <= 0 or ph <= 0:
            return

        # Natural размеры контента.
        self._categories_row.adjustSize()
        content_w = self._categories_row.width()
        content_h = self._categories_row.height()

        # Доступная горизонталь: от правого края кнопки +5
        # до правого края родителя −10.
        btn_right_global = self._master_btn.mapToGlobal(
            QPoint(self._master_btn.width(), 0)
        )
        btn_right_in_parent = parent.mapFromGlobal(btn_right_global)
        available_left = btn_right_in_parent.x() + 5
        available_right = pw - 10
        available_width = max(0, available_right - available_left)

        final_w = min(content_w, available_width)
        will_scroll = content_w > final_w

        hbar_h = 0
        if will_scroll:
            hbar_h = (
                self._scroll.horizontalScrollBar().sizeHint().height()
            )
        final_h = content_h + hbar_h

        self._scroll.resize(final_w, final_h)

        # Желаемая позиция — по верхнему левому углу кнопки.
        btn_pos = self._master_btn.mapToGlobal(QPoint(0, 0))
        desired = parent.mapFromGlobal(btn_pos)

        max_x = max(0, pw - final_w)
        max_y = max(0, ph - final_h)
        x = max(0, min(available_left, max_x))
        y = max(0, min(desired.y(), max_y))
        self._scroll.move(x, y)

        # Раскрытые _body едут за своими категориями.
        for category in self._categories.values():
            category.reposition_body_if_open()

    def _build_ui(self) -> None:
        """Строит мастер-кнопку и скроллируемый ряд категорий.

        Роль: кнопка «Фильтры» лежит в layout панели. Ряд
              категорий обёрнут в QScrollArea — при переполнении
              появляется горизонтальный скроллбар. Фон ряда —
              на самой _scroll и её viewport; сам _categories_row
              прозрачен. Позиционируется вручную через move().
        """
        from ui.factories.filter_factory import FilterFactory

        # Внешний layout панели — только кнопка.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._master_btn = FilterFactory.create_master_button(
            self, "Фильтры", None,
        )
        self._master_btn.clicked.connect(self._toggle_open)
        layout.addWidget(self._master_btn, alignment=Qt.AlignLeft)

        category_widgets = []
        for fd in self._field_defs:
            category = FilterFactory.create_category(
                self, fd, self.bg_color,
            )
            category.selection_changed.connect(
                self._on_category_changed
            )
            self._categories[fd.name] = category
            category_widgets.append(category)

        # Подложка ряда — на 10% темнее фона окна.
        panel_bg = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - r // 9,
            g_fn=lambda g: g - g // 8,
            b_fn=lambda b: b - b // 7,
            alpha=None,
        )

        # Overlay-контейнер: parent — центральный виджет окна.
        parent_widget = self._resolve_overlay_parent()

        # Ряд категорий создаётся без родителя — его присвоит
        # QScrollArea.setWidget (передаст владение).
        self._categories_row = QWidget()
        self._categories_row.setObjectName("filter_categories_row")
        self._categories_row.setStyleSheet(
            "QWidget#filter_categories_row { background: transparent; }"
        )

        row_layout = QHBoxLayout(self._categories_row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)
        row_layout.setAlignment(Qt.AlignLeft)
        for c in category_widgets:
            c.set_overlay_parent(parent_widget)
            row_layout.addWidget(c)

        # QScrollArea — обёртка ряда. Горизонтальный скроллбар
        # появляется при переполнении, вертикальный отключён.
        self._scroll = ListWidgetFactory.create_scroll_area(
            parent_widget,
            widget=self._categories_row,
            bg_color=panel_bg,
            border="none",
            border_radius=6,
            widget_resizable=False,
            object_name="filter_categories_scroll",
            rounded=False,
        )
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._scroll.setVisible(False)
        # Скролл → слот. valueChanged(int) — принимаем с дефолтом.
        self._scroll.horizontalScrollBar().valueChanged.connect(
            self._on_horizontal_scroll
        )

    # ---------- Публичный API ----------

    def get_filtered(self) -> list:
        """Возвращает отфильтрованный список.

        Выход: list — источник, пропущенный через предикаты
               всех категорий (AND между категориями).
        """
        source = self._get_source()
        predicates = [
            FilterCore.build_predicate(fd, self._selected[fd.name])
            for fd in self._field_defs
        ]
        return FilterCore.apply(source, predicates)

    def refresh(self) -> None:
        """Пересобирает значения категорий из источника.

        Роль: для каждой категории собирает values через
              FilterCore.collect_values, чистит мёртвые выбранные
              (selected & values), передаёт в category.
              Вызывается при раскрытии панели.
        """
        source = self._get_source()
        for fd in self._field_defs:
            values = FilterCore.collect_values(source, fd)
            self._selected[fd.name] &= set(values)
            category = self._categories[fd.name]
            category.set_values(values)
            category.set_selected(self._selected[fd.name])

    def reset(self) -> None:
        """Сбрасывает все категории."""
        for fd in self._field_defs:
            self._selected[fd.name] = set()
            self._categories[fd.name].set_selected(set())
        self._update_master_text()

    def collapse(self) -> None:
        """Публичное сворачивание панели."""
        if not self._is_open:
            return
        self._is_open = False
        for category in self._categories.values():
            category.collapse_body()
        self._scroll.setVisible(False)
        self._update_master_text()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def is_open(self) -> bool:
        """Возвращает состояние раскрытия."""
        return self._is_open

    # ---------- Внутренние ----------

    def _toggle_open(self) -> None:
        """Раскрывает/сворачивает ряд категорий."""
        if self._is_open:
            self.collapse()
            return
        self._is_open = True
        self.refresh()
        # Сначала показать — Qt активирует layout, выставит
        # реальные sizeHint. Без этого row.height() == 0 и move()
        # позиционирует виджет нулевой высоты.
        self._scroll.show()
        self._position_overlay()
        self._scroll.raise_()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._update_master_text()

    def _update_master_text(self) -> None:
        """Обновляет текст мастер-кнопки.

        Роль: заглушка для возможного изменения текста кнопки
        """
        self._master_btn.setText("Фильтры")

    def _on_category_changed(self, name: str) -> None:
        """Реакция на изменение выбора в категории.

        Вход: name — ключ категории (fd.name).
        Роль: обновляет _selected, счётчик на мастер-кнопке,
              эмитит filtered_changed с новым списком.
        """
        if name not in self._categories:
            return
        self._selected[name] = self._categories[name].get_selected()
        self._update_master_text()
        self.filtered_changed.emit(self.get_filtered())

    def eventFilter(self, obj, event) -> bool:
        """Ловит клик вне панели и overlay-ряда — сворачивает.

        Вход: obj — объект-источник; event — событие.
        Выход: False — событие не поглощаем (клик доходит
               до получателя).

        Роль:
            Два случая:
                1. MouseButtonPress вне панели и вне overlay →
                   collapse. Клик не поглощаем.
                2. Resize родителя overlay → пересчитать позицию
                   (кнопка «Фильтры» могла сдвинуться вместе с
                   layout). Клик доходит до получателя как есть.
        """
        # Событие — ресайз родителя: пересчитываем позицию overlay.
        if (self._is_open
                and event.type() == QEvent.Resize
                and obj is self._scroll.parent()):
            self._position_overlay()

        if event.type() == QEvent.MouseButtonPress and self._is_open:
            pos = event.globalPosition().toPoint()
            # Клик внутри самой панели (по кнопке «Фильтры») — ок.
            if self.rect().contains(self.mapFromGlobal(pos)):
                return super().eventFilter(obj, event)
            # Клик внутри _scroll (включая скроллбар) — ок.
            if self._scroll.rect().contains(
                    self._scroll.mapFromGlobal(pos)):
                return super().eventFilter(obj, event)
            # Клик внутри раскрытого overlay-списка любой
            # категории — тоже ок.
            for category in self._categories.values():
                body = category.get_body_widget()
                if body is None or not body.isVisible():
                    continue
                if body.rect().contains(body.mapFromGlobal(pos)):
                    return super().eventFilter(obj, event)
            # Иначе — вне, сворачиваем.
            self.collapse()
            return False
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        """Снимает eventFilter при закрытии панели."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)