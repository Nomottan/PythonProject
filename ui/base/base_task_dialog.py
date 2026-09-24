"""
Базовый диалог задачи.

Содержит BaseTaskDialog — промежуточный слой между BaseEditDialog
и тремя диалогами задачи: NewTaskDialog, DeadlineEditDialog,
PlannerRecurrenceEditDialog. Хранит ссылку на задачу, но не создаёт
никаких полей — это делают наследники в _build_content.
"""

from ui.base.base_edit_dialog import BaseEditDialog


class BaseTaskDialog(BaseEditDialog):
    """Базовый диалог задачи.

    Назначение:
        Общий предок для трёх диалогов задачи. Убирает дублирование
        каркаса и хранения ссылки на задачу.

    Роль в программе:
        Промежуточный слой. Наследники переопределяют _build_content,
        _collect_result, _validate.
    """

    def __init__(self, parent=None, task=None, title="",
                 bg_color=(64, 48, 66, 0.8), width=400, height=350,
                 close_button=True, ok_cancel=True,
                 draggable=False, close_on_click_outside=False,
                 modal=True, center=True, on_close=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            task — PlannerTask (None при создании).
            title — заголовок.
            bg_color — цвет фона.
            width, height — размеры.
            close_button — показывать ли крестик.
            ok_cancel — показывать ли кнопки ОК/Отмена.
            draggable — перетаскивание.
            close_on_click_outside — закрывать при клике вне.
            modal — модальность.
            center — центрировать.
            on_close — callback при закрытии.

        Роль: сохраняет self._task, проксирует остальное в BaseEditDialog.
        """
        self._task = task
        super().__init__(
            parent=parent, title=title, bg_color=bg_color,
            width=width, height=height, close_button=close_button,
            ok_cancel=ok_cancel, draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal, center=center, on_close=on_close,
        )