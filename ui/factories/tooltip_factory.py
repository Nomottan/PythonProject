"""
Фабрика tooltip-подсказок.

Содержит TooltipFactory — единую точку создания QLabel-подсказок.
Стилизация — через WidgetStyle.apply_tooltip, как у других фабрик.
"""

from PySide6.QtCore import Qt, QPoint, QObject, QEvent
from PySide6.QtGui import QCursor

from ui.factories.base_factory import BaseWidgetFactory
from ui.factories.element_factory import LabelFactory
from ui.styles import WidgetStyle, ColorCalculator

class TooltipHoverFilter(QObject):
    """Фильтр наведения для tooltip-подсказок.

    Назначение:
        Универсальный QObject-фильтр: вызывает переданный
        обработчик для событий, не зная про конкретный диалог.

    Роль в программе:
        Живёт рядом с TooltipFactory, чтобы диалоги не
        определяли собственные фильтры и не зависели от MRO.
    """

    def __init__(self, parent, handler):
        """Конструктор.

        Вход:
            parent — QObject-родитель (обычно диалог).
            handler — callable(obj, event) -> bool.
        """
        super().__init__(parent)
        self._handler = handler

    def eventFilter(self, obj, event) -> bool:
        """Делегирует событие обработчику."""
        return self._handler(obj, event)

class TooltipController(QObject):
    """Управляет tooltip-подсказками для набора виджетов.

    Хранит текст по каждому виджету, активный tooltip и фон.
    Диалог только говорит: «у этого поля такая ошибка» или
    «очистить ошибки». Показ/скрытие — внутри контроллера.
    """

    def __init__(self, parent, bg_color, logger=None):
        """Конструктор.

        Вход:
            parent — QObject-родитель (обычно диалог).
            bg_color — фон подсказки.
            logger — LoggerV2 или None.
        """
        super().__init__(parent)
        self._parent = parent
        self._bg_color = bg_color
        self._logger = logger
        self._texts = {}
        self._active_tooltip = None
        self._filter = TooltipHoverFilter(self, self._handle_event)

    def install(self, widget) -> None:
        """Ставит фильтр наведения на виджет."""
        widget.installEventFilter(self._filter)
        if self._logger is not None:
            self._logger.debug(
                "tooltip install: "
                f"{type(widget).__name__}, "
                f"id={id(widget)}, "
                f"object={widget.objectName()!r}"
            )

    def set_text(self, widget, text: str) -> None:
        """Задаёт текст ошибки для виджета."""
        if text:
            self._texts[widget] = text
        else:
            self._texts.pop(widget, None)

    def clear(self) -> None:
        """Скрывает активный tooltip и очищает все тексты."""
        self.hide()
        self._texts.clear()

    def hide(self) -> None:
        """Скрывает активный tooltip."""
        if self._active_tooltip is not None:
            self._active_tooltip.hide()
            self._active_tooltip.deleteLater()
            self._active_tooltip = None

    def _handle_event(self, obj, event) -> bool:
        """Обрабатывает Enter/Leave для показа и скрытия tooltip."""
        if event.type() == QEvent.Enter:
            text = self._texts.get(obj)
            if self._logger is not None:
                self._logger.debug(
                    "tooltip enter text: "
                    f"text={text!r}, "
                    f"active={self._active_tooltip is not None}"
                )
            if text and self._active_tooltip is None:
                if self._logger is not None:
                    self._logger.debug(
                        "tooltip create input: "
                        f"text={text!r}, bg={self._bg_color!r}"
                    )
                self._active_tooltip = TooltipFactory.create_tooltip(
                    self._parent, text, self._bg_color,
                )
                if self._logger is not None:
                    tooltip = self._active_tooltip
                    self._logger.debug(
                        "\ntooltip create output: "
                        f"\nvisible={tooltip.isVisible()}, "
                        f"\nsize={tooltip.size()}, "
                        f"\nhint={tooltip.sizeHint()}, "
                        f"\nflags={int(tooltip.windowFlags())}, "
                        f"\nobject={tooltip.objectName()!r}, "
                        f"\nstyled_bg={tooltip.testAttribute(Qt.WA_StyledBackground)}, "
                        f"\ntranslucent={tooltip.testAttribute(Qt.WA_TranslucentBackground)}, "
                        f"\nstyle={tooltip.styleSheet()!r}\n"
                    )
                TooltipFactory.show_tooltip(self._active_tooltip)
                if self._logger is not None:
                    tooltip = self._active_tooltip
                    self._logger.debug(
                        "tooltip shown: "
                        f"visible={tooltip.isVisible()}, "
                        f"geom={tooltip.geometry()}, "
                        f"flags={int(tooltip.windowFlags())}"
                    )
        elif event.type() == QEvent.Leave:
            if self._logger is not None:
                self._logger.debug("tooltip leave")
            self.hide()
        return False

class TooltipFactory(BaseWidgetFactory):
    """Фабрика tooltip-подсказок.

    Назначение:
        Создаёт QLabel с флагами Qt.ToolTip, прозрачным для мыши
        и без активации. Текст — plain text, стиль — через
        WidgetStyle.apply_tooltip.

    Роль в программе:
        Все tooltip в проекте создаются здесь. Диалог управляет
        показом/скрытием и позицией, фабрика — только создание
        и стилизация.
    """

    @staticmethod
    def create_tooltip(parent, text: str, bg_color, text_color=None):
        """Создаёт стилизованную tooltip-подсказку.

        Вход:
            parent — родительское окно.
            text — текст подсказки.
            bg_color — фон подсказки.
            text_color — цвет текста; None → контрастный.

        Выход:
            QLabel с флагами Qt.ToolTip.

        Роль:
            Единая точка создания tooltip. QLabel создаётся через
            LabelFactory, затем накладывается tooltip-стиль через
            WidgetStyle.apply_tooltip. Виджет скрыт по умолчанию:
            показ и позиционирование — через show_tooltip.
        """
        tooltip = LabelFactory.create_label(
            parent,
            text=text or "",
            bg_color=(0, 0, 0, 0),
            text_color=text_color,
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            object_name="tooltip_label",
        )
        tooltip.setWindowFlags(
            Qt.ToolTip | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        tooltip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        tooltip.setAttribute(Qt.WA_ShowWithoutActivating, True)
        tooltip.setAttribute(Qt.WA_TranslucentBackground, False)
        tooltip.setAttribute(Qt.WA_StyledBackground, True)
        tooltip.setTextFormat(Qt.PlainText)

        tooltip_bg = ColorCalculator.element_bg_for(
            bg_color, r_div=2, g_div=2, b_div=2, divisor=10,
        )
        r, g, b = tooltip_bg[:3]
        tooltip_bg = (r, g, b, 1.0)
        border_color = ColorCalculator.element_bg_for(
            tooltip_bg, r_div=3, g_div=3, b_div=3, divisor=10,
        )
        border = f"1px solid {ColorCalculator.to_str(border_color)}"

        WidgetStyle.apply_tooltip(
            tooltip,
            tooltip_bg,
            text_color=text_color,
            border=border,
        )
        tooltip.ensurePolished()
        tooltip.adjustSize()
        hint = tooltip.sizeHint()
        tooltip.setFixedSize(
            max(1, hint.width()),
            max(1, hint.height()),
        )
        return tooltip

    @staticmethod
    def show_tooltip(tooltip, offset: QPoint = None) -> None:
        """Показывает tooltip рядом с курсором и поднимает его.

        Вход:
            tooltip — QLabel из create_tooltip.
            offset — смещение от курсора; None → QPoint(12, 12).

        Выход: нет.

        Роль:
            Единая точка показа: сама считает глобальную позицию
            курсора, чтобы вызывающий код не импортировал QCursor.
            move → show → raise_; raise_ нужен, чтобы tooltip
            не ушёл под модальное окно.
        """
        if offset is None:
            offset = QPoint(12, 12)
        tooltip.move(QCursor.pos() + offset)
        tooltip.show()
        tooltip.raise_()