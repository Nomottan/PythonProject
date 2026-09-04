from pathlib import Path
from typing import Optional, Dict, Any, List
from PySide6.QtCore import QObject, Signal

from utils.logger import ILogger
from utils.run_manager import RunManager
from utils.state_manager import StateManager, StepConfig, ButtonState
from utils.persistence_manager import PersistenceManager
from utils.condition_checker import ConditionChecker
from utils.action_dispatcher import ActionDispatcher


class ProcessController(QObject):
    """
    Главный координатор процесса.
    Управляет всеми менеджерами, обрабатывает события от UI и сервисов.
    """

    # Сигналы для UI
    state_changed = Signal(str, ButtonState, ButtonState)  # step_id, old_state, new_state
    log_message = Signal(str, int)  # сообщение, уровень
    show_confirmation = Signal(str, str)  # заголовок, текст
    open_folder = Signal(str)  # путь к папке

    def __init__(
        self,
        process_name: str,
        target_dir: str,
        config_manager,
        logger: ILogger,
        parent_widget=None,
    ):
        super().__init__()
        self.process_name = process_name
        self.target_dir = target_dir
        self.config_manager = config_manager
        self.logger = logger
        self.parent_widget = parent_widget

        # Создаём менеджеры
        self.run_manager = RunManager(target_dir, process_name, logger)
        self.state_manager = StateManager(logger)
        self.persistence_manager = PersistenceManager(
            self.run_manager.get_work_folder(),
            logger,
            filename=f".{process_name.lower()}_state.json"
        )
        self.condition_checker = ConditionChecker(
            self.run_manager,
            config_manager,
            process_name.lower(),
            logger
        )
        self.action_dispatcher = ActionDispatcher(self.state_manager, logger)
        self.action_dispatcher.set_parent_widget(parent_widget)

        # Подписываемся на сигналы state_manager
        self.state_manager.state_changed.connect(self._on_state_changed)
        self.action_dispatcher.action_finished.connect(self._on_action_finished)

        # Флаг выполнения
        self.is_processing = False

        # Список зарегистрированных шагов
        self.step_ids: List[str] = []

        # Восстанавливаем состояние, если есть
        self._restore_state()

    def _restore_state(self):
        """Загружает сохранённое состояние и восстанавливает флаги выполнения."""
        state = self.persistence_manager.load_state()
        executed = state.get("executed_steps", [])
        for step_id in executed:
            if step_id in self.state_manager.steps:
                self.state_manager.executed_flags.add(step_id)
                self.logger.info(f"Восстановлено выполнение шага: {step_id}")
        self.state_manager.update_all()

    def register_step(
        self,
        step_id: str,
        button_text: str,
        condition_func,
        action_func,
        action_args: tuple = (),
        action_kwargs: dict = None,
        depends_on: list[str] = None,
        is_first: bool = False,
        is_final: bool = False,
        auto_open_folder: bool = False,
        button_text_executed: str = None,
    ):
        """Регистрирует шаг и добавляет его в систему."""
        config = StepConfig(
            step_id=step_id,
            button_text=button_text,
            condition_func=condition_func,
            action_func=action_func,
            action_args=action_args,
            action_kwargs=action_kwargs or {},
            depends_on=depends_on or [],
            is_first=is_first,
            is_final=is_final,
            auto_open_folder=auto_open_folder,
            button_text_executed=button_text_executed,
        )
        self.state_manager.register_step(config)
        self.step_ids.append(step_id)

    def _on_state_changed(self, step_id: str, old_state: ButtonState, new_state: ButtonState):
        """Проксирует сигнал из StateManager в UI."""
        self.state_changed.emit(step_id, old_state, new_state)

    def _on_action_finished(self, step_id: str, success: bool, error: str):
        """Обрабатывает завершение действия."""
        self.is_processing = False
        if success:
            self.state_manager.set_executed(step_id)
            # Проверяем, является ли шаг финальным
            config = self.state_manager.steps.get(step_id)
            if config and config.is_final:
                # Открываем папку, если нужно
                if config.auto_open_folder:
                    self._request_open_folder()
        else:
            self.logger.error(f"Ошибка выполнения шага {step_id}: {error}")
            # Кнопка остаётся активной (если условия всё ещё выполнены)
            self.state_manager.update_all()

    def _request_open_folder(self):
        """Запрашивает открытие папки через UI."""
        if self.parent_widget:
            # Можно показать диалог через сигнал
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self.parent_widget,
                "Открыть папку",
                "Открыть папку с результатами?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.open_folder.emit(str(self.run_manager.get_work_folder()))

    def on_button_clicked(self, step_id: str):
        """Вызывается из UI при нажатии на кнопку."""
        if self.is_processing:
            self.logger.warning("Уже выполняется действие, подождите")
            return

        state = self.state_manager.get_state(step_id)
        config = self.state_manager.steps.get(step_id)

        if state == ButtonState.LOCKED:
            return

        if state == ButtonState.GRAY:
            # Проверяем условия повторно, возможно они изменились
            condition_ok, reason = config.condition_func()
            if condition_ok:
                # Условия вдруг стали выполнены — переходим в ACTIVE
                self.state_manager._update_step(step_id)
                state = self.state_manager.get_state(step_id)
                # Если после обновления стало ACTIVE — выполняем
                if state == ButtonState.ACTIVE:
                    self._execute_action(step_id)
                return
            else:
                # Условия не выполнены — логируем причину
                self.logger.warning(f"Условия не выполнены: {reason}")
                return

        if state == ButtonState.ACTIVE:
            self._execute_action(step_id)

        elif state == ButtonState.EXECUTED:
            # Защита от дублирования
            self._ask_for_repeat(step_id)

    def _execute_action(self, step_id: str):
        """Запускает действие для шага."""
        config = self.state_manager.steps.get(step_id)
        if not config:
            return

        self.is_processing = True

        # Если это первый шаг — архивируем текущий прогон и сбрасываем цепочку
        if config.is_first:
            self.run_manager.archive_current_run()
            self.state_manager.reset_chain(step_id)

        # Запускаем действие
        self.action_dispatcher.run_action(
            step_id,
            config.action_func,
            args=config.action_args,
            kwargs=config.action_kwargs,
            buttons_to_lock=[step_id]  # блокируем только эту кнопку
        )

    def _ask_for_repeat(self, step_id: str):
        """Запрашивает подтверждение повторного выполнения."""
        config = self.state_manager.steps.get(step_id)
        if not config:
            return

        # Показываем диалог через сигнал (или напрямую через QMessageBox)
        if self.parent_widget:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self.parent_widget,
                "Повторное выполнение",
                f"Шаг '{config.button_text}' уже выполнен. Выполнить повторно? Данные будут перезаписаны.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                # Сбрасываем цепочку зависимых шагов
                self.state_manager.reset_chain(step_id)
                # Убираем флаг выполнения
                self.state_manager.executed_flags.discard(step_id)
                # Обновляем состояние
                self.state_manager._update_step(step_id)
                # Запускаем действие
                self._execute_action(step_id)

    def reset_process(self):
        """Полный сброс процесса (перезапуск с первого шага)."""
        self.logger.info(f"Сброс процесса {self.process_name}")
        self.state_manager.executed_flags.clear()
        self.state_manager.update_all()
        # Удаляем файл состояния
        self.persistence_manager.reset_state()

    def shutdown(self):
        """Вызывается при закрытии окна для сохранения состояния."""
        # Сохраняем состояние
        state = {
            "executed_steps": list(self.state_manager.executed_flags),
            # Можно добавить дополнительные данные для сравнения
        }
        self.persistence_manager.save_state(state)
        self.logger.info(f"Состояние процесса {self.process_name} сохранено")