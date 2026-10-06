"""
Базовый диалог чек-листа.

Содержит ChecklistDialog — каркас диалога множественного выбора:
список элементов чекбоксами, связанные — сверху с галкой,
применение изменений через hook _apply_result по OK.
Никакой привязки к брендам, продавцам, задачам — только
«элементы».

Роль в программе:
    Единая база для BrandChecklistDialog, SellerChecklistDialog
    и будущих чек-листов. Наследники реализуют четыре
    абстрактных метода и при необходимости переопределяют
    опциональные hooks.
"""

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, ListWidgetFactory,
)


class ChecklistDialog(BaseEditDialog):
    """Абстрактный диалог множественного выбора.

    Назначение:
        Показать список элементов чекбоксами. Связанные
        (по _is_item_checked) — сверху с галкой, остальные — снизу
        без галки. Внутри групп — сортировка по _get_item_sort_key.
        По OK вызывается _apply_result(checked, unchecked).

    Роль в программе:
        База для конкретных чек-листов. Работает с абстрактными
        «элементами», не знает про сущности.

    Наследник обязан реализовать:
        _get_items() — полный список элементов.
        _get_item_label(item) — подпись чекбокса.
        _is_item_checked(item) — связан ли элемент с целевым
                                  объектом на момент открытия.
        _apply_result(checked, unchecked) — применить результат.

    Наследник может переопределить:
        _get_header_text() — заголовок над списком (None → нет).
        _get_item_sort_key(item) — ключ сортировки внутри групп.
        _get_checkbox_object_name() — objectName чекбокса.
    """

    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None

    def __init__(self, parent=None, title="", bg_color=(64, 48, 66, 0.8),
                 close_button=True, draggable=True,
                 close_on_click_outside=True, modal=True,
                 width=400, height=450, log_manager_v2=None,
                 service_window_override=None) -> None:
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок.
            bg_color — цвет фона.
            close_button — показывать ли крестик.
            draggable — перетаскивание за тело.
            close_on_click_outside — закрывать при клике вне.
            modal — модальность.
            width, height — размеры.
            log_manager_v2 — LogManagerV2 или None.
            service_window_override — явное сервисное окно для
                центрирования. Основной сценарий: чек-лист
                «Child Б внутри Child A» (SellerChecklistDialog
                внутри BrandEditDialog) должен центрироваться
                от сервисного окна, а не от маленького диалога.

        Роль: сохраняет self._title и self._checkbox_items до
              super().__init__, прокидывает service_window_override
              в BaseEditDialog.
        """
        self._title = title
        self._checkbox_items: list = []
        super().__init__(
            parent=parent,
            title=title,
            bg_color=bg_color,
            width=width,
            height=height,
            close_button=close_button,
            ok_cancel=True,
            draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal,
            center=True,
            log_manager_v2=log_manager_v2,
            service_window_override=service_window_override,
        )

    # ---------- Абстрактные методы ----------

    def _get_items(self) -> list:
        """Полный список элементов для показа.

        Выход: list.
        Роль: абстрактный. Наследник возвращает свой источник.
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _get_items"
        )

    def _get_item_label(self, item) -> str:
        """Подпись чекбокса для элемента.

        Вход: item — элемент из _get_items().
        Выход: str — текст чекбокса.
        Роль: абстрактный.
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _get_item_label"
        )

    def _is_item_checked(self, item) -> bool:
        """Связан ли элемент с целевым объектом на момент открытия.

        Вход: item — элемент из _get_items().
        Выход: bool. True → чекбокс отмечен, элемент в верхней группе.
        Роль: абстрактный. Используется при инициализации чекбоксов
              и для сортировки «связанные сверху».
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _is_item_checked"
        )

    def _apply_result(self, checked: list, unchecked: list) -> None:
        """Применяет результат по OK.

        Вход:
            checked — list элементов с отмеченным чекбоксом.
            unchecked — list элементов со снятым чекбоксом.

        Выход: нет.
        Роль: абстрактный. Вызывается ровно один раз из
              _collect_result. Наследник сам решает, что делать:
              мутировать модели, звать сервис или ничего не делать.
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _apply_result"
        )

    # ---------- Опциональные hooks ----------

    def _get_header_text(self) -> str | None:
        """Заголовок над списком.

        Выход: str — показать заголовок; None — не строить.
        Роль: опциональный. Дефолт — без заголовка.
        """
        return None

    def _get_item_sort_key(self, item) -> str:
        """Ключ сортировки внутри группы.

        Вход: item — элемент.
        Выход: str. Дефолт — подпись в нижнем регистре.
        Роль: опциональный. Наследник может вернуть своё.
        """
        return self._get_item_label(item).lower()

    def _get_checkbox_object_name(self) -> str | None:
        """objectName чекбоксов.

        Выход: str — установить как objectName; None — без имени.
        Роль: опциональный. Дефолт — без имени.
        """
        return None

    # ---------- Каркас ----------

    def _build_content(self, layout) -> None:
        """Строит заголовок (если hook вернул текст) и чекбоксы.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Выход: нет.

        Роль:
            Единая сборка списка: заголовок → скролл-контейнер →
            чекбоксы. Связанные элементы (по _is_item_checked)
            идут первыми с галкой, остальные — ниже. Внутри
            каждой группы — сортировка по _get_item_sort_key.
            Все пары (QCheckBox, item) складываются
            в self._checkbox_items для _collect_result.
        """
        header_text = self._get_header_text()
        if header_text is not None:
            layout.addWidget(LabelFactory.create_header_label(
                self, header_text,
            ))

        scroll_area, _, content_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=2, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll_area)

        items = self._get_items()
        checked_items: list = []
        unchecked_items: list = []
        for item in items:
            if self._is_item_checked(item):
                checked_items.append(item)
            else:
                unchecked_items.append(item)

        checked_items = sorted(
            checked_items, key=lambda it: self._get_item_sort_key(it),
        )
        unchecked_items = sorted(
            unchecked_items, key=lambda it: self._get_item_sort_key(it),
        )

        object_name = self._get_checkbox_object_name()

        for item in checked_items:
            cb = InputWidgetFactory.create_checkbox(
                self, self._get_item_label(item), checked=True,
                bg_color=(0, 0, 0, 0), text_color=None,
                object_name=object_name,
            )
            self._checkbox_items.append((cb, item))
            content_layout.addWidget(cb)

        for item in unchecked_items:
            cb = InputWidgetFactory.create_checkbox(
                self, self._get_item_label(item), checked=False,
                bg_color=(0, 0, 0, 0), text_color=None,
                object_name=object_name,
            )
            self._checkbox_items.append((cb, item))
            content_layout.addWidget(cb)

    def _collect_result(self):
        """Собирает результат и вызывает _apply_result.

        Выход: None (базовый контракт BaseEditDialog).
        Роль:
            Формирует checked / unchecked по состоянию чекбоксов
            и делегирует применение в _apply_result один раз.
            Возвращает None — сам результат наследник хранит
            у себя.
        """
        checked: list = []
        unchecked: list = []
        for cb, item in self._checkbox_items:
            if cb.isChecked():
                checked.append(item)
            else:
                unchecked.append(item)
        self._apply_result(checked, unchecked)
        return None