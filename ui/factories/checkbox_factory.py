"""
Фабрика композитного чекбокса.

Содержит CheckBoxFactory — единую точку создания CheckBox.
Принимает параметры, при bg_color=None резолвит фон через
BaseWidgetFactory.resolve_element_bg и возвращает готовый
виджет.
"""

from ui.factories.base_factory import BaseWidgetFactory


class CheckBoxFactory:
    """Фабрика для создания CheckBox.

    Роль:
        Единая точка создания композитных чекбоксов. Собирает
        параметры, резолвит bg_color (при None — от родителя),
        возвращает готовый CheckBox.
    """

    @staticmethod
    def create_checkbox(parent, text, checked=False, *,
                        tristate=False, check_state=None,
                        position="right", bg_color=None,
                        square_size=None, fixed_size=None,
                        fixed_height=None, spacing=6,
                        object_name=None, tooltip=None,
                        read_only=False, font_size=None):
        """Создаёт CheckBox.

        Вход:
            parent — родитель.
            text — подпись.
            checked — начальное состояние (bool).
            tristate — keyword-only. Включить тристейт.
            check_state — keyword-only. Явное Qt.CheckState;
                          если задан — переопределяет checked.
            position — keyword-only. "right" или "left".
            bg_color — keyword-only. Фон; None → от родителя через
                       BaseWidgetFactory.resolve_element_bg.
            square_size — keyword-only. Размер квадрата; None → от
                          высоты текста.
            fixed_size — keyword-only. Фиксированный размер виджета.
            spacing — keyword-only. Отступ между текстом и квадратом.
            object_name — keyword-only. objectName.
            tooltip — keyword-only. Подсказка.

        Выход: CheckBox.

        Роль:
            bg_color=None резолвится от родителя. Если резолв
            вернул не кортеж — fallback (255, 255, 255, 1.0).
            check_state переопределяет checked при не-None.
            Ленивый импорт CheckBox — разрыв возможного цикла
            ui.factories → ui.widgets → ui.factories (см. отчёт).
        """
        from ui.widgets.checkbox import CheckBox

        if bg_color is None:
            bg_color = BaseWidgetFactory.resolve_element_bg(parent)
            if not isinstance(bg_color, (tuple, list)):
                bg_color = (255, 255, 255, 1.0)

        cb = CheckBox(
            parent, text=text, checked=checked, position=position,
            bg_color=bg_color, square_size=square_size,
            fixed_size=fixed_size, fixed_height=fixed_height,
            spacing=spacing, read_only=read_only,
            font_size=font_size,
        )

        if object_name:
            cb.setObjectName(object_name)
        if tooltip:
            cb.setToolTip(tooltip)
        if tristate:
            cb.setTristate(True)
        if check_state is not None:
            cb.setCheckState(check_state)
        else:
            cb.setChecked(checked)
        return cb