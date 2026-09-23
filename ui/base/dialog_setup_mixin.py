"""
Миксин для настройки каркаса QDialog.

Содержит DialogSetupMixin — тонкую обёртку над
ExtendedWindowFactory.setup_window. Миксин нужен, чтобы все
формы редактирования шли через единый вызов setup_dialog_frame,
а не дёргали фабрику напрямую.
"""

from ui.factories.window_factories import ExtendedWindowFactory


class DialogSetupMixin:
    """Миксин для QDialog: превращает окно в форму редактирования.

    Назначение:
        Делегирует настройку каркаса в ExtendedWindowFactory.setup_window.
        Не дублирует код — единый источник правды для каркаса диалогов.

    Роль в программе:
        Наследники BaseEditDialog используют миксин, чтобы получить
        content_layout для наполнения. Прямые вызовы
        ExtendedWindowFactory.setup_window из диалогов исчезают —
        всё идёт через setup_dialog_frame.

    Зависимости:
        ui.factories.window_factories.ExtendedWindowFactory — целевой
        метод настройки. Зависимость «база → фабрика», обратной быть
        не должно, чтобы избежать циклов.
    """

    def setup_dialog_frame(self, parent, title, bg_color,
                           width=400, height=350,
                           close_button=True, ok_cancel=True,
                           draggable=False, close_on_click_outside=False,
                           modal=True, center=True, on_close=None):
        """Настраивает каркас диалога.

        Вход:
            parent — родительское окно.
            title — заголовок.
            bg_color — цвет фона (кортеж (r, g, b) или (r, g, b, a)).
            width, height — размеры по умолчанию.
            close_button — показывать ли крестик.
            ok_cancel — показывать ли кнопки ОК/Отмена.
            draggable — перетаскивание за тело.
            close_on_click_outside — закрывать при клике вне.
            modal — модальность.
            center — центрировать относительно parent.
            on_close — callback при закрытии.

        Выход: content_layout — QVBoxLayout для контента.

        Роль: обёртка над ExtendedWindowFactory.setup_window.
              Кнопки ОК/Отмена замыкаются на self.accept / self.reject —
              BaseEditDialog переопределяет accept() для валидации.
        """
        return ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title=title,
            bg_color=bg_color,
            close_button=close_button,
            ok_cancel=ok_cancel,
            # Замыкаем колбэки на методы QDialog — BaseEditDialog
            # переопределит accept() для валидации перед закрытием.
            ok_callback=self.accept if ok_cancel else None,
            cancel_callback=self.reject if ok_cancel else None,
            draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal,
            center=center,
            on_close=on_close,
            return_content_layout=True,
            default_width=width,
            default_height=height,
        )