"""
Виджет CheckBox.

Содержит CheckBox — композитный чекбокс: квадратик-индикатор
плюс текстовая метка. Работает в обычном режиме (bool) и
тристейт (Qt.CheckState). Тристейт-состояние выставляется
извне через setCheckState; сигналы всегда булевы.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QSizePolicy
from ui.factories.element_factory import LabelFactory
from ui.styles import (
    ColorCalculator, IconRenderer, WidgetStyle, BackgroundResolver, SizingCalculator
)


class _CheckBoxSquare(QLabel):
    """Квадратик-индикатор внутри CheckBox.

    QLabel с pixmap. Эмитит hover_changed по enter/leave.
    Клики не перехватывает — событие уходит родителю CheckBox.
    """

    hover_changed = Signal(bool)

    def __init__(self, parent, size: int):
        """Конструктор.

        Вход:
            parent — родитель (CheckBox).
            size — логический размер стороны квадрата.
        """
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)

    def set_pixmap(self, pixmap) -> None:
        """Устанавливает pixmap."""
        self.setPixmap(pixmap)

    def enterEvent(self, event) -> None:
        """Курсор вошёл — сообщить родителю."""
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Курсор вышел — сообщить родителю."""
        self.hover_changed.emit(False)
        super().leaveEvent(event)


class CheckBox(QWidget):
    """Композитный чекбокс: квадратик + текстовая метка.

    Сигналы:
        clicked(bool) — всегда при клике (если сигналы не заблокированы).
        toggled(bool) — только при переходе Unchecked <-> Checked.
        stateChanged(int) — при любом изменении состояния.

    Состояние:
        bool (Unchecked/Checked) или тристейт (Unchecked/PartiallyChecked/
        Checked). PartiallyChecked выставляется извне через
        setCheckState; клик по нему переводит в Checked.
    """

    clicked = Signal(bool)
    toggled = Signal(bool)
    stateChanged = Signal(int)
    text_clicked = Signal()

    def __init__(self, parent, text: str, checked: bool = False,
                 position: str = "right",
                 bg_color: tuple = (255, 255, 255, 1.0),
                 square_size: int | None = None,
                 fixed_size: tuple | None = None,
                 fixed_height: int | None = None,
                 text_bg: tuple = (0, 0, 0, 0),
                 spacing: int = 6,
                 font_size: int | None = None,
                 read_only: bool = False,
                 word_wrap: bool = True,
                 text_padding: str = "1px",
                 border: str = "none"):
        """Конструктор.

        Вход:
            parent — родитель.
            text — подпись.
            checked — начальное состояние (bool).
            position — "right" или "left" — где квадрат относительно текста.
            bg_color — эффективный фон родителя (для иконки и рамки).
            square_size — размер квадрата; None → от высоты текста.
            fixed_size — фиксированный размер виджета; None → Expanding/Fixed.
            text_bg — фон текстовой метки.
            spacing — отступ между текстом и квадратом.
        """
        super().__init__(parent)
        self.bg_color = BackgroundResolver.resolve_bg_color(self, bg_color)
        self._icon_color = ColorCalculator.text_for(self.bg_color)
        self._checked = checked
        self._tristate = False
        self._check_state = Qt.Checked if checked else Qt.Unchecked
        self._hovered = False
        self._pressed = False
        self._read_only = read_only
        self._text_padding = text_padding
        self._border = border

        self._text_label = LabelFactory.create_label(
            self, text=text, bg_color=text_bg, padding=text_padding,
            font_size=font_size,
            alignment=Qt.AlignLeft | Qt.AlignVCenter, word_wrap=word_wrap,
        )
        self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._text_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        label_height = SizingCalculator.get_text_height(self._text_label, font_size)
        if square_size is None:
            widget_height = None
            if fixed_size:
                widget_height = fixed_size[1]
            elif fixed_height is not None:
                widget_height = fixed_height
            square_size = self._calc_square_size(label_height, widget_height)
        self._square_size = square_size

        self._icon_label = _CheckBoxSquare(self, square_size)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        layout.setAlignment(Qt.AlignVCenter)

        if position == "right":
            layout.addWidget(self._text_label)
            layout.addStretch(1)
            layout.addWidget(self._icon_label)
        else:
            layout.addWidget(self._icon_label)
            layout.addWidget(self._text_label)
            layout.addStretch(1)

        if fixed_size:
            self.setFixedSize(*fixed_size)
        elif fixed_height is not None:
            self.setFixedHeight(fixed_height)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._icon_label.hover_changed.connect(self._on_hover_changed)
        WidgetStyle.apply_checkbox(
            self, self.bg_color, error_color=None,
            padding=self._text_padding, square_size=self._square_size,
            border=self._border,
        )
        self._refresh_icon()

    @staticmethod
    def _calc_square_size(text_height: int, widget_height: int | None = None) -> int:
        """Вычисляет размер квадрата.

        Роль:
            Берётся 80% от высоты композита (widget_height), но
            не более 120% от высоты текста (text_height). Если
            высота композита неизвестна, отталкиваемся от текста.
            Результат — чётное число, минимум 14.
        """
        if widget_height is None:
            widget_height = text_height + 8

        size_by_height = int(widget_height * 0.8)
        max_size_by_text = int(text_height * 1.2)

        s = min(size_by_height, max_size_by_text)
        if s % 2 != 0:
            s -= 1
        return max(14, s)

    # ---------- Публичный API ----------

    def checkState(self) -> Qt.CheckState:
        """Текущее состояние (Unchecked / PartiallyChecked / Checked)."""
        return self._check_state

    def setCheckState(self, state: Qt.CheckState) -> None:
        """Программная установка состояния.

        Вход: state — Qt.CheckState (или int, приводится к enum).

        Роль: обновляет состояние и pixmap. При signalsBlocked()
              сигналы не эмитятся, но состояние и иконка
              обновляются. toggled эмитится только при переходе
              Unchecked <-> Checked; stateChanged — при любом.
        """
        if not isinstance(state, Qt.CheckState):
            state = Qt.CheckState(state)

        if state == self._check_state:
            return

        prev = self._check_state
        self._check_state = state
        self._checked = (state == Qt.Checked)
        self._refresh_icon()

        if self.signalsBlocked():
            return

        self.stateChanged.emit(state.value)
        if (prev in (Qt.Checked, Qt.Unchecked)
                and state in (Qt.Checked, Qt.Unchecked)):
            self.toggled.emit(self._checked)

    def isTristate(self) -> bool:
        """Включён ли тристейт."""
        return self._tristate

    def setTristate(self, value: bool) -> None:
        """Включает/выключает тристейт."""
        self._tristate = value

    def isChecked(self) -> bool:
        """True, если состояние Checked."""
        return self._checked

    def setChecked(self, value: bool) -> None:
        """Булева установка: True → Checked, False → Unchecked."""
        self.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def text(self) -> str:
        """Возвращает подпись чекбокса."""
        return self._text_label.text()

    def setText(self, text: str) -> None:
        """Устанавливает подпись чекбокса."""
        self._text_label.setText(text)

    def set_error_state(self, is_error: bool) -> None:

        """Устанавливает/снимает рамку ошибки.

        Вход: is_error — True → рамка через ColorCalculator.error_color;
                          False → рамка возвращается к bg_color.
        """
        if is_error:
            err = ColorCalculator.error_color(self.bg_color)
            WidgetStyle.apply_checkbox(
                self, self.bg_color, error_color=err,
                padding=self._text_padding, square_size=self._square_size,
                border=self._border,
            )
        else:
            WidgetStyle.apply_checkbox(
                self, self.bg_color, error_color=None,
                padding=self._text_padding, square_size=self._square_size,
                border=self._border,
            )

    # ---------- Обработчики мыши ----------

    def mousePressEvent(self, event) -> None:
        """Левая кнопка — включить состояние «нажат»."""
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._refresh_icon()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Левая кнопка — переключить, если курсор в пределах виджета.
        Если клик пришёлся на текстовую метку — эмитится text_clicked.
        """
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            inside = self.rect().contains(event.position().toPoint())
            self._refresh_icon()
            if inside:
                pos = event.position().toPoint()
                if self._text_label.isVisible() and self._text_label.geometry().contains(pos):
                    self.text_clicked.emit()
                else:
                    self._toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- Взаимодействие с окном ----------

    def enterEvent(self, event) -> None:
        """Курсор вошёл в виджет."""
        if not self._hovered:
            self._hovered = True
            self._refresh_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Курсор вышел из виджета."""
        if self._hovered:
            self._hovered = False
            self._refresh_icon()
        super().leaveEvent(event)

    # ---------- Внутренние ----------

    def _toggle(self) -> None:
        """Переключает состояние по клику.

        Роль:
            Тристейт: Unchecked → Checked, Checked → Unchecked,
            PartiallyChecked → Checked (Partial пропускается при
            переходе, ведёт себя как Checked).
            Обычный: Unchecked <-> Checked.
            clicked(bool) эмитится всегда при клике (если сигналы
            не заблокированы).
        """
        if self._read_only:
            return

        if self._tristate:
            if self._check_state == Qt.Checked:
                new_state = Qt.Unchecked
            else:
                new_state = Qt.Checked
        else:
            new_state = (Qt.Unchecked if self._check_state == Qt.Checked
                         else Qt.Checked)
        self.setCheckState(new_state)
        if not self.signalsBlocked():
            self.clicked.emit(self._checked)

    def _on_hover_changed(self, hovered: bool) -> None:
        """Реакция на hover квадратика."""
        if self._hovered != hovered:
            self._hovered = hovered
            self._refresh_icon()

    def _refresh_icon(self) -> None:
        """Перерисовывает иконку индикатора с учётом pressed/hover."""
        color = self._icon_color
        if self._pressed:
            color = ColorCalculator.pressed(color) or self._icon_color
        elif self._hovered:
            color = ColorCalculator.hover(color) or self._icon_color
        pixmap = IconRenderer.make_checkbox_indicator(
            self._check_state, self._square_size, color,
        )
        self._icon_label.set_pixmap(pixmap)
