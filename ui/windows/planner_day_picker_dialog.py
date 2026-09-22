"""
Диалог выбора чисел месяца для правила «Определённые числа».

Сетка 7×5 с плитками 36×36, превью выбранных чисел.
Вопрос про 29/30/31 задаётся внутри _on_ok.
"""

from PySide6.QtWidgets import (
    QDialog, QWidget, QGridLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.factories.factories import ButtonFactory, LabelFactory
from ui.factories.window_factories import ExtendedWindowFactory
from ui.windows.message_dialog import MessageDialog

class PlannerDayPickerDialog(QDialog):
    """Диалог выбора чисел месяца.

    Назначение:
        Позволяет выбрать числа 1–31. Если выбраны 29/30/31 — при «ОК»
        спрашивает, использовать ли последний день месяца, когда
        выбранного числа нет.

    Роль в программе:
        Открывается из PlannerRecurrenceFieldsWidget.
    """

    def __init__(self, parent=None, selected=None):
        """Конструктор.

        Вход: parent — родитель; selected — список предвыбранных чисел.
        """
        super().__init__(parent)
        self._selected = list(selected or [])
        self._use_last_day = False

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Выберите числа месяца",
            bg_color=(70, 80, 90, 0.95),
            close_button=False,
            ok_cancel=True,
            ok_callback=self._on_ok,
            cancel_callback=self.reject,
            draggable=True,
            return_content_layout=True,
            default_width=420,
            default_height=400,
        )

        content_layout.addWidget(LabelFactory.create_header_label(
            self, "Выберите числа месяца"
        ))

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
        content_layout.addWidget(grid_widget)

        self._preview_label = LabelFactory.create_label(
            self, "", bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignCenter, font_size=11, word_wrap=True,
        )
        content_layout.addWidget(self._preview_label)

        self._refresh_grid()

    def _on_day_clicked(self, day: int) -> None:
        """Переключает выбранность числа."""
        if day in self._selected:
            self._selected.remove(day)
        else:
            self._selected.append(day)
        self._refresh_grid()

    def _refresh_grid(self) -> None:
        """Обновляет подсветку кнопок и превью."""
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
        text = (", ".join(str(d) for d in sorted(self._selected))
                if self._selected else "—")
        self._preview_label.setText(f"Выбрано: {text}")

    def _on_ok(self) -> None:
        """При «ОК» — вопрос про 29/30/31."""
        if any(d in (29, 30, 31) for d in self._selected):
            reply = MessageDialog.question(
                self,
                "В некоторых месяцах недостаточно дней. "
                "Выбирать последнюю дату в них?",
                title_text="Последний день",
                bg_color=(70, 80, 90),
            )
            self._use_last_day = (reply == QDialog.Accepted)
        self.accept()

    def get_selected(self) -> list:
        """Возвращает отсортированный список выбранных чисел."""
        return sorted(self._selected)

    def get_use_last_day(self) -> bool:
        """Возвращает флаг «использовать последний день»."""
        return self._use_last_day