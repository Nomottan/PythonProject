"""
Виджет выбора чисел месяца.

Сетка 7×5 кнопок 36×36, превью выбранных чисел. Переиспользуемый
компонент: используется в PlannerDayPickerDialog и может быть
встроен в другие формы.
"""

from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout,
)
from PySide6.QtCore import Qt, Signal

from ui.factories.factories import ButtonFactory, LabelFactory


class PlannerDayPickerWidget(QWidget):
    """Виджет выбора чисел месяца.

    Назначение:
        Сетка кнопок 1–31, подсветка выбранных, превью снизу.
        Каждый клик переключает число и эмитит selection_changed.

    Роль в программе:
        Встраивается в PlannerDayPickerDialog. Логика «спросить
        про 29/30/31» вынесена в диалог-обёртку — виджет только
        собирает выбор.

    Сигналы:
        selection_changed(list) — список выбранных чисел.
    """

    selection_changed = Signal(list)

    def __init__(self, parent=None, selected=None):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            selected — список предвыбранных чисел (1–31).

        Роль: строит сетку 7×5, превью, вызывает _refresh_grid
              для начальной подсветки.
        """
        super().__init__(parent)
        self._selected = list(selected or [])

        # Вертикальная компоновка: сетка + превью.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # --- Сетка кнопок ---
        grid_widget = QWidget()
        grid_layout = QGridLayout(grid_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(4)

        self._day_buttons = {}
        for day in range(1, 32):
            row = (day - 1) // 7
            col = (day - 1) % 7
            btn = ButtonFactory.create_button(
                grid_widget, str(day), bg_color=(50, 60, 70, 0.95),
                fixed_size=(36, 36), padding="0px", font_size=12,
            )
            btn.clicked.connect(
                lambda checked=False, d=day: self._on_day_clicked(d)
            )
            grid_layout.addWidget(btn, row, col)
            self._day_buttons[day] = btn
        layout.addWidget(grid_widget)

        # --- Превью выбранных чисел ---
        self._preview_label = LabelFactory.create_label(
            self, "", bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignCenter, font_size=11, word_wrap=True,
        )
        layout.addWidget(self._preview_label)

        self._refresh_grid()

    # ---------- Публичный API ----------

    def get_selected(self) -> list:
        """Возвращает отсортированный список выбранных чисел."""
        return sorted(self._selected)

    def set_selected(self, selected: list) -> None:
        """Устанавливает выбранные числа и обновляет подсветку.

        Вход: selected — список чисел 1–31.
        """
        self._selected = list(selected or [])
        self._refresh_grid()

    # ---------- Внутренние ----------

    def _on_day_clicked(self, day: int) -> None:
        """Переключает выбранность числа.

        Вход: day — число 1–31.
        Роль: добавляет/убирает из _selected, обновляет подсветку,
              эмитит selection_changed.
        """
        if day in self._selected:
            self._selected.remove(day)
        else:
            self._selected.append(day)
        self._refresh_grid()
        self.selection_changed.emit(self.get_selected())

    def _refresh_grid(self) -> None:
        """Обновляет подсветку кнопок и превью.

        Роль: выбранные кнопки — голубые, невыбранные — тёмные.
              Превью показывает отсортированный список.
        """
        for day, btn in self._day_buttons.items():
            if day in self._selected:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(80, 160, 220, 1.0);
                        color: #ffffff;
                        border: none;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(50, 60, 70, 0.95);
                        color: #d4d4d4;
                        border: 1px solid #3a4556;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: rgba(70, 80, 90, 0.95);
                    }
                """)
        text = (
            ", ".join(str(d) for d in sorted(self._selected))
            if self._selected else "—"
        )
        self._preview_label.setText(f"Выбрано: {text}")