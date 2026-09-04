from typing import Callable, Optional, Dict, Any
from PySide6.QtCore import QObject, Signal

from utils.logger import ILogger
from utils.log_templates import LogTemplates
from utils.state_manager import StateManager, ButtonState
from ui.factories.factories import ThreadFactory

class ActionDispatcher(QObject):
    """
    Запускает сервисы в фоновых потоках.
    Управляет блокировкой/разблокировкой кнопок.
    """

    action_finished = Signal(str, bool, str)  # step_id, success, error_message

    def __init__(self, state_manager: StateManager, logger: ILogger):
        super().__init__()
        self.state_manager = state_manager
        self.logger = logger
        self._running_tasks: Dict[str, Any] = {}  # храним объекты потоков (опционально)
        self._parent_widget = None  # для ThreadFactory

    def set_parent_widget(self, parent):
        """Устанавливает родительский виджет для ThreadFactory."""
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
        """
        Запускает действие в фоновом потоке.
        Блокирует указанные кнопки (по умолчанию только текущую).
        """
        if step_id in self._running_tasks:
            self.logger.warning(f"Действие для шага {step_id} уже выполняется")
            return

        # Блокируем кнопки
        lock_buttons = buttons_to_lock or [step_id]
        for bid in lock_buttons:
            if self.state_manager.get_state(bid) != ButtonState.LOCKED:
                # Временно сохраняем состояние, чтобы потом восстановить
                self.state_manager._set_state(bid, ButtonState.LOCKED)
                self.state_manager.state_changed.emit(bid, ButtonState.ACTIVE, ButtonState.LOCKED)

        LogTemplates.service_started(self.logger, step_id)

        kwargs = kwargs or {}

        def wrapped_action():
            try:
                result = action_func(*args, **kwargs)
                return result
            except Exception as e:
                raise e

        def on_success(result):
            self._on_action_done(step_id, True, "", on_finished, lock_buttons)

        def on_error(error):
            self._on_action_done(step_id, False, str(error), on_error, lock_buttons)

        # Используем ThreadFactory для запуска
        if self._parent_widget:
            ThreadFactory.run_in_thread(
                target_func=wrapped_action,
                on_finished=on_success,
                error_callback=on_error
            )
        else:
            # Запасной вариант — обычный threading (но лучше передать parent)
            import threading
            def wrapper():
                try:
                    result = wrapped_action()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
            thread = threading.Thread(target=wrapper, daemon=True)
            thread.start()
            self._running_tasks[step_id] = thread

    def _on_action_done(self, step_id: str, success: bool, error: str, callback: Callable, lock_buttons: list):
        """Обработчик завершения действия."""
        # Удаляем из running_tasks
        self._running_tasks.pop(step_id, None)

        # Разблокируем кнопки
        for bid in lock_buttons:
            if self.state_manager.get_state(bid) == ButtonState.LOCKED:
                # Возвращаем к предыдущему состоянию (обновляем)
                self.state_manager._update_step(bid)

        LogTemplates.service_finished(self.logger, step_id, success, error)

        if callback:
            callback()

        self.action_finished.emit(step_id, success, error)

    def cancel_action(self, step_id: str):
        """Отменяет выполнение (если поддерживается)."""
        # Пока не реализовано, т.к. ThreadFactory не поддерживает отмену
        self.logger.warning("Отмена действий не поддерживается")