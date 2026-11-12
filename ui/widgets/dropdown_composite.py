"""
Композитный выпадающий список (DropdownComposite).

Содержит DropdownComposite — виджет, состоящий из кнопки-триггера
и выпадающей панели (popup), которая позиционируется как отдельное
окно (Qt.Popup) и не обрезается границами родителя. Ограничение
позиции происходит только по границам экрана.
"""

from PySide6.QtCore import Qt, Signal, QEvent, QPoint
from PySide6.QtGui import QGuiApplication, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QApplication,
    QSpacerItem, QSizePolicy, QGraphicsDropShadowEffect,  QLayoutItem
)

from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory, ListWidgetFactory,
)
from ui.styles import (
    WidgetStyle, ColorCalculator, IconRenderer,
    GeometryCalculator, BackgroundResolver,
)

class _DropdownRow(QWidget):
    """Строка выпадающего списка с поддержкой hover и press."""
    def __init__(self, parent, bg_color):
        super().__init__(parent)
        self.bg_color = bg_color  # <--- Публичный атрибут для BackgroundResolver
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
        self.setStyleSheet(f"background-color: {ColorCalculator.to_str(bg)}; border-radius: 4px;")

class DropdownComposite(QWidget):
    """Композитный выпадающий список.

    Представляет собой кнопку-триггер и выпадающую панель (popup),
    которая позиционируется как отдельное окно (Qt.Popup). Благодаря
    этому список не обрезается границами родительских виджетов и
    может выходить за пределы MainWindow, но всегда ограничивается
    физическими границами экрана.

    Пример использования:
        dropdown = DroplistFactory.create_dropdown(parent, config={
            "settings": {"placeholder": "Выберите...", "max_length": 300},
            "items": [
                {"label": "Пункт 1", "data": 1},
                {"label": "Пункт 2", "data": 2},
                {"separator": True},
                {"label": "Пункт 3", "data": 3},
            ]
        })

    Сигналы:
        selection_changed(object) — испускается при смене выбора.
            Для одиночного выбора (multi_select=False) возвращает data
            выбранного элемента (или None). Для мультивыбора возвращает
            список list[data] всех выбранных элементов.
        item_clicked(int) — испускается при клике по любой активной
            строке, передает её индекс.
    """

    selection_changed = Signal(object)
    item_clicked = Signal(int)

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
        "max_length": 600,
        "row_style": "default",
        "arrow_position": "right",
        "auto_select_first": True,
        "item_separators": False,
    }

    def __init__(self, parent, config: dict = None, **kwargs):
        """Конструктор выпадающего списка.

                Вход:
                    parent — родительский виджет.
                    config — словарь конфигурации, содержащий два ключа:
                        "settings" (dict) — переопределение настроек (см. ниже).
                        "items" (list[dict]) — список элементов для наполнения.
                    **kwargs — дополнительные настройки, которые объединяются
                        с config["settings"] (приоритет: config["settings"] > kwargs).

                --- НАСТРОЙКИ (config["settings"]) ---
                multi_select (bool): Режим множественного выбора. Если True,
                    current_data() возвращает список, а кнопка показывает
                    "Выбрано: N". По умолчанию False.
                close_on_select (bool | None): Закрывать ли попап при выборе
                    элемента. None означает: True для одиночного выбора,
                    False для мультивыбора.
                placeholder (str): Текст-заглушка на кнопке, если ничего
                    не выбрано. По умолчанию "Выберите...".
                auto_update_button (bool): Автоматически обновлять текст
                    кнопки при выборе элемента. По умолчанию True.
                allow_multiple_open (bool): Разрешать открытие вложенных
                    DropdownComposite одновременно с родительским. По умолчанию False.
                close_on_scroll (bool): Закрывать ли вложенные списки при
                    скролле родительского. По умолчанию True.
                select_on_interactive_click (bool): Выбирать строку целиком
                    при клике на интерактивный элемент внутри неё (кнопку, чекбокс).
                    По умолчанию False (клик по кнопке не меняет выбор строки).
                popup_bg_color (tuple | None): Цвет фона выпадающего списка.
                    Если None, вычисляется автоматически от фона родителя.
                popup_border (str): QSS-рамка списка. Например,
                    "1px solid rgba(255,255,255,0.2)". По умолчанию "none".
                popup_border_radius (int): Радиус скругления углов списка.
                    По умолчанию 6.
                popup_shadow (bool): Отображать ли тень под попапом.
                    По умолчанию False.
                max_length (int): Максимальная длина списка в пикселях.
                    Если список раскрывается по вертикали — это max-height,
                    если по горизонтали — max-width. По умолчанию 600.
                row_style (str): Стиль строк. "default" — обычный текст,
                    "chip" — текст в виде цветной плашки. По умолчанию "default".
                arrow_position (str): Положение стрелки на кнопке ("left" или
                    "right"). По умолчанию "right".
                auto_select_first (bool): Автоматически выбирать первый элемент
                    при добавлении. По умолчанию True.
                item_separators (bool): Автоматически вставлять горизонтальные
                    разделители между всеми элементами списка. По умолчанию False.

                --- СТРУКТУРА ЭЛЕМЕНТОВ (config["items"]) ---
                Каждый элемент списка — это словарь. Поддерживаются следующие типы:
                1. {"label": "Текст", "data": <любые данные>} — обычная текстовая строка.
                2. {"button": "Текст", "callback": func, "icon_type": "..."} — строка с кнопкой.
                3. {"widget": QWidget | QLayoutItem} — произвольный виджет (например, вложенный дропдаун).
                4. {"spacer": True} — распорка для отжатия элементов.
                5. {"separator": True} — горизонтальная линия-разделитель.
                Также можно добавить "disabled": True, чтобы заблокировать строку.
                """
        super().__init__(parent)
        if config is None:
            config = {}

        # Слияние настроек: _DEFAULT_SETTINGS -> kwargs -> config["settings"]
        self.settings = self._DEFAULT_SETTINGS.copy()
        self.settings.update(kwargs)
        self.settings.update(config.get("settings", {}))

        if self.settings["close_on_select"] is None:
            self.settings["close_on_select"] = not self.settings["multi_select"]

        self._rows = []  # list[QWidget]
        self._row_datas = []  # list[object]
        self._row_texts = []  # list[str] (первый текстовый элемент)
        self._row_disabled = []  # list[bool]
        self._row_is_separator = []

        self._current_index = -1
        self._selected_indices = set()
        self._popup = None
        self._popup_direction = "down"

        # Резолв фона для popup
        if self.settings["popup_bg_color"] is None:
            parent_bg = BackgroundResolver.resolve_bg_color(self, None)
            if parent_bg is None:
                parent_bg = (63, 63, 63, 1.0)
            self._popup_bg = ColorCalculator.element_bg_for(parent_bg)
        else:
            self._popup_bg = self.settings["popup_bg_color"]

            # 1. Кнопка-триггер (композит из текста и отдельной кнопки-стрелки)
            self._trigger = QWidget(self)
            self._trigger.setObjectName(f"dropdown_trigger_{id(self)}")
            WidgetStyle.apply_panel(
                self._trigger, self._popup_bg,
                border_radius=self.settings["popup_border_radius"]
            )
            # Клик по пустому месту триггера тоже открывает список
            self._trigger.mousePressEvent = lambda e: self.toggle()

            trigger_layout = QHBoxLayout(self._trigger)
            trigger_layout.setContentsMargins(8, 4, 4, 4)
            trigger_layout.setSpacing(4)

            self._text_label = LabelFactory.create_label(
                self._trigger, text=self.settings["placeholder"], bg_color=(0, 0, 0, 0)
            )
            self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

            # Фон стрелки — темнее фона триггера
            arrow_bg = ColorCalculator.element_bg_for(self._popup_bg)
            self._arrow_btn = ButtonFactory.create_button(
                self._trigger, text="", bg_color=arrow_bg,
                fixed_size=(24, 24), padding="0px",
                border_radius=max(2, self.settings["popup_border_radius"] - 2)
            )
            self._arrow_btn.clicked.connect(self.toggle)

            if self.settings.get("arrow_position") == "left":
                trigger_layout.addWidget(self._arrow_btn)
                trigger_layout.addWidget(self._text_label, 1)
            else:
                trigger_layout.addWidget(self._text_label, 1)
                trigger_layout.addWidget(self._arrow_btn)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._trigger)

            self._update_button_icon()

    def _update_trigger_style(self):
        """Меняет фон триггера при открытии/закрытии."""
        is_open = self._popup and self._popup.isVisible()
        bg = self._popup_bg

        extra = ""
        if is_open:
            # Разделитель снизу, чтобы отделить кнопку от списка, и убираем нижние скругления
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
        """Обновляет иконку стрелки на кнопке в зависимости от состояния."""
        is_open = self._popup and self._popup.isVisible()
        pos = self.settings.get("arrow_position", "right")

        if is_open:
            # При раскрытии стрелка смотрит в сторону списка
            direction = self._popup_direction
        else:
            # В закрытом состоянии стрелка смотрит на текст
            direction = "left" if pos == "right" else "right"

        self._arrow_btn.setIcon(
            IconRenderer.make_arrow(direction, self._arrow_btn, bg_color=self._popup_bg)
        )

    # ---------- Публичный API ----------

    def add_item(self, config: dict) -> int:
        """Добавляет новую строку в выпадающий список.

        Вход:
            config — словарь с описанием строки (см. структуру в __init__).

        Выход: индекс добавленной строки (int) или -1 при ошибке.
        """
        index = len(self._rows)
        row_widget, data, text, is_sep = self._build_row(config, index)
        if row_widget is None:
            return -1

        index = len(self._rows)
        self._rows.append(row_widget)
        self._row_datas.append(data)
        self._row_texts.append(text)
        self._row_disabled.append(config.get("disabled", False))
        self._row_is_separator.append(is_sep)

        if (index == 0
                and self.settings["auto_select_first"]
                and not self.settings["multi_select"]
                and not self._row_disabled[index]):
            self.set_current_index(0)
        else:
            self._update_button_text()

        return index

    def add_separator(self) -> int:
        """Добавляет горизонтальный разделитель в список вручную.

        Выход: индекс добавленного разделителя (int).
        """
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
        """Очищает список полностью и сбрасывает состояние выбора.

        Возвращает кнопку к отображению placeholder (если auto_update_button=True).
        """
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
        if self.settings["auto_update_button"]:
            self._text_label.setText(self.settings["placeholder"])

    def set_current_index(self, index: int) -> None:
        """Программный выбор строки по её индексу.

        Вход:
            index — индекс строки (int). Если индекс выходит за границы,
                    указывает на разделитель или disabled-строку —
                    ничего не произойдет.
        """
        if 0 <= index < len(self._rows) and not self._row_disabled[index] and not self._row_is_separator[index]:
            if not self.settings["multi_select"]:
                self._selected_indices.clear()
            self._selected_indices.add(index)
            self._current_index = index
            self._update_row_styles()  # <--- ДОБАВИТЬ
            self._emit_selection()
            if self.settings["auto_update_button"]:
                self._update_button_text()

    def current_index(self) -> int:
        """Возвращает индекс текущей выбранной строки (или -1)."""
        return self._current_index

    def set_current_data(self, data) -> None:
        """Программный выбор строки по связанным с ней данным (data).

        Вход:
            data — объект, переданный в конфиге строки (ключ "data").
        """
        for i, d in enumerate(self._row_datas):
            if d == data:
                self.set_current_index(i)
                return

    def current_data(self):
        """Возвращает данные (data) выбранных строк.

        Выход:
            Для multi_select=False: data выбранного элемента или None.
            Для multi_select=True: список list[data] выбранных элементов.
        """
        if self.settings["multi_select"]:
            return [self._row_datas[i] for i in sorted(self._selected_indices)]
        if self._current_index >= 0:
            return self._row_datas[self._current_index]
        return None

    def set_placeholder(self, text: str) -> None:
        """Динамически меняет текст-заглушку (placeholder).

        Текст применится, если в данный момент ничего не выбрано.
        """
        self.settings["placeholder"] = text
        if not self._selected_indices and self.settings["auto_update_button"]:
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
        self._update_button_icon()
        self._update_trigger_style()

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def close(self) -> None:
        """Закрывает выпадающий список."""
        if self._popup and self._popup.isVisible():
            self._popup.hide()
            self._update_button_icon()
            self._update_trigger_style()
        app = QApplication.instance()
        if app:
            app.removeEventFilter(self)

    def toggle(self) -> None:
        """Переключает состояние списка (открывает/закрывает)."""
        if self._popup and self._popup.isVisible():
            self.close()
        else:
            self.open()

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

            # Поддержка как {"items": [...]}, так и прямого {"label": ...}
        items = config.get("items")
        if items is None:
            items = [config]

        widgets = []
        first_text = ""
        row_data = config.get("data")

        for item in items:
            match item:
                case {"widget": w}:
                    widgets.append(w)
                case {"label": lbl_text}:
                    if self.settings["row_style"] == "chip":
                        lbl = LabelFactory.create_label(None, lbl_text, bg_color=(0, 0, 0, 0))
                        WidgetStyle.apply_dropdown_chip(lbl, self._popup_bg)
                    else:
                        # Прозрачный фон, но с нормальными отступами для высоты
                        text_color = ColorCalculator.text_for(self._popup_bg)
                        lbl = LabelFactory.create_label(
                            None,
                            lbl_text,
                            bg_color=(0, 0, 0, 0),
                            text_color=text_color,
                            padding="4px 8px",
                            border_radius=0
                        )
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
        row_layout.setContentsMargins(4, 4, 4, 4)
        row_layout.setSpacing(0)
        row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for w in widgets:
            if isinstance(w, QWidget):
                row_layout.addWidget(w)
            elif isinstance(w, QLayoutItem):
                row_layout.addItem(w)

        if config.get("disabled", False):
            row.setEnabled(False)

        # Обработка клика по строке
        original_mouse_press = row.mousePressEvent

        def mouse_press(event, idx=index):
            if event.button() == Qt.LeftButton:
                self.item_clicked.emit(idx)
                if self.settings["select_on_interactive_click"] or not config.get("interactive", False):
                    self.set_current_index(idx)
                    if self.settings["close_on_select"]:
                        self.close()
            # Вызываем оригинальный метод _DropdownRow для отрисовки эффекта нажатия
            original_mouse_press(event)

        row.mousePressEvent = mouse_press
        return row, row_data, first_text, False

    def _build_popup(self) -> None:
        """Создает и собирает выпадающее окно."""
        self._popup = QWidget(None, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self._popup.setAttribute(Qt.WA_TranslucentBackground)
        self._popup.setAttribute(Qt.WA_DeleteOnClose, False)

        # Главный контейнер для фона (тень и закругления)
        container = QWidget(self._popup)
        container.setObjectName("dropdown_popup_container")

        # Перехватываем клики, чтобы Qt.Popup не закрывался при клике в пустоту
        container.mousePressEvent = lambda e: e.accept()
        self._popup.mousePressEvent = lambda e: e.accept()

        # Стилизация контейнера
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

        # Создаем QScrollArea и внутренний контейнер
        scroll, content_widget, scroll_layout = ListWidgetFactory.create_scroll_container(
            container, bg_color=self._popup_bg, rounded=False
        )
        self._scroll = scroll

        # Применяем скругление к самому скроллу и его вьюпорту, чтобы углы списка были круглыми
        radius = self.settings["popup_border_radius"]
        scroll.setStyleSheet(f"QScrollArea {{ border-radius: {radius}px; background: transparent; border: none; }}")
        scroll.viewport().setStyleSheet(f"border-radius: {radius}px; background: transparent;")
        content_widget.setStyleSheet(f"border-radius: {radius}px; background: transparent;")

        # Добавляем строки напрямую в layout скролла
        for i, row in enumerate(self._rows):
            row.setParent(content_widget)
            scroll_layout.addWidget(row)

            # Добавляем разделитель ПОСЛЕ строки, если это не последняя строка
            if self.settings.get("item_separators", False) and i < len(self._rows) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                WidgetStyle.apply_dropdown_separator(line, self._popup_bg)
                line.setParent(content_widget)
                scroll_layout.addWidget(line)

        # Внутренний layout контейнера (содержит только скролл)
        inner_layout = QVBoxLayout(container)
        # Теперь можно вернуть отступы в 0, так как QScrollArea стал прозрачным и скругленным
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.addWidget(scroll)

    def _position_popup(self) -> None:
        """Позиционирует popup с учетом экрана."""
        if not self._popup:
            return

        # 1. Сбрасываем лимиты и привязываем ширину к триггеру
        w = max(self._trigger.width(), 100)
        self._popup.setFixedWidth(w)
        self._scroll.setMaximumHeight(16777215)  # Qt-дефолт (сброс)
        self._scroll.setMaximumWidth(16777215)

        self._popup.layout().activate()
        self._popup.adjustSize()

        h = self._popup.height()

        # 2. Позиционируем ровно под триггером
        btn_global = self._trigger.mapToGlobal(QPoint(0, self._trigger.height()))

        # Если есть тень, визуальный край списка начинается ниже на размер отступа
        margin = 10 if self.settings["popup_shadow"] else 0
        btn_global.setY(btn_global.y() - margin)

        # 3. Вычисляем координаты и направление
        x, y, direction = GeometryCalculator.calculate_popup_position(
            btn_global, w, h, self._trigger.height(), self._trigger.width()
        )
        self._popup_direction = direction

        # 4. Применяем max_length в зависимости от направления
        if direction in ("up", "down"):
            self._scroll.setMaximumHeight(self.settings["max_length"])
        else:  # "left", "right"
            self._scroll.setMaximumWidth(self.settings["max_length"])

        # 5. Пересчитываем размеры (если лимит был превышен) и применяем позицию
        self._popup.layout().activate()
        self._popup.adjustSize()
        self._popup.move(x, y)

    def _update_button_text(self) -> None:
        if not self._selected_indices:
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
            self._text_label.setText(text if text else self.settings["placeholder"])

    def _update_row_styles(self) -> None:
        """Обновляет фон строк в зависимости от того, выбраны они или нет."""
        for i, row in enumerate(self._rows):
            if self._row_is_separator[i]:
                continue
            if isinstance(row, _DropdownRow):
                row.is_selected = (i in self._selected_indices)
                row._update_style()

    def _emit_selection(self) -> None:
        """Генерирует сигнал об изменении выбора."""
        self.selection_changed.emit(self.current_data())

    def eventFilter(self, obj, event) -> bool:
        """Закрывает popup при клике вне его границ."""
        if event.type() == QEvent.MouseButtonPress and self._popup and self._popup.isVisible():
            pos = event.globalPosition().toPoint()

            # Клик внутри popup — ок, не закрываем
            if self._popup.geometry().contains(pos):
                return False

            # Клик по кнопке-триггеру — принудительно закрываем и ПОГЛОЩАЕМ событие
            if self._trigger.rect().contains(self._trigger.mapFromGlobal(pos)):
                self.close()
                return True

            # Клик вне — закрываем и ПОГЛОЩАЕМ событие
            self.close()
            return True

        return super().eventFilter(obj, event)