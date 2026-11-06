"""
Диалоги разрешения неизвестных имён и выбора объекта.

Содержит:
    UnknownResolverDialog — мастер последовательного разрешения:
        для каждого norm_key показывает label и кнопки по actions.
    ObjectPickerDialog — список с поиском и кнопкой подтверждения:
        выбор одного элемента из items + extra_items.

Роль в программе:
    Открываются из SellsFBSWindow по callback'ам резолвера.
    UnknownResolverDialog возвращает result {action_key: {norm_key: value}},
    ObjectPickerDialog — выбранный key (str) или None.

"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QHBoxLayout

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory,
)
from ui.styles import ColorCalculator, WindowStyle
from ui.windows.message_dialog import NotificationDialog
from utils.text_utils import TextUtils
from utils.unknown_resolver import ResolverAction


class UnknownResolverDialog(BaseEditDialog):
    """Мастер последовательного разрешения неизвестных имён.

    Роль:
        Показывает пользователю norm_key по одному с лейблом
        и набором кнопок (actions). Каждое нажатие → вызов
        action.handler → сохранение value → переход к следующему.
        После последнего объекта — accept().

    Атрибуты класса:
        LOGGER_SOURCE, LOGGER_DOMAIN — идентификация для LoggerV2.

    Контракт жёсткости:
        reject() → pass. Esc и клик вне окна не закрывают мастер.
        Закрытие только через accept() после прохода всех объектов.
    """

    LOGGER_SOURCE = "UnknownResolverDialog.unknown_resolver_dialog"
    LOGGER_DOMAIN = "chz_mp"

    def __init__(self, parent, items, actions, get_label, title,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (обычно SellsFBSWindow).
            items — dict[norm_key, list[str]] — что разрешаем.
            actions — list[ResolverAction].
            get_label — Callable[[norm_key, raws], str] — подпись
                        объекта в UI.
            title — заголовок окна.
            log_manager_v2 — LogManagerV2 или None.

        Роль:
            Сохраняет данные до super().__init__. Фон считает сам
            от родителя по формуле (+10, +30, +20). При пустом
            items — сразу accept().
        """
        self._items = items
        self._actions = actions
        self._get_label = get_label
        self._keys_list = list(items.keys())
        self._current_index = 0
        self._results: dict = {a.key: {} for a in actions}

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 10,
            g_fn=lambda g: g + 30,
            b_fn=lambda b: b + 20,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title=title,
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=500,
            height=280,
            log_manager_v2=log_manager_v2,
        )

        # Пустой вход — нечего показывать.
        if not self._keys_list:
            self.accept()

    def reject(self) -> None:
        """Запрещает закрытие мастера через Esc / программный reject.

        Роль: мастер обходится только accept() после прохода всех
              объектов. Единственный выход — принять решение по
              каждому.
        """
        pass

    def keyPressEvent(self, event) -> None:
        """Блокирует Esc — мастер закрывается только через accept().

        Роль: reject() → pass недостаточно, если выше по иерархии
              keyPressEvent обходит вызов reject(). Явный ignore()
              на Esc гарантирует, что мастер не закроется по
              клавиатуре. Остальные клавиши — наверх.
        """
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def _build_content(self, layout) -> None:
        """Счётчик, лейбл объекта и кнопки по actions.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: при пустом items — ничего не строим, __init__ закроет
              диалог сразу после super().__init__.
        """
        if not self._keys_list:
            return

        self._counter_label = LabelFactory.create_header_label(
            self,
            f"Разрешение {self._current_index + 1} из "
            f"{len(self._keys_list)}",
        )
        layout.addWidget(self._counter_label)

        norm_key = self._keys_list[self._current_index]
        raws = self._items[norm_key]
        self._item_label = LabelFactory.create_label(
            self,
            self._get_label(norm_key, raws),
            bg_color=(0, 0, 0, 0),
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        layout.addWidget(self._item_label)

        btns_layout = QHBoxLayout()
        btns_layout.addStretch()
        for action in self._actions:
            btn = ButtonFactory.create_button(
                self, action.label, (100, 100, 140, 0.8),
                padding="6px 14px",
            )
            btn.clicked.connect(
                lambda checked=False, a=action: self._on_action(a)
            )
            btns_layout.addWidget(btn)
        btns_layout.addStretch()
        layout.addLayout(btns_layout)

    def _on_action(self, action: ResolverAction) -> None:
        """Обработка нажатия одной кнопки-действия.

        Вход: action — ResolverAction.

        Роль:
            Вызывает action.handler(norm_key, raws). Если handler
            бросил ValueError — показывает уведомление и остаётся
            на текущем объекте. Если вернул None — уведомление,
            остаётся. Иначе сохраняет value и переходит дальше.
        """
        norm_key = self._keys_list[self._current_index]
        raws = self._items[norm_key]

        try:
            value = action.handler(norm_key, raws)
        except ValueError as e:
            NotificationDialog.notify(
                self, str(e),
                title_text="Ошибка",
                bg_color=self.bg_color,
            )
            return

        if value is None:
            NotificationDialog.notify(
                self,
                "Обработчик вернул пустое значение — попробуйте снова",
                title_text="Ошибка",
                bg_color=self.bg_color,
            )
            return

        self._results[action.key][norm_key] = value
        self._advance()

    def _advance(self) -> None:
        """Переход к следующему объекту или accept()."""
        self._current_index += 1
        if self._current_index >= len(self._keys_list):
            self.accept()
            return

        self._counter_label.setText(
            f"Разрешение {self._current_index + 1} из "
            f"{len(self._keys_list)}"
        )
        norm_key = self._keys_list[self._current_index]
        raws = self._items[norm_key]
        self._item_label.setText(self._get_label(norm_key, raws))

    def get_result(self) -> dict:
        """Возвращает dict[action_key, dict[norm_key, value]]."""
        return self._results


class ObjectPickerDialog(BaseEditDialog):
    """Список с поиском — выбор одного объекта.

    Роль:
        Показывает объединённый набор items + extra_items,
        фильтрует по подстроке, возвращает выбранный key.

    Атрибуты класса:
        LOGGER_SOURCE, LOGGER_DOMAIN — идентификация для LoggerV2.

    Контракт жёсткости:
        reject() → pass. Пользователь обязан выбрать объект.
    """

    LOGGER_SOURCE = "ObjectPickerDialog.unknown_resolver_dialog"
    LOGGER_DOMAIN = "chz_mp"

    def __init__(self, parent, items, extra_items, title,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (обычно UnknownResolverDialog).
            items — dict[key, label] — основные объекты.
            extra_items — dict[key, label] | None — спец-объекты
                          (Мусор / Неопознанный / Возвраты).
            title — заголовок окна.
            log_manager_v2 — LogManagerV2 или None.

        Роль:
            Сохраняет данные до super().__init__. Фон считает сам
            от родителя (резолвера) по формуле (+10, -20, +15).
        """
        self._items = dict(items)
        self._extra_items = dict(extra_items) if extra_items else {}
        self._selected = None

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 10,
            g_fn=lambda g: g - 20,
            b_fn=lambda b: b + 15,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title=title,
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=450,
            height=500,
            log_manager_v2=log_manager_v2,
        )

    def reject(self) -> None:
        """Запрещает закрытие через Esc / программный reject.

        Роль: пользователь обязан выбрать объект кликом по строке
              и нажать «Подтвердить».
        """
        pass

    def keyPressEvent(self, event) -> None:
        """Блокирует Esc — пикер закрывается только через accept().

        Роль: reject() → pass недостаточно, если выше по иерархии
              keyPressEvent обходит вызов reject(). Явный ignore()
              на Esc гарантирует, что пикер не закроется по
              клавиатуре. Остальные клавиши — наверх.
        """
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def _build_content(self, layout) -> None:
        """Заголовок, поиск, список и кнопка подтверждения.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Выберите",
        ))

        self._search_edit = InputWidgetFactory.create_default_line_edit(
            self, placeholder="Фильтр...",
        )
        self._search_edit.textChanged.connect(self._filter_list)
        layout.addWidget(self._search_edit)

        self._list_widget = ListWidgetFactory.create_list_widget(
            self,
            bg_color=self.bg_color,
            text_color=None,
            selection_mode=QListWidget.SelectionMode.SingleSelection,
        )
        self._list_widget.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        self._populate_list()
        layout.addWidget(self._list_widget)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self._btn_confirm = ButtonFactory.create_button(
            self, "Подтвердить", (70, 160, 90, 0.8),
            fixed_size=(150, 35),
        )
        self._btn_confirm.clicked.connect(self._on_confirm)
        self._btn_confirm.setEnabled(False)
        bottom.addWidget(self._btn_confirm)
        bottom.addStretch()
        layout.addLayout(bottom)

    def _populate_list(self) -> None:
        """Заполняет QListWidget объединённым набором items + extra.

        Роль: key сохраняется в item.data(UserRole) — чтобы
              _on_confirm отдал наружу key, а не label.
              extra_items идут после items; при совпадении ключей
              приоритет у extra.
        """
        all_items = {**self._items, **self._extra_items}
        for key, label in all_items.items():
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list_widget.addItem(item)

    def _filter_list(self, text: str) -> None:
        """Скрывает строки, не содержащие нормализованный text.

        Вход: text — текст из поля поиска.
        Роль: пустой текст (норм. строка) не скрывает ничего.
        """
        norm = TextUtils.normalize(text)
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            item.setHidden(norm not in TextUtils.normalize(item.text()))

    def _on_selection_changed(self) -> None:
        """Активирует «Подтвердить» при выбранной строке."""
        selected = self._list_widget.currentItem()
        self._btn_confirm.setEnabled(selected is not None)

    def _on_confirm(self) -> None:
        """Сохраняет выбранный key и закрывает диалог."""
        selected = self._list_widget.currentItem()
        if selected is None:
            return
        self._selected = selected.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def get_selected(self) -> str | None:
        """Возвращает выбранный key или None."""
        return self._selected