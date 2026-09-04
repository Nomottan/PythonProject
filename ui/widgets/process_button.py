
# ui/widgets/process_button.py
from enum import Enum, auto
from typing import Callable, Tuple
from PySide6.QtWidgets import QPushButton

from utils.logger import ILogger


class ButtonState(Enum):
    """Состояния кнопки процесса."""
    GRAY = auto()
    ACTIVE = auto()
    EXECUTED = auto()
    LOCKED = auto()


class ProcessButton(QPushButton):
    """
    Кнопка процесса. Хранит состояние, проверяет условия, запускает действие.
    Внешний вид обновляется автоматически на основе базового цвета.
    """

    def __init__(
        self,
        step_id: str,
        text: str,
        condition_checker: Callable[[], Tuple[bool, str]],
        action: Callable,
        logger: ILogger,
        bg_color,
        parent=None,
        initial_state: ButtonState = ButtonState.GRAY,
    ):
        super().__init__(text, parent)
        self.step_id = step_id
        self._condition_checker = condition_checker
        self._action = action
        self._logger = logger
        self._bg_color = bg_color          # базовый цвет (кортеж RGB или RGBA)
        self._base_style = ""              # будет заполнен из фабрики после применения стиля
        self._state = initial_state

        self.clicked.connect(self._on_click)

        # Применяем начальное состояние (но сначала фабрика должна задать базовый стиль)
        # Мы вызовем update_state из фабрики после сохранения base_style.

    # ---- Свойства ----
    def get_state(self) -> ButtonState:
        return self._state

    # ---- Управление состоянием ----
    def update_state(self, new_state: ButtonState):
        """Обновляет состояние и перерисовывает кнопку."""
        if self._state == new_state:
            return
        self._state = new_state
        self._apply_style()

    # ---- Логика нажатия ----
    def _on_click(self):
        if self._state == ButtonState.LOCKED:
            return
        can, reason = self._condition_checker()
        if not can:
            self._logger.warning(f"Условие для '{self.step_id}' не выполнено: {reason}")
            return
        self._action()

    # ---- Внешний вид ----
    def _apply_style(self):
        """Применяет стиль в зависимости от состояния, сохраняя базовый стиль."""
        # Сначала сбрасываем enable (вдруг был заблокирован)
        self.setEnabled(True)

        # Всегда начинаем с базового стиля (он содержит padding, border-radius, hover и т.д.)
        current_style = self._base_style

        if self._state == ButtonState.ACTIVE:
            # Оставляем базовый стиль без изменений
            self.setStyleSheet(current_style)

        elif self._state == ButtonState.GRAY:
            # Фиксированный серый цвет (не зависит от базового)
            self.setStyleSheet(current_style + """
                QPushButton {
                    background-color: rgba(80, 80, 80, 0.5) !important;
                    color: #666 !important;
                }
            """)

        elif self._state == ButtonState.EXECUTED:
            # Затемняем базовый цвет: отнимаем 10 от каждого канала RGB
            r, g, b = self._bg_color[:3]
            r = max(0, r - 10)
            g = max(0, g - 10)
            b = max(0, b - 10)
            color_str = f"rgb({r}, {g}, {b})"
            self.setStyleSheet(current_style + f"""
                QPushButton {{
                    background-color: {color_str} !important;
                    color: white !important;
                    font-weight: bold !important;
                }}
            """)

        elif self._state == ButtonState.LOCKED:
            # Делаем красноватым: R+50, G-20, B-20 (ограничиваем значения)
            r, g, b = self._bg_color[:3]
            r = min(255, r + 50)
            g = max(0, g - 20)
            b = max(0, b - 20)
            color_str = f"rgb({r}, {g}, {b})"
            self.setStyleSheet(current_style + f"""
                QPushButton {{
                    background-color: {color_str} !important;
                    color: white !important;
                }}
            """)
            self.setEnabled(False)