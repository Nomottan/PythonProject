# utils/action_dispatcher.py
from typing import Callable, Optional, Dict, Any, List
from PySide6.QtCore import QObject, Signal

from utils.logger import ILogger
from utils.log_templates import LogTemplates
from utils.state_manager import StateManager, ButtonState
from ui.factories.factories import ThreadFactory


class ActionDispatcher(QObject):
    action_finished = Signal(str, bool, str)  # step_id, success, error_message

    def __init__(self, state_manager: StateManager, logger: ILogger):
        super().__init__()
        self.state_manager = state_manager
        self.logger = logger
        self._running_tasks: Dict[str, Any] = {}
        self._parent_widget = None

    def set_parent_widget(self, parent):
        self._parent_widget = parent

    def run_action(
        self,
        step_id: str,
        action_func: Callable,
        args: tuple = (),
        kwargs: dict = None,
        on_finished: Callable = None,
        on_error: Callable = None,
        buttons_to_lock: list[str] = None,
    ):
        if step_id in self._running_tasks:
            self.logger.warning(f"Действие для шага {step_id} уже выполняется")
            return

        # Блокируем кнопки
        lock_buttons = buttons_to_lock or [step_id]
        for bid in lock_buttons:
            if self.state_manager.get_state(bid) != ButtonState.LOCKED:
                self.state_manager._set_state(bid, ButtonState.LOCKED)
                self.state_manager.state_changed.emit(bid, ButtonState.ACTIVE, ButtonState.LOCKED)

        LogTemplates.service_started(self.logger, step_id)

        kwargs = kwargs or {}

        def on_success():
            self._on_action_done(step_id, True, "", on_finished, lock_buttons)

        def on_error_callback(error):
            self._on_action_done(step_id, False, str(error), on_error, lock_buttons)

        # Используем ThreadFactory.create_thread
        ThreadFactory.create_thread(
            parent=self._parent_widget,
            buttons=[],  # мы сами блокируем кнопки, поэтому не передаём их в фабрику
            target_func=action_func,
            args=args,
            kwargs=kwargs,
            on_finished=on_success,
            error_callback=on_error_callback
        )

    def _on_action_done(self, step_id: str, success: bool, error: str, callback: Callable, lock_buttons: list):
        self._running_tasks.pop(step_id, None)

        # Разблокируем кнопки
        for bid in lock_buttons:
            if self.state_manager.get_state(bid) == ButtonState.LOCKED:
                # Пересчитываем состояние (например, если условия всё ещё выполнены, станет ACTIVE или EXECUTED)
                self.state_manager._update_step(bid)

        LogTemplates.service_finished(self.logger, step_id, success, error)

        if callback:
            callback()

        self.action_finished.emit(step_id, success, error)

    def cancel_action(self, step_id: str):
        # Пока не реализовано
        self.logger.warning("Отмена действий не поддерживается")
