"""
Диалог настройки тем задач.

Позволяет переименовывать 8 фиксированных тем (ThemeKey). Цвета и
дефолтные имена — в models/planner_task.py, здесь только UI и
сохранение diff в MainConfig по ключу "planner_themes".
"""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    LabelFactory, InputWidgetFactory, ListWidgetFactory,
    ButtonFactory, LayoutFactory,
)
from ui.styles import ColorCalculator, WindowStyle
from models.planner_task import ThemeKey


class PlannerThemesDialog(BaseEditDialog):
    """Диалог настройки тем задач."""

    LOGGER_SOURCE = "PlannerThemesDialog.planner_themes_dialog"
    LOGGER_DOMAIN = "planner"

    def __init__(self, parent, main_config, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель.
            main_config — MainConfig для чтения/записи.
            log_manager_v2 — LogManagerV2.
        """
        self._main_config = main_config
        self._editing_key: ThemeKey | None = None
        self._row_widgets: dict = {}

        raw_names = self._main_config.get("planner_themes", {})
        self._theme_names = {}
        for key in ThemeKey:
            self._theme_names[key] = ThemeKey.resolve_effective_name(
                key, raw_names
            )

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 30, 50))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r // 2,
            g_fn=lambda g: int(g // 1.5),
            b_fn=lambda b: int(b // 1.3),
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Темы задач",
            bg_color=self.bg_color,
            close_button=True,
            ok_cancel=False,
            modal=True,
            draggable=True,
            close_on_click_outside=False,
            center=True,
            width=320,
            height=460,
            log_manager_v2=log_manager_v2,
        )

        if self.logger:
            self.logger.debug(
                f"PlannerThemesDialog.__init__: режим открытия, "
                f"тем={len(ThemeKey)}"
            )

    def _build_content(self, layout) -> None:
        """Строит UI диалога."""
        # Заголовок
        layout.addWidget(LabelFactory.create_header_label(self, "Темы задач"))

        # Подсказка
        layout.addWidget(LabelFactory.create_label(
            self, "Нажмите на название, чтобы переименовать",
            bg_color=(0, 0, 0, 0), text_color=None,
            alignment=Qt.AlignCenter, word_wrap=True,
        ))

        # Скролл-контейнер
        scroll_container, _, content_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=4, bg_color=self.bg_color,
        )

        for key in ThemeKey:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(8)

            # Метка (теперь фиксированного размера)
            label = LabelFactory.create_label(
                self, self._theme_names[key],
                bg_color=key.color, text_color=None,
                clickable=True,
                on_click=lambda k=key: self._start_edit(k),
                alignment=Qt.AlignCenter,
                fixed_size=(200, 30),
            )

            # Редактор (скрыт)
            edit = InputWidgetFactory.create_default_line_edit(
                self, text=self._theme_names[key], max_length=10,
                fixed_size=(200, 30), bg_color=key.color,
            )
            edit.setVisible(False)
            edit.installEventFilter(self)

            # Подключение сигналов
            edit.returnPressed.connect(lambda k=key: self._finish_edit(k, commit=True))
            edit.editingFinished.connect(lambda k=key: self._finish_edit(k, commit=True))

            # Центрируем элементы в строке
            row_layout.addStretch()
            row_layout.addWidget(label)
            row_layout.addWidget(edit)
            row_layout.addStretch()
            self._row_widgets[key] = {"label": label, "edit": edit}

            content_layout.addWidget(row_widget)

        layout.addWidget(scroll_container)

        # Кнопка Сохранить
        save_btn = ButtonFactory.create_button(
            self, "Сохранить", bg_color=(70, 120, 90, 0.8),
        )
        save_btn.clicked.connect(self.accept)
        LayoutFactory.add_centered_widget(layout, save_btn)

    def _start_edit(self, key: ThemeKey) -> None:
        """Переключает строку в режим редактирования.

        Вход: key — тема для редактирования.
        """
        if self._editing_key is not None and self._editing_key != key:
            self._finish_edit(self._editing_key, commit=True)

        if self._editing_key == key:
            return

        row = self._row_widgets[key]
        row["label"].setVisible(False)
        row["edit"].setVisible(True)
        row["edit"].setFocus()
        row["edit"].selectAll()
        self._editing_key = key

    def _finish_edit(self, key: ThemeKey, commit: bool) -> None:
        """Завершает редактирование.

        Вход:
            key — тема.
            commit — True при сохранении, False при отмене (Esc).
        """
        if self._editing_key != key:
            return

        row = self._row_widgets[key]

        if commit:
            text = row["edit"].text().strip()
            old = self._theme_names[key]

            if not text or len(text) > 10:
                self._theme_names[key] = key.default_name
            else:
                self._theme_names[key] = text

            row["label"].setText(self._theme_names[key])
            if self.logger and old != self._theme_names[key]:
                self.logger.debug(
                    f"Переименование: {key.value} → "
                    f"{self._theme_names[key]!r}"
                )

        row["edit"].setVisible(False)
        row["label"].setVisible(True)
        self._editing_key = None

    def eventFilter(self, obj, event) -> bool:
        """Обрабатывает нажатие Esc в редакторе."""
        if (event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape
                and self._editing_key is not None
                and obj is self._row_widgets[self._editing_key]["edit"]):
            self._finish_edit(self._editing_key, commit=False)
            event.accept()
            return True

        return super().eventFilter(obj, event)

    def _validate(self) -> bool:
        """Валидация перед сохранением."""
        if self._editing_key is not None:
            self._finish_edit(self._editing_key, commit=True)
        return True

    def _collect_result(self):
        """Сохраняет diff в MainConfig."""
        diff = ThemeKey.build_diff(self._theme_names)
        try:
            self._main_config.set("planner_themes", diff)
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"Ошибка сохранения тем: {e}",
                    can_influence=False,
                )
            return None

        if self.logger:
            self.logger.debug(
                f"Сохранение: diff={len(diff)} переименований"
            )
        return None