"""
Декораторы для логирования действий.

Содержит log_button_action — обёртку для обработчиков кнопок
в MainWindow: debug при старте, critical при ошибке.
"""

import functools


def log_button_action(name: str, error_template: str):
    """Оборачивает обработчик кнопки.

    Вход:
        name — имя действия для debug-сообщения
               ("open_sellers_window").
        error_template — шаблон critical-сообщения с {e}
                         ("Ошибка при открытии окна 'Продавцы': {e}").

    Роль: при вызове пишет debug «{name}: старт». Если внутри
          произошло исключение — вызывает logger.critical с
          отформатированным шаблоном и can_influence=False
          (пользователь не может повлиять на баг кода).
          Исключение НЕ пробрасывается: UI не должен падать
          от ошибки одного обработчика.

    Если у self нет атрибута logger — вызывает функцию без обёртки
    (легаси-совместимость). Если ошибка произошла, а logger тоже
    нет — исключение всё-таки пробрасывается.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            logger = getattr(self, "logger", None)
            if logger is not None:
                logger.debug(f"{name}: старт")
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                if logger is not None:
                    logger.critical(
                        error_template.format(e=e),
                        can_influence=False,
                    )
                else:
                    raise
        return wrapper
    return decorator