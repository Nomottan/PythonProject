"""
Диалоги пайплайна возвратов.

Содержит PriorityResolutionDialog — модальное окно выбора
продавца для каждого конфликтного бренда. Открывается из
ReturnsWindow по callback от KizTransferService.

Роль в программе:
    Жёсткий модальный мастер: пользователь должен выбрать
    получателя для каждого конфликта. Возвращает {brand_key: Seller}
    через get_resolution().
"""

from PySide6.QtCore import Qt

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    ListWidgetFactory, LayoutFactory,
)
from ui.styles import ColorCalculator, WindowStyle

class PriorityResolutionDialog(BaseEditDialog):
    """Модальный диалог разрешения конфликтов брендов.

    Роль:
        Для каждого конфликтного brand_key пользователь выбирает
        продавца-получателя. Мастер жёсткий — reject запрещён,
        закрытие только через «Готово» → accept() → _collect_result.

    Атрибуты класса:
        LOGGER_SOURCE, LOGGER_DOMAIN — для создания логгера в
        BaseEditDialog.__init__.
    """

    LOGGER_SOURCE = "PriorityResolutionDialog.returns_dialogs"
    LOGGER_DOMAIN = "returns"

    def __init__(self, parent=None, conflicts=None,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (обычно ReturnsWindow).
            conflicts — dict {brand_key: {"raw_brand": str,
                                          "candidates": [Seller]}}.
                None → {}.
            log_manager_v2 — LogManagerV2 или None.

        Роль: сохраняет conflicts, вычисляет bg_color от
              родителя, строит каркас. Порядок ключей —
              детерминирован (sorted).
        """
        self._conflicts: dict = conflicts or {}
        self._resolution: dict = {}
        self._combos: dict = {}
        self._items: list = sorted(self._conflicts.keys())

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 25,
            g_fn=lambda g: g - 10,
            b_fn=lambda b: b + 15,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Разрешение конфликтов брендов",
            bg_color=self.bg_color,
            close_button=False,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=500,
            height=400,
            log_manager_v2=log_manager_v2,
        )

        if self.logger:
            self.logger.debug(
                f"PriorityResolutionDialog.__init__: "
                f"конфликтов {len(self._items)}"
            )

    # ---------- Переопределения ----------

    def reject(self) -> None:
        """Запрещает закрытие через Esc / программный reject.

        Вход: нет.
        Выход: нет.
        Роль: мастер жёсткий — обход только через accept() после
              выбора продавца для каждого конфликта.
        """
        pass

    def _build_content(self, layout) -> None:
        """Строит заголовок, скролл с лейблами и combo, кнопку.

        Вход: layout — QVBoxLayout из BaseEditDialog.
        Роль: при пустом conflicts ничего не строим — диалог
              всё равно не должен открываться в этом случае,
              но защита есть.
        """
        layout.addWidget(LabelFactory.create_header_label(
            self, "Выберите продавца для каждого бренда",
        ))

        if not self._items:
            return

        scroll, _, content_layout = (
            ListWidgetFactory.create_scroll_container(
                self, spacing=4, bg_color=self.bg_color,
            )
        )
        layout.addWidget(scroll)

        element_bg = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - r // 5,
            g_fn=lambda g: g - g // 5,
            b_fn=lambda b: b - b // 5,
            alpha=1.0,
        )

        for brand_key in self._items:
            info = self._conflicts[brand_key]

            raw_label = LabelFactory.create_label(
                self,
                info["raw_brand"] or brand_key,
                bg_color=(0, 0, 0, 0),
                alignment=Qt.AlignLeft | Qt.AlignVCenter,
                word_wrap=True,
            )
            content_layout.addWidget(raw_label)

            combo = InputWidgetFactory.create_combo_box(
                self,
                items=[s.name for s in info["candidates"]],
                current_index=0,
                bg_color=element_bg,
            )
            combo.currentIndexChanged.connect(
                lambda idx, k=brand_key: self._on_choice(k, idx)
            )
            content_layout.addWidget(combo)
            self._combos[brand_key] = combo

        ok_btn = ButtonFactory.create_button(
            self, "Готово", (70, 120, 90, 0.8), fixed_size=(200, 30),
        )
        ok_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, ok_btn)

    # ---------- Обработчики ----------

    def _on_choice(self, brand_key: str, index: int) -> None:
        """Debug-лог выбора продавца.

        Вход:
            brand_key — нормализованный ключ бренда.
            index — индекс выбранного combo (0..len-1).

        Роль: модель не трогаем — итог собирается в
              _collect_result при accept().
        """
        if self.logger:
            self.logger.debug(
                f"Выбран продавец для '{brand_key}': индекс {index}"
            )

    # ---------- Результат ----------

    def _collect_result(self):
        """Собирает {brand_key: Seller} по текущим индексам combo.

        Выход: None. Результат — в self._resolution.
        Роль: вызывается BaseEditDialog.accept() при нажатии
              «Готово». Индекс вне диапазона candidates —
              ключ в resolution не попадает.
        """
        resolution = {}
        for brand_key, combo in self._combos.items():
            idx = combo.currentIndex()
            candidates = self._conflicts[brand_key]["candidates"]
            if 0 <= idx < len(candidates):
                resolution[brand_key] = candidates[idx]
        self._resolution = resolution
        return None

    def get_resolution(self) -> dict:
        """Возвращает {brand_key: Seller}.

        Выход: dict. Пустой — если _collect_result не вызывался
               (например, при внешнем закрытии).
        Роль: используется KizTransferService через
              ReturnsWindow._open_priority_dialog.
        """
        return self._resolution