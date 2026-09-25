"""
Фасад стилей виджетов.

Содержит WidgetStyle — публичное API пакета ui/styles.
Методы apply_* устанавливают QSS через widget.setStyleSheet
и делегируют сборку в QssBuilder, ScrollbarStyle, WindowStyle.

Роль в программе:
    Единственная точка, с которой работают фабрики в Фазе 3.
    BaseWidgetFactory делегирует apply_common_settings сюда.
"""

from .colors import ColorCalculator
from .qss import QssBuilder
from .scrollbar import ScrollbarStyle
from .window import WindowStyle
from .selectors import SelectorBuilder


class WidgetStyle:
    """Фасад стилей.

    Назначение:
        Методы apply_* получают виджет и параметры, собирают QSS
        через QssBuilder/ScrollbarStyle/WindowStyle и вызывают
        widget.setStyleSheet.

    Роль в программе:
        Единая точка стилизации. Все фабрики в Фазе 3 используют
        только этот класс.
    """

    # ---------- Общие настройки ----------

    @staticmethod
    def apply_common(widget, object_name=None, cursor_shape=None,
                     extra_style="") -> None:
        """Применяет к виджету общие настройки.

        Вход:
            widget — целевой QWidget.
            object_name — objectName.
            cursor_shape — Qt.CursorShape.
            extra_style — дополнительный CSS-блок, добавляется
                          к уже существующему стилю виджета.

        Выход: нет.

        Роль: не заменяет styleSheet, а дополняет его. Порядок:
              objectName → cursor → extra_style.
        """
        if object_name:
            widget.setObjectName(object_name)
        if cursor_shape is not None:
            widget.setCursor(cursor_shape)
        if extra_style:
            current = widget.styleSheet()
            widget.setStyleSheet(current + extra_style)

    # ---------- Кнопки ----------

    @staticmethod
    def apply_button(btn, bg_color, text_color=None, padding="8px 16px",
                     border_radius=5, border="none", font_size=None,
                     font_family=None, font_weight=None, alignment=None,
                     hover_color=None, pressed_color=None,
                     disabled_color=None, extra_style="") -> None:
        """QSS для QPushButton.

        Вход:
            btn — QPushButton.
            bg_color — фон.
            text_color — цвет текста. None → контрастный.
            padding, border, border_radius — стиль.
            font_size, font_family, font_weight — шрифт.
            alignment — text-align.
            hover_color, pressed_color, disabled_color — цвета
                состояний. None → вычисляются автоматически.
            extra_style — дополнительный CSS.

        Выход: нет.

        Роль: единая сборка QSS кнопки. Порядок:
              базовый блок → :hover → :pressed → :disabled →
              extra_style.
        """
        bg_c = ColorCalculator.to_str(bg_color)
        text_c = ColorCalculator.text_for(bg_color, text_color)
        hover_c = hover_color if hover_color else ColorCalculator.hover(bg_color)
        pressed_c = pressed_color if pressed_color else ColorCalculator.pressed(bg_color)
        disabled_c = (disabled_color if disabled_color
                      else ColorCalculator.disabled(bg_color))

        selector = SelectorBuilder.build(
            "QPushButton", btn.objectName() or None)

        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_c,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            font_family=font_family,
            font_weight=font_weight,
            alignment=alignment,
        )

        if hover_c:
            style += QssBuilder.background_rule(
                SelectorBuilder.with_state(selector, "hover"), hover_c)

        if pressed_c:
            style += QssBuilder.background_rule(
                SelectorBuilder.with_state(selector, "pressed"), pressed_c)

        if disabled_c:
            style += QssBuilder.background_rule(
                SelectorBuilder.with_state(selector, "disabled"), disabled_c)

        if extra_style:
            style += extra_style

        btn.setStyleSheet(style)

    # ---------- Метки ----------

    @staticmethod
    def apply_label(lbl, bg_color, text_color=None, padding="4px 8px",
                    border_radius=5, border="none", font_size=None,
                    font_family=None, font_weight=None, alignment=None,
                    extra_style="") -> None:
        """QSS для QLabel.

        Вход:
            lbl — QLabel.
            bg_color — фон.
            text_color — цвет текста. None → контрастный.
            padding, border, border_radius — стиль.
            font_size, font_family, font_weight — шрифт.
            alignment — text-align.
            extra_style — дополнительный CSS.

        Выход: нет.

        Роль: единая сборка QSS меток.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)

        selector = SelectorBuilder.build("QLabel", lbl.objectName() or None)

        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            font_family=font_family,
            font_weight=font_weight,
            alignment=alignment,
        )
        if extra_style:
            style += extra_style
        lbl.setStyleSheet(style)

    # ---------- Поля ввода ----------

    @staticmethod
    def apply_line_edit(edit, bg_color, text_color=None, border="none",
                        border_radius=3, padding="3px", font_size=None,
                        font_family=None, extra_style="") -> None:
        """QSS для QLineEdit.

        Вход: edit — QLineEdit; остальные параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS поля ввода.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QLineEdit", edit.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            font_family=font_family,
        )
        if extra_style:
            style += extra_style
        edit.setStyleSheet(style)

    @staticmethod
    def apply_checkbox(cb, bg_color, text_color=None, border="none",
                       border_radius=0, padding="0px", font_size=None,
                       font_weight=None,
                       indicator_size=(16, 16),
                       indicator_bg_color=(200, 200, 200),
                       indicator_border="1px solid #888888",
                       indicator_checked_bg_color=(180, 180, 180),
                       indicator_border_radius=3,
                       extra_style="") -> None:
        """QSS для QCheckBox.

        Вход: cb — QCheckBox; параметры — стиль основного блока
              и индикатора.

        Выход: нет.
        Роль: единая сборка QSS чекбокса.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QCheckBox", cb.objectName() or None)

        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            font_weight=font_weight,
        )
        style += QssBuilder.indicator_rule(
            selector, indicator_size, indicator_bg_color,
            indicator_border, indicator_border_radius,
            indicator_checked_bg_color,
        )
        if extra_style:
            style += extra_style
        cb.setStyleSheet(style)

    @staticmethod
    def apply_combo_box(combo, bg_color, text_color=None, border="none",
                        border_radius=3, padding="3px", font_size=None,
                        font_family=None, extra_style="") -> None:
        """QSS для QComboBox.

        Вход: combo — QComboBox; параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS выпадающего списка.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QComboBox", combo.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            font_family=font_family,
        )
        if extra_style:
            style += extra_style
        combo.setStyleSheet(style)

    @staticmethod
    def apply_text_edit(te, bg_color, text_color=None, border="none",
                        border_radius=5, padding="5px", font_size=None,
                        extra_style="") -> None:
        """QSS для QTextEdit.

        Вход: te — QTextEdit; параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS многострочного поля.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QTextEdit", te.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
        )
        if extra_style:
            style += extra_style
        te.setStyleSheet(style)

    @staticmethod
    def apply_spin_box(spin, bg_color, text_color=None, border="none",
                       border_radius=5, padding="3px", font_size=None,
                       extra_props="padding-right: 20px;",
                       extra_style="") -> None:
        """QSS для QSpinBox.

        Вход: spin — QSpinBox; параметры — стиль; extra_props —
              дополнительные свойства (по умолчанию освобождает
              место под стрелки).

        Выход: нет.
        Роль: единая сборка QSS числового поля.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QSpinBox", spin.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            extra_props=extra_props,
        )
        if extra_style:
            style += extra_style
        spin.setStyleSheet(style)

    @staticmethod
    def apply_datetime_edit(dt, bg_color, text_color=None, border="none",
                            border_radius=5, padding="3px", font_size=None,
                            extra_props="padding-right: 20px;",
                            extra_style="") -> None:
        """QSS для QDateTimeEdit.

        Вход: dt — QDateTimeEdit; параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS поля даты/времени.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QDateTimeEdit", dt.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            extra_props=extra_props,
        )
        if extra_style:
            style += extra_style
        dt.setStyleSheet(style)

    @staticmethod
    def apply_date_edit(de, bg_color, text_color=None, border="none",
                        border_radius=5, padding="3px", font_size=None,
                        extra_style="") -> None:
        """QSS для QDateEdit.

        Вход: de — QDateEdit; параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS поля даты.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QDateEdit", de.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
        )
        if extra_style:
            style += extra_style
        de.setStyleSheet(style)

    # ---------- Списки и скролл-области ----------

    @staticmethod
    def apply_list_widget(lw, bg_color, text_color=None, border="none",
                          border_radius=5, padding="0px", font_size=None,
                          extra_style="") -> None:
        """QSS для QListWidget.

        Вход: lw — QListWidget; параметры — стиль.

        Выход: нет.
        Роль: единая сборка QSS списка. Добавляет ::item с
              padding=2px.
        """
        text_c = text_color if text_color is not None else ColorCalculator.text_for(bg_color)
        selector = SelectorBuilder.build("QListWidget", lw.objectName() or None)
        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            text_color=text_c,
            border=border,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
        )
        style += QssBuilder.item_rule(selector, padding="2px")
        if extra_style:
            style += extra_style
        lw.setStyleSheet(style)

    @staticmethod
    def apply_scroll_area(scroll, bg_color, border="none",
                          border_radius=0, scrollbar_width=12,
                          scrollbar_radius=6, extra_style="") -> None:
        """QSS для QScrollArea со скроллбарами.

        Вход:
            scroll — QScrollArea.
            bg_color — фон, от которого считаются цвета скроллбара.
            border, border_radius — стиль области.
            scrollbar_width, scrollbar_radius — параметры скроллбара.
            extra_style — дополнительный CSS.

        Выход: нет.

        Роль: единая сборка QSS скролл-области. Скроллбар
              подбирается автоматически через ScrollbarStyle.
              bg_property="background" — сохраняем совместимость
              с оригиналом: у QScrollArea в проекте фон задаётся
              через "background", а не "background-color".
        """
        selector = SelectorBuilder.build(
            "QScrollArea", scroll.objectName() or None)

        style = QssBuilder.base_rule(
            selector,
            bg_color=bg_color,
            border=border,
            border_radius=border_radius,
            bg_property="background",
        )
        colors = ScrollbarStyle.palette(bg_color)
        style += ScrollbarStyle.build_qss(
            colors, scrollbar_width, scrollbar_radius)
        if extra_style:
            style += extra_style
        scroll.setStyleSheet(style)

    # ---------- Окно ----------

    @staticmethod
    def apply_window_central(central, bg_color) -> None:
        """QSS для центрального виджета окна.

        Вход: central — QWidget; bg_color — фон.
        Выход: нет.
        Роль: делегирует в WindowStyle.central_widget_qss.
        """
        central.setStyleSheet(WindowStyle.central_widget_qss(bg_color))

    @staticmethod
    def apply_close_button(btn, color) -> None:
        """QSS для кнопки закрытия «✕».

        Вход: btn — QPushButton; color — цвет фона.
        Выход: нет.
        Роль: делегирует в WindowStyle.close_button_qss.
        """
        btn.setStyleSheet(WindowStyle.close_button_qss(color))