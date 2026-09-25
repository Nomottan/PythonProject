"""
Фабрика кнопок.

Содержит ButtonFactory — единая точка создания QPushButton
с готовым QSS, и ActionButtonType — Enum-описание «кнопок действий».

ButtonFactory не наследует BaseWidgetFactory: QSS собирается
через ui.styles.WidgetStyle, а не через наследственные методы.
"""

from enum import Enum
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ui.styles import WidgetStyle


class ActionButtonType(Enum):
    """Тип кнопки действия.

    Каждый член несёт готовый набор атрибутов для создания
    стилизованной кнопки: символ, цвет фона по умолчанию,
    фиксированный размер и размер шрифта.

    Использование:
        ButtonFactory.create_action_button(
            parent, ActionButtonType.DELETE, callback,
        )
    """

    # (symbol, color, size, font_size)
    EDIT = ("✎", (120, 120, 150), (26, 26), 14)
    COMPLETE = ("✓", (70, 150, 90), (26, 26), 14)
    DELETE = ("✕", (176, 80, 80), (22, 22), None)
    RESTORE = ("↺", (100, 130, 150), (26, 26), 14)

    def __init__(self, symbol: str, color: Tuple[int, ...],
                 size: Tuple[int, int], font_size: Optional[int]) -> None:
        """Конструктор члена Enum.

        Вход:
            symbol — отображаемый символ.
            color — цвет фона по умолчанию.
            size — фиксированный размер (w, h).
            font_size — размер шрифта или None.
        """
        self.symbol = symbol
        self.color = color
        self.size = size
        self.font_size = font_size


class ButtonFactory:
    """Фабрика для создания кнопок.

    Роль: единая точка создания QPushButton. QSS собирается
          через WidgetStyle.apply_button — поддерживает
          :hover, :pressed, :disabled, выравнивание, шрифты.

    Публичный API:
        create_button — универсальная кнопка.
        create_action_button — кнопка-иконка из ActionButtonType.
        create_edit_button, create_complete_button,
        create_delete_button, create_restore_button — обёртки.
        create_datetime_button — кнопка даты/времени.
        create_buttons_from_config — массовое создание.
        create_add_button — круглая кнопка добавления +.
    """

    @staticmethod
    def create_button(parent, text, bg_color, text_color=None,
                      padding="8px 16px", fixed_size=None, alignment=None,
                      object_name=None, cursor_shape=None, border_radius=5,
                      border="none", font_size=None, font_family=None,
                      font_weight=None, extra_style="", checkable=False,
                      checked=False, tooltip=None, min_size=None,
                      max_size=None, hover_color=None, pressed_color=None,
                      disabled_color=None):
        """Создаёт стилизованную QPushButton.

        Вход:
            parent — родительский виджет.
            text — подпись.
            bg_color — цвет фона.
            text_color — цвет текста. None → контрастный.
            padding — внутренние отступы (CSS).
            fixed_size — (ширина, высота) или None.
            alignment — "left"/"center"/"right".
            object_name — objectName для селектора.
            cursor_shape — Qt.CursorShape.
            border_radius — радиус скругления в px.
            border — CSS-рамка.
            font_size, font_family, font_weight — шрифт.
            extra_style — дополнительный CSS.
            checkable — сделать ли checkable.
            checked — начальное состояние (если checkable).
            tooltip — подсказка.
            min_size, max_size — ограничения размеров.
            hover_color, pressed_color, disabled_color — цвета
                состояний. None → вычисляются автоматически.

        Выход: QPushButton с QSS.
        """
        btn = QPushButton(text, parent)
        if object_name:
            btn.setObjectName(object_name)
        if cursor_shape:
            btn.setCursor(cursor_shape)
        if tooltip:
            btn.setToolTip(tooltip)
        if min_size:
            btn.setMinimumSize(*min_size)
        if max_size:
            btn.setMaximumSize(*max_size)
        if fixed_size:
            btn.setFixedSize(*fixed_size)
        if checkable:
            btn.setCheckable(True)
            btn.setChecked(checked)

        WidgetStyle.apply_button(
            btn, bg_color, text_color, padding, border_radius, border,
            font_size, font_family, font_weight, alignment,
            hover_color, pressed_color, disabled_color, extra_style,
        )
        return btn

    @staticmethod
    def create_action_button(parent, action: ActionButtonType, callback,
                             size=None, bg_color=None, font_size=None,
                             tooltip=None):
        """Создаёт кнопку-иконку по типу действия.

        Вход:
            parent — родитель.
            action — ActionButtonType.
            callback — обработчик clicked.
            size — (w, h). None → из action.size.
            bg_color — цвет фона. None → из action.color.
            font_size — размер шрифта. None → из action.font_size.
            tooltip — подсказка.

        Выход: QPushButton.
        """
        btn = ButtonFactory.create_button(
            parent,
            text=action.symbol,
            bg_color=bg_color if bg_color is not None else action.color,
            fixed_size=size if size is not None else action.size,
            padding="0px",
            font_size=font_size if font_size is not None else action.font_size,
            tooltip=tooltip,
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_edit_button(parent, callback, size=None, bg_color=None):
        """Кнопка редактирования (✎)."""
        return ButtonFactory.create_action_button(
            parent, ActionButtonType.EDIT, callback,
            size=size, bg_color=bg_color,
        )

    @staticmethod
    def create_complete_button(parent, callback, size=None, bg_color=None):
        """Кнопка выполнения (✓)."""
        return ButtonFactory.create_action_button(
            parent, ActionButtonType.COMPLETE, callback,
            size=size, bg_color=bg_color,
        )

    @staticmethod
    def create_delete_button(parent, callback, size=None, bg_color=None):
        """Кнопка удаления (✕)."""
        return ButtonFactory.create_action_button(
            parent, ActionButtonType.DELETE, callback,
            size=size, bg_color=bg_color,
        )

    @staticmethod
    def create_restore_button(parent, callback, size=None, bg_color=None):
        """Кнопка восстановления из архива (↺)."""
        return ButtonFactory.create_action_button(
            parent, ActionButtonType.RESTORE, callback,
            size=size, bg_color=bg_color,
        )

    @staticmethod
    def create_datetime_button(parent, callback):
        """Создаёт кнопку для отображения текущей даты и времени.

        Вход:
            parent — родитель.
            callback — обработчик clicked.

        Выход: QPushButton с полупрозрачным фоном.

        Роль: используется в MainWindow. Текст обновляется снаружи
              по таймеру; кнопка только отображает.
        """
        btn = ButtonFactory.create_button(
            parent,
            text="",
            bg_color=(255, 255, 255, 0.1),
            text_color="#ffffff",
            padding="8px 12px",
            border_radius=10,
            border="1px solid rgba(255, 255, 255, 0.3)",
            font_size=14,
            font_weight="bold",
            object_name="datetime_btn",
            cursor_shape=Qt.PointingHandCursor,
            extra_style="""
                QPushButton#datetime_btn:hover {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_buttons_from_config(parent, configs, handlers=None):
        """Создаёт набор кнопок по конфигурации.

        Вход:
            parent — родительский виджет.
            configs — список кортежей (attr, text, color
                      [, padding, fixed_size, object_name,
                       cursor_shape, extra_style]).
            handlers — dict {attr: callable | имя_метода}.

        Выход: dict {attr: QPushButton}.

        Роль: массовое создание кнопок одной строкой. Атрибут
              attr устанавливается на parent через setattr.
        """
        if handlers is None:
            handlers = {}
        created = {}

        for cfg in configs:
            attr = cfg[0]
            text = cfg[1]
            color = cfg[2]
            pad = cfg[3] if len(cfg) > 3 else "8px 16px"
            size = cfg[4] if len(cfg) > 4 else None
            obj_name = cfg[5] if len(cfg) > 5 else None
            cursor = cfg[6] if len(cfg) > 6 else None
            extra = cfg[7] if len(cfg) > 7 else ""

            btn = ButtonFactory.create_button(
                parent,
                text=text,
                bg_color=color,
                padding=pad,
                fixed_size=size,
                object_name=obj_name,
                cursor_shape=cursor,
                extra_style=extra
            )

            handler = handlers.get(attr)
            if handler:
                if callable(handler):
                    btn.clicked.connect(handler)
                else:
                    btn.clicked.connect(getattr(parent, handler))

            setattr(parent, attr, btn)
            created[attr] = btn

        return created

    @staticmethod
    def create_add_button(parent, callback, size=(40, 40),
                          bg_color=(255, 255, 255, 0.15),
                          border="1px solid rgba(255, 255, 255, 0.3)",
                          font_size=18,
                          hover_color=(255, 255, 255, 0.3)):
        """Создаёт круглую кнопку добавления «+».

        Вход:
            parent — родитель.
            callback — обработчик clicked.
            size — (w, h). Радиус = ширина // 2.
            bg_color — фон.
            border — CSS-рамка.
            font_size — размер шрифта.
            hover_color — цвет при наведении.

        Выход: QPushButton.

        Роль: используется в списках и сетках. Белый цвет текста
              задаётся через extra_style — для полупрозрачного
              белого авто-расчёт не подходит.
        """
        btn = ButtonFactory.create_button(
            parent,
            text="+",
            bg_color=bg_color,
            fixed_size=size,
            border_radius=size[0] // 2,
            border=border,
            font_size=font_size,
            hover_color=hover_color,
            extra_style="QPushButton { color: white; }",
        )
        btn.clicked.connect(callback)
        return btn