"""
Базовый предок диалогов сообщений.

Содержит класс BaseMessageDialog — общий предок для MessageDialog
и NotificationDialog: расчёт цветов от фона родителя, стилизация
фона и обводки, создание лейбла и заголовка, перетаскивание.

Роль в программе:
    Не используется напрямую. Наследники переопределяют:
        _is_modal() -> bool — модальность (для WindowManager).
        _build_content(layout) — дополнительный контент
            (например, кнопки в MessageDialog).

    Флаги окна, модальность и геометрия делегируются WindowManager
    при register_window. База не ставит setWindowFlags и
    setWindowModality — это забота менеджера.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout

from ui.factories.factories import LabelFactory, BaseWidgetFactory
from ui.styles import ColorCalculator


class BaseMessageDialog(QDialog):
    """Общий предок для диалогов сообщений.

    Назначение:
        Содержит всё, что одинаково у MessageDialog и NotificationDialog:
        расчёт цветов от фона родителя, стилизацию фона и обводки,
        создание лейбла и заголовка, перетаскивание.

    Роль в программе:
        Не используется напрямую. Наследники переопределяют поведение
        окна (_is_modal) и предоставляют свои точки входа.

    Флаги окна, модальность и геометрия делегируются WindowManager
    при register_window. База не ставит setWindowFlags и
    setWindowModality.
    """

    def __init__(self, parent=None, text: str = "",
                 title_text: str = None,
                 bg_color: tuple = None,
                 min_size: tuple = None,
                 draggable: bool = True,
                 border_color_override: tuple = None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            text — текст сообщения (единственный элемент содержимого).
            title_text — опциональный заголовок.
            bg_color — опциональный фон родителя (иначе ищется у parent).
            min_size — минимальный размер (w, h).
            draggable — разрешить перетаскивание. По умолчанию True.
            border_color_override — переопределить цвет обводки.

        Роль: вычисляет цвета, создаёт содержимое, подключает dragging,
              регистрирует окно в WindowManager (если у parent есть
              window_manager). Модальность ставит WindowManager
              по _is_modal() наследника.
        """
        super().__init__(parent)

        self._parent_bg = self._resolve_parent_bg(parent, bg_color)
        self._dialog_bg = self._calc_dialog_bg(self._parent_bg)
        self._border_color = (
            border_color_override
            or self._calc_dialog_border(self._parent_bg)
        )

        self._setup_ui(text, title_text, min_size)

        if draggable:
            self._setup_dragging()

        # Регистрация в WindowManager: модальность — по типу
        # наследника (MessageDialog → True, NotificationDialog → False).
        modal_flag = self._is_modal()
        if parent is not None and hasattr(parent, "window_manager"):
            parent.window_manager.register_window(
                self, parent=parent, fill_parent=False, modal=modal_flag,
            )

    # ---------- Расчёт цветов (общие) ----------

    @staticmethod
    def _resolve_parent_bg(parent, bg_color) -> tuple:
        """Возвращает bg_color: аргумент → parent.bg_color → parent.window().bg_color → fallback.

        Вход: parent — родительское окно; bg_color — явный цвет или None.
        Выход: кортеж (r, g, b, a).
        Роль: единая точка поиска фона родителя. Fallback — (64, 48, 66, 0.8).
        """
        if bg_color is not None:
            return bg_color
        if parent is not None:
            if hasattr(parent, "bg_color"):
                return parent.bg_color
            top = parent.window()
            if top is not None and hasattr(top, "bg_color"):
                return top.bg_color
        return (64, 48, 66, 0.8)

    @staticmethod
    def _calc_dialog_bg(parent_bg: tuple) -> tuple:
        """Фон диалога: +60/−60 от родителя, alpha 0.95."""
        r, g, b = parent_bg[:3]
        avg = (r + g + b) // 3
        shift = 60 if avg <= 128 else -60

        return (
            ColorCalculator.clamp(r + shift),
            ColorCalculator.clamp(g + shift),
            ColorCalculator.clamp(b + shift),
            0.95,
        )

    @staticmethod
    def _calc_dialog_border(parent_bg: tuple) -> tuple:
        """Обводка: красноватая, +40+20+20 / −20−40−40, alpha 0.9."""
        r, g, b = parent_bg[:3]
        avg = (r + g + b) // 3

        if avg <= 128:
            return (
                ColorCalculator.clamp(r + 40),
                ColorCalculator.clamp(g + 20),
                ColorCalculator.clamp(b + 20),
                0.9,
            )
        return (
            ColorCalculator.clamp(r - 20),
            ColorCalculator.clamp(g - 40),
            ColorCalculator.clamp(b - 40),
            0.9,
        )

    def _calc_button_bg(self) -> tuple:
        """Цвет кнопок — производный от фона диалога."""
        r, g, b = self._dialog_bg[:3]
        avg = (r + g + b) // 3
        shift = 25 if avg <= 128 else -25

        return (
            ColorCalculator.clamp(r + shift),
            ColorCalculator.clamp(g + shift),
            ColorCalculator.clamp(b + shift),
            0.9,
        )

    # ---------- Сборка UI ----------

    def _setup_ui(self, text, title_text, min_size) -> None:
        """Строит содержимое: фон с обводкой, опциональный заголовок, лейбл."""
        central = QWidget()
        central.setObjectName("message_dialog_root")
        bg_c = BaseWidgetFactory.color_to_str(self._dialog_bg)
        border_c = BaseWidgetFactory.color_to_str(self._border_color)
        central.setStyleSheet(f"""
                    QWidget#message_dialog_root {{
                        background-color: {bg_c};
                        border: 2px solid {border_c};
                        border-radius: 10px;
                    }}
                """)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        if title_text:
            layout.addWidget(
                LabelFactory.create_header_label(self, title_text)
            )

        text_color = BaseWidgetFactory.calc_text_color(self._dialog_bg)
        label = LabelFactory.create_label(
            self, text=text, bg_color=(0, 0, 0, 0),
            text_color=text_color, word_wrap=True,
            alignment=Qt.AlignCenter,
        )
        layout.addWidget(label)

        self._build_content(layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(central)

        if min_size:
            self.setMinimumSize(*min_size)
        else:
            self.setMinimumSize(320, 180)

        self.adjustSize()

    # ---------- Хуки для наследников ----------

    def _is_modal(self) -> bool:
        """Модален ли диалог. Переопределяется в наследниках.

        Выход: True — WindowModal; False — NonModal.
        Роль: WindowManager.register_window ставит модальность
              по этому флагу. MessageDialog → True,
              NotificationDialog → False.
        """
        raise NotImplementedError(
            "Наследник должен реализовать _is_modal"
        )

    def _build_content(self, layout) -> None:
        """Добавляет содержимое после лейбла. По умолчанию — ничего.

        Вход: layout — QVBoxLayout внутри центрального виджета.
        Роль: точка расширения. MessageDialog добавляет сюда кнопки.
        """
        pass

    def _setup_dragging(self) -> None:
        """Перетаскивание за центральный виджет."""
        def mousePressEvent(event):
            if event.button() == Qt.LeftButton:
                self._drag_pos = (
                    event.globalPosition().toPoint()
                    - self.frameGeometry().topLeft()
                )
                event.accept()

        def mouseMoveEvent(event):
            if hasattr(self, "_drag_pos") and event.buttons() & Qt.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()

        central = self.findChild(QWidget)
        if central:
            central.mousePressEvent = mousePressEvent
            central.mouseMoveEvent = mouseMoveEvent