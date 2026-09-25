"""
Поля ввода дедлайна.

Содержит DeadlineFieldsWidget — виджет с двумя взаимозаменяемыми
формами ввода:
    «inclusive» — дата + часы + минуты.
    «duration»  — значение + единица (Часы/Дни/Месяцы).

Роль в программе:
    Переиспользуется в NewTaskDialog и DeadlineEditDialog.
    Combo выбора типа в виджет не входит — тип задаётся снаружи
    через set_mode(). Это позволяет встроить combo в другой ряд
    (например, рядом с приоритетом).
"""

from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from ui.factories.input_factory import InputWidgetFactory
from ui.factories.element_factory import LabelFactory


class DeadlineFieldsWidget(QWidget):
    """Поля ввода дедлайна: инклюзивный блок + блок срока.

    Назначение:
        Два взаимозаменяемых блока:
            «inclusive» — дата + часы + минуты.
            «duration»  — значение + единица (Часы/Дни/Месяцы).

    Роль в программе:
        Переиспользуемый виджет для диалогов задачи. Внутри сам
        переключает видимый блок через set_mode(), значения полей
        сохраняются при переключении.
    """

    def __init__(self, parent=None, initial: Optional[str] = None,
                 mode: str = "inclusive",
                 field_bg=(85, 60, 42, 0.9),
                 field_border="1px solid #6b4a33"):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            initial — строка дедлайна "%d.%m.%Y %H:%M" для
                      предзаполнения.
            mode — начальный режим: "inclusive" или "duration".
            field_bg — цвет фона полей ввода.
            field_border — CSS-рамка полей.

        Роль: цвета полей вынесены в параметры, чтобы виджет
              подходил под фон любого родительского диалога.
              DeadlineEditDialog передаёт свою палитру.
        """
        super().__init__(parent)
        self._initial = initial
        self._mode = mode
        self._field_bg = field_bg
        self._field_border = field_border
        self._build_ui()
        if initial:
            self._load_initial(initial)
        self.set_mode(mode)

    def _build_ui(self) -> None:
        """Собирает UI: два взаимозаменяемых блока.

        Роль: вызывается один раз из __init__. Создаёт оба блока
              сразу; set_mode() решает, какой видим.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl_kw = {"bg_color": (0, 0, 0, 0), "text_color": "#d4d4d4",
                  "font_size": 11}

        # --- Инклюзивный блок: дата + часы + минуты ---
        self._inclusive = QWidget()
        inc_l = QHBoxLayout(self._inclusive)
        inc_l.setContentsMargins(0, 0, 0, 0)
        inc_l.setSpacing(4)

        self._date_edit = InputWidgetFactory.create_line_edit(
            self._inclusive,
            placeholder="ДД.ММ.ГГГГ",
            bg_color=self._field_bg,
            border=self._field_border,
            border_radius=3,
            padding="3px",
            max_length=10,
        )
        # setFixedWidth — height=0 сломал бы виджет.
        self._date_edit.setFixedWidth(100)

        self._hours_spin = InputWidgetFactory.create_spin_box(
            self._inclusive, min_value=0, max_value=23, value=0,
            bg_color=self._field_bg, border=self._field_border,
            show_buttons=False,
        )
        self._hours_spin.setFixedWidth(60)

        self._minutes_spin = InputWidgetFactory.create_spin_box(
            self._inclusive, min_value=0, max_value=59, value=0,
            bg_color=self._field_bg, border=self._field_border,
            show_buttons=False,
        )
        self._minutes_spin.setFixedWidth(60)

        inc_l.addWidget(LabelFactory.create_label(
            self._inclusive, "Дата:", **lbl_kw))
        inc_l.addWidget(self._date_edit)
        inc_l.addWidget(LabelFactory.create_label(
            self._inclusive, "Час:", **lbl_kw))
        inc_l.addWidget(self._hours_spin)
        inc_l.addWidget(LabelFactory.create_label(
            self._inclusive, "Мин:", **lbl_kw))
        inc_l.addWidget(self._minutes_spin)
        inc_l.addStretch()
        layout.addWidget(self._inclusive)

        # --- Блок «Срок»: значение + единица ---
        self._duration = QWidget()
        dur_l = QHBoxLayout(self._duration)
        dur_l.setContentsMargins(0, 0, 0, 0)
        dur_l.setSpacing(4)

        self._duration_value = InputWidgetFactory.create_spin_box(
            self._duration, min_value=1, max_value=9999, value=1,
            bg_color=self._field_bg, border=self._field_border,
            show_buttons=False,
        )
        self._duration_value.setFixedWidth(80)

        self._duration_unit = InputWidgetFactory.create_combo_box(
            self._duration,
            items=["Часы", "Дни", "Месяцы"],
            current_index=1,
            bg_color=self._field_bg,
            border=self._field_border,
        )

        dur_l.addWidget(LabelFactory.create_label(
            self._duration, "Через:", **lbl_kw))
        dur_l.addWidget(self._duration_value)
        dur_l.addWidget(self._duration_unit)
        dur_l.addStretch()
        layout.addWidget(self._duration)

    def set_mode(self, mode: str) -> None:
        """Переключает режим отображения.

        Вход: mode — "inclusive" или "duration".
        Роль: показывает нужный блок, второй скрывает. Значения
              полей сохраняются — можно переключаться туда-обратно
              без потери ввода.
        """
        self._mode = mode
        self._inclusive.setVisible(mode == "inclusive")
        self._duration.setVisible(mode == "duration")

    def _load_initial(self, deadline_str: str) -> None:
        """Предзаполняет поля из строки.

        Вход: deadline_str — строка в формате "%d.%m.%Y %H:%M".
        Роль: парсит дату, кладёт в дату/часы/минуты. Если строка
              битая — молча выходим, поля остаются пустыми.
        """
        from datetime import datetime
        try:
            dt = datetime.strptime(deadline_str, "%d.%m.%Y %H:%M")
        except (ValueError, TypeError):
            return
        self._date_edit.setText(dt.strftime("%d.%m.%Y"))
        self._hours_spin.setValue(dt.hour)
        self._minutes_spin.setValue(dt.minute)

    def get_deadline_data(self, mode: Optional[str] = None) -> Optional[str]:
        """Возвращает строку дедлайна.

        Вход: mode — "inclusive" или "duration". Если None — берётся
              текущий режим виджета.

        Выход: строка "%d.%m.%Y %H:%M" или None при невалидном вводе.

        Роль: для inclusive — собирает дату + часы + минуты,
              проверяет, что дата парсится. Для duration — считает
              target = now + delta и возвращает. Невалидная дата
              → None, вызывающий код сам решает, что делать.
        """
        from datetime import datetime, timedelta
        actual_mode = mode if mode is not None else self._mode

        if actual_mode == "inclusive":
            date_str = self._date_edit.text().strip()
            h = self._hours_spin.value()
            m = self._minutes_spin.value()
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                return None
            return f"{date_str} {h:02d}:{m:02d}"

        val = self._duration_value.value()
        unit = self._duration_unit.currentText()
        if unit == "Часы":
            delta = timedelta(hours=val)
        elif unit == "Дни":
            delta = timedelta(days=val)
        else:
            # «Месяцы» условно считаем по 30 дней.
            delta = timedelta(days=val * 30)
        target = datetime.now() + delta
        return target.strftime("%d.%m.%Y %H:%M")