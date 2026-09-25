"""
Фабрика полей ввода.

Содержит InputWidgetFactory — единая точка создания полей ввода
(QLineEdit, QCheckBox, QComboBox, QTextEdit, QSpinBox,
QDateTimeEdit, QDateEdit).

QSS собирается через ui.styles.WidgetStyle.apply_*. Класс
не наследует BaseWidgetFactory.
"""

from PySide6.QtCore import QDateTime, QDate
from PySide6.QtWidgets import (
    QLineEdit, QCheckBox, QComboBox, QTextEdit, QSpinBox,
    QDateTimeEdit, QAbstractSpinBox, QDateEdit,
)

from ui.styles import WidgetStyle


class InputWidgetFactory:
    """Фабрика для создания полей ввода.

    Роль: единая точка создания полей ввода. Все методы
          делегируют QSS в WidgetStyle.apply_*.

    Публичный API:
        create_line_edit, create_checkbox, create_combo_box,
        create_default_line_edit, create_text_edit,
        create_spin_box, create_datetime_edit, create_date_edit.
    """

    @staticmethod
    def create_line_edit(parent, text="", placeholder="",
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=3,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         read_only=False, max_length=None,
                         alignment=None, font_size=None, font_family=None,
                         extra_style="", min_size=None, max_size=None):
        """Создаёт однострочное текстовое поле.

        Вход:
            parent — родитель.
            text — начальный текст.
            placeholder — подсказка при пустом поле.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, min_size, max_size — размеры.
            object_name, cursor_shape — общие настройки.
            read_only — только для чтения.
            max_length — максимальная длина.
            alignment — выравнивание текста.
            font_size, font_family — шрифт.
            extra_style — доп. CSS.

        Выход: QLineEdit с QSS.
        """
        line_edit = QLineEdit(text, parent)

        if object_name:
            line_edit.setObjectName(object_name)
        if cursor_shape is not None:
            line_edit.setCursor(cursor_shape)
        if read_only:
            line_edit.setReadOnly(True)
        if max_length:
            line_edit.setMaxLength(max_length)
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        if alignment is not None:
            line_edit.setAlignment(alignment)
        if fixed_size:
            line_edit.setFixedSize(*fixed_size)
        if min_size:
            line_edit.setMinimumSize(*min_size)
        if max_size:
            line_edit.setMaximumSize(*max_size)

        WidgetStyle.apply_line_edit(
            line_edit, bg_color, text_color, border, border_radius,
            padding, font_size, font_family, extra_style,
        )
        return line_edit

    @staticmethod
    def create_checkbox(parent, text, checked=False,
                        bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                        border="none", border_radius=0, padding="0px",
                        fixed_size=None, object_name=None, cursor_shape=None,
                        font_size=None, font_weight=None,
                        extra_style="", tooltip=None,
                        indicator_size=(16, 16),
                        indicator_bg_color=(200, 200, 200),
                        indicator_border="1px solid #888888",
                        indicator_checked_bg_color=(180, 180, 180),
                        indicator_border_radius=3):
        """Создаёт стилизованный QCheckBox.

        Вход:
            parent — родитель.
            text — подпись рядом с чекбоксом.
            checked — начальное состояние.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            font_size, font_weight — шрифт.
            extra_style — доп. CSS.
            tooltip — подсказка.
            indicator_size — (w, h) квадратика-индикатора.
            indicator_bg_color — фон индикатора в обычном состоянии.
            indicator_border — рамка индикатора.
            indicator_checked_bg_color — фон индикатора в отмеченном.
            indicator_border_radius — скругление индикатора.

        Выход: QCheckBox с QSS.
        """
        checkbox = QCheckBox(text, parent)
        checkbox.setChecked(checked)

        if object_name:
            checkbox.setObjectName(object_name)
        if cursor_shape is not None:
            checkbox.setCursor(cursor_shape)
        if tooltip:
            checkbox.setToolTip(tooltip)
        if fixed_size:
            checkbox.setFixedSize(*fixed_size)

        WidgetStyle.apply_checkbox(
            checkbox, bg_color, text_color, border, border_radius,
            padding, font_size, font_weight,
            indicator_size, indicator_bg_color, indicator_border,
            indicator_checked_bg_color, indicator_border_radius,
            extra_style,
        )
        return checkbox

    @staticmethod
    def create_combo_box(parent, items=None, current_index=0,
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=3,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         font_size=None, font_family=None,
                         extra_style="", tooltip=None):
        """Создаёт стилизованный QComboBox.

        Вход:
            parent — родитель.
            items — список строк для addItems.
            current_index — индекс выбранного по умолчанию.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            font_size, font_family — шрифт.
            extra_style, tooltip — доп. CSS и подсказка.

        Выход: QComboBox.
        """
        combo = QComboBox(parent)
        if items:
            combo.addItems(items)
            combo.setCurrentIndex(current_index)

        if object_name:
            combo.setObjectName(object_name)
        if cursor_shape is not None:
            combo.setCursor(cursor_shape)
        if tooltip:
            combo.setToolTip(tooltip)
        if fixed_size:
            combo.setFixedSize(*fixed_size)

        WidgetStyle.apply_combo_box(
            combo, bg_color, text_color, border, border_radius,
            padding, font_size, font_family, extra_style,
        )
        return combo

    @staticmethod
    def create_default_line_edit(parent, text="", **kwargs):
        """Создаёт QLineEdit с тёмным стилем по умолчанию.

        Вход:
            parent — родитель.
            text — начальный текст.
            **kwargs — дополнительные параметры в create_line_edit.

        Выход: QLineEdit.
        """
        return InputWidgetFactory.create_line_edit(
            parent,
            text=text,
            bg_color=(60, 50, 70, 0.9),
            text_color="#d4d4d4",
            border="1px solid #5a4a5c",
            border_radius=3,
            padding="3px",
            **kwargs
        )

    @staticmethod
    def create_text_edit(parent, text="", placeholder="",
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=5,
                         padding="5px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         read_only=False, font_size=None, extra_style="",
                         enabled=True):
        """Создаёт стилизованный QTextEdit.

        Вход:
            parent — родитель.
            text — начальный текст.
            placeholder — подсказка при пустом поле.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            read_only — только для чтения.
            font_size — размер шрифта.
            extra_style — доп. CSS.
            enabled — включён ли виджет.

        Выход: QTextEdit.
        """
        te = QTextEdit(parent)
        if text:
            te.setPlainText(text)
        if placeholder:
            te.setPlaceholderText(placeholder)
        if object_name:
            te.setObjectName(object_name)
        if cursor_shape is not None:
            te.setCursor(cursor_shape)
        if read_only:
            te.setReadOnly(True)
        if fixed_size:
            te.setFixedSize(*fixed_size)
        te.setEnabled(enabled)

        WidgetStyle.apply_text_edit(
            te, bg_color, text_color, border, border_radius,
            padding, font_size, extra_style,
        )
        return te

    @staticmethod
    def create_spin_box(parent, min_value=0, max_value=999, value=0,
                        prefix="", suffix="",
                        bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                        border="1px solid #5a4a5c", border_radius=5,
                        padding="3px", fixed_size=None,
                        object_name=None, cursor_shape=None,
                        font_size=None, extra_style="", show_buttons=True):
        """Создаёт стилизованный QSpinBox.

        Вход:
            parent — родитель.
            min_value, max_value, value — диапазон и значение.
            prefix, suffix — префикс/суффикс значения.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            font_size — размер шрифта.
            extra_style — доп. CSS.
            show_buttons — показывать ли стрелки вверх/вниз.

        Выход: QSpinBox.
        """
        spin = QSpinBox(parent)
        spin.setRange(min_value, max_value)
        spin.setValue(value)
        spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        if not show_buttons:
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        if prefix:
            spin.setPrefix(prefix)
        if suffix:
            spin.setSuffix(suffix)
        if object_name:
            spin.setObjectName(object_name)
        if cursor_shape is not None:
            spin.setCursor(cursor_shape)
        if fixed_size:
            spin.setFixedSize(*fixed_size)

        WidgetStyle.apply_spin_box(
            spin, bg_color, text_color, border, border_radius,
            padding, font_size, extra_style=extra_style,
        )
        return spin

    @staticmethod
    def create_datetime_edit(parent, value=None,
                             bg_color=(60, 50, 70, 0.9),
                             text_color="#d4d4d4",
                             border="1px solid #5a4a5c", border_radius=5,
                             padding="3px", fixed_size=None,
                             object_name=None, cursor_shape=None,
                             font_size=None, extra_style=""):
        """Создаёт стилизованный QDateTimeEdit.

        Вход:
            parent — родитель.
            value — QDateTime начальное. None → текущий момент.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            font_size — размер шрифта.
            extra_style — доп. CSS.

        Выход: QDateTimeEdit.
        """
        dt = QDateTimeEdit(parent)
        dt.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        if value is not None:
            dt.setDateTime(value)
        else:
            dt.setDateTime(QDateTime.currentDateTime())
        if object_name:
            dt.setObjectName(object_name)
        if cursor_shape is not None:
            dt.setCursor(cursor_shape)
        if fixed_size:
            dt.setFixedSize(*fixed_size)

        WidgetStyle.apply_datetime_edit(
            dt, bg_color, text_color, border, border_radius,
            padding, font_size, extra_style=extra_style,
        )
        return dt

    @staticmethod
    def create_date_edit(parent, value=None,
                         bg_color=(60, 50, 70, 0.9),
                         text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=5,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         font_size=None, extra_style="",
                         display_format="dd.MM.yyyy"):
        """Создаёт стилизованный QDateEdit.

        Вход:
            parent — родитель.
            value — QDate начальное. None → текущая дата.
            bg_color, text_color, border, border_radius, padding — стиль.
            fixed_size, object_name, cursor_shape — общие настройки.
            font_size — размер шрифта.
            extra_style — доп. CSS.
            display_format — формат отображения (по умолчанию дд.мм.гггг).

        Выход: QDateEdit.
        """
        de = QDateEdit(parent)
        if value is None:
            value = QDate.currentDate()
        de.setDate(value)
        de.setDisplayFormat(display_format)

        if object_name:
            de.setObjectName(object_name)
        if cursor_shape is not None:
            de.setCursor(cursor_shape)
        if fixed_size:
            de.setFixedSize(*fixed_size)

        WidgetStyle.apply_date_edit(
            de, bg_color, text_color, border, border_radius,
            padding, font_size, extra_style,
        )
        return de