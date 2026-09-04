from enum import Enum, auto
from typing import Callable, Optional, Dict, Set, Tuple
from PySide6.QtCore import QObject, Signal

from utils.logger import ILogger
from utils.log_templates import LogTemplates


class ButtonState(Enum):
    """Состояния кнопки."""
    GRAY = auto()          # условия не выполнены
    ACTIVE = auto()        # условия выполнены, можно нажать
    EXECUTED = auto()      # шаг выполнен
    LOCKED = auto()        # заблокирована на время выполнения


class StepConfig:
    """Конфигурация шага."""
    def __init__(
        self,
        step_id: str,
        button_text: str,
        condition_func: Callable[[], Tuple[bool, str]],
        action_func: Callable,
        action_args: tuple = (),
        action_kwargs: dict = None,
        depends_on: list[str] = None,
        is_first: bool = False,
        is_final: bool = False,
        auto_open_folder: bool = False,
        button_text_executed: str = None,
    ):
        self.step_id = step_id
        self.button_text = button_text
        self.button_text_executed = button_text_executed or f"{button_text} ✓"
        self.condition_func = condition_func
        self.action_func = action_func
        self.action_args = action_args
        self.action_kwargs = action_kwargs or {}
        self.depends_on = depends_on or []
        self.is_first = is_first
        self.is_final = is_final
        self.auto_open_folder = auto_open_folder


class StateManager(QObject):
    """
    Управляет состояниями кнопок, зависимостями и проверкой условий.
    Испускает сигналы при изменении состояния.
    """

    state_changed = Signal(str, ButtonState, ButtonState)  # step_id, old_state, new_state

    def __init__(self, logger: ILogger):
        super().__init__()
        self.logger = logger
        self.steps: Dict[str, StepConfig] = {}
        self.states: Dict[str, ButtonState] = {}
        self.executed_flags: set[str] = set()
        self._failure_reasons: Dict[str, str] = {}
        self._condition_cache: Dict[str, Tuple[bool, str]] = {}

    def register_step(self, config: StepConfig):
        """Регистрирует шаг."""
        step_id = config.step_id
        self.steps[step_id] = config
        # Начальное состояние — GRAY
        self.states[step_id] = ButtonState.GRAY
        self._failure_reasons[step_id] = ""
        self._update_step(step_id)

    def update_all(self):
        """Обновляет состояния всех зарегистрированных шагов."""
        # Сначала обновляем зависимости: проходим по шагам в порядке регистрации
        for step_id in self.steps:
            self._update_step(step_id)

    def _update_step(self, step_id: str):
        """Обновляет состояние одного шага."""
        config = self.steps.get(step_id)
        if not config:
            return

        # Если кнопка заблокирована — не меняем состояние
        if self.states.get(step_id) == ButtonState.LOCKED:
            return

        old_state = self.states.get(step_id, ButtonState.GRAY)
        old_reason = self._failure_reasons.get(step_id, "")

        # Проверка зависимостей
        for dep_id in config.depends_on:
            dep_state = self.states.get(dep_id, ButtonState.GRAY)
            if dep_state != ButtonState.EXECUTED:
                self._set_state(step_id, ButtonState.GRAY)
                new_reason = f"Зависимость '{dep_id}' не выполнена"
                self._failure_reasons[step_id] = new_reason
                if old_state != ButtonState.GRAY or old_reason != new_reason:
                    LogTemplates.condition_failed(self.logger, step_id, new_reason)
                self._log_if_changed(step_id, old_state, ButtonState.GRAY)
                return

        # Проверка условий
        condition_ok, reason = self._check_condition(step_id)
        if not condition_ok:
            self._set_state(step_id, ButtonState.GRAY)
            self._failure_reasons[step_id] = reason
            # Логируем только если состояние или причина изменились
            if old_state != ButtonState.GRAY or old_reason != reason:
                LogTemplates.condition_failed(self.logger, step_id, reason)
            self._log_if_changed(step_id, old_state, ButtonState.GRAY)
            return
        else:
            self._failure_reasons[step_id] = ""

        # Если условия выполнены и шаг уже выполнен в этой сессии
        if step_id in self.executed_flags:
            new_state = ButtonState.EXECUTED
        else:
            new_state = ButtonState.ACTIVE

        self._set_state(step_id, new_state)
        self._log_if_changed(step_id, old_state, new_state)

    def _check_condition(self, step_id: str) -> Tuple[bool, str]:
        """Вызывает condition_func и кеширует результат (на время одного цикла обновления)."""
        config = self.steps.get(step_id)
        if not config:
            return False, "Шаг не зарегистрирован"

        # Для первой кнопки всегда true, если есть данные (но условие всё равно вызывается)
        try:
            return config.condition_func()
        except Exception as e:
            self.logger.error(f"Ошибка в condition_func для {step_id}: {e}")
            return False, f"Ошибка проверки: {e}"

    def _set_state(self, step_id: str, new_state: ButtonState):
        """Устанавливает состояние (без проверок)."""
        self.states[step_id] = new_state

    def _log_if_changed(self, step_id: str, old_state: ButtonState, new_state: ButtonState):
        """Логирует изменение состояния, если оно произошло."""
        if old_state != new_state:
            LogTemplates.state_changed(self.logger, step_id, old_state.name, new_state.name)
            self.state_changed.emit(step_id, old_state, new_state)

    def get_state(self, step_id: str) -> ButtonState:
        """Возвращает текущее состояние шага."""
        return self.states.get(step_id, ButtonState.GRAY)

    def get_failure_reason(self, step_id: str) -> str:
        """Возвращает причину, почему шаг неактивен (если есть)."""
        return self._failure_reasons.get(step_id, "")

    def set_executed(self, step_id: str):
        """Отмечает шаг как выполненный (если он активен)."""
        config = self.steps.get(step_id)
        if not config:
            return
        if self.get_state(step_id) == ButtonState.ACTIVE:
            self.executed_flags.add(step_id)
            self._update_step(step_id)

    def reset_chain(self, step_id: str):
        """
        Сбрасывает состояния всех шагов, которые прямо или косвенно зависят от step_id.
        """
        # Находим все зависимые шаги
        dependent = set()
        for sid, config in self.steps.items():
            if step_id in config.depends_on:
                dependent.add(sid)
                # Также добавляем тех, кто зависит от этих
                self._collect_dependents(sid, dependent)

        # Сбрасываем их состояния
        for sid in dependent:
            if self.states.get(sid) != ButtonState.LOCKED:
                self.executed_flags.discard(sid)
                self._update_step(sid)
                self._failure_reasons[sid] = "Сброшено из-за перезапуска предыдущего шага"

        # Пересчитываем состояние самого шага (если он не заблокирован)
        if self.states.get(step_id) != ButtonState.LOCKED:
            self._update_step(step_id)

    def _collect_dependents(self, step_id: str, result: set):
        """Рекурсивно собирает все шаги, зависящие от step_id."""
        for sid, config in self.steps.items():
            if step_id in config.depends_on and sid not in result:
                result.add(sid)
                self._collect_dependents(sid, result)

    def get_all_states(self) -> dict:
        """Возвращает словарь {step_id: executed_flag} для сохранения."""
        result = {}
        for step_id in self.steps:
            result[step_id] = step_id in self.executed_flags
        return result

    def restore_from_state(self, state_data: dict):
        """Восстанавливает состояние из загруженного словаря."""
        for step_id, executed in state_data.items():
            if step_id in self.steps and executed:
                self.executed_flags.add(step_id)
                LogTemplates.state_restored(self.logger, step_id)
        self.update_all()