import threading
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QDateTime, QDate
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox,
    QListWidget, QScrollArea, QSizePolicy, QFileDialog, QProgressBar,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout, QStackedLayout,
    QTextEdit, QSpinBox, QDateTimeEdit, QAbstractSpinBox, QDateEdit
)

from ui.widgets.process_button import ProcessButton, ButtonState
from typing import Callable, Tuple
from utils.logger import ILogger


class BaseWidgetFactory:
    """Базовый класс для фабрик виджетов. Предоставляет общие методы стилизации и настройки."""

    @staticmethod
    def color_to_str(color):
        """
        Преобразует цвет в строку для CSS.
        Поддерживает кортежи (r, g, b) или (r, g, b, a) и строки (например, "#fff", "white").
        Возвращает строку вида "rgb(...)" / "rgba(...)" или исходную строку.
        """
        if isinstance(color, str):
            return color
        if isinstance(color, (tuple, list)):
            if len(color) == 3:
                return f"rgb({color[0]}, {color[1]}, {color[2]})"
            elif len(color) == 4:
                return f"rgba({color[0]}, {color[1]}, {color[2]}, {color[3]})"
        # Если что-то другое, возвращаем как есть (или можно выбросить исключение)
        return str(color)

    @staticmethod
    def calc_hover_color(bg_color):
        """
        Рассчитывает цвет для состояния hover на основе базового цвета фона.
        Для кортежей (r,g,b) или (r,g,b,a) осветляет или затемняет.
        Для строк возвращает пустую строку (означает, что hover не определён).
        """
        if isinstance(bg_color, (tuple, list)) and len(bg_color) >= 3:
            base = bg_color[:3]
            hover = []
            for c in base:
                if c + 25 <= 255:
                    hover.append(c + 25)
                else:
                    hover.append(c - 25)
            if len(bg_color) == 4:
                hover.append(bg_color[3])
            return BaseWidgetFactory.color_to_str(tuple(hover))
        # Для строк или других форматов не можем вычислить hover
        return ""

    @staticmethod
    def calc_text_color(bg_color, forced=None):
        """
        Определяет контрастный цвет текста для заданного фона.
        Если forced задан, возвращает его.
        Для кортежей использует яркость фона, для строк пытается преобразовать в RGB.
        """
        if forced is not None:
            return forced

        if isinstance(bg_color, str):
            # Пытаемся распарсить строку (поддерживаем "#RGB", "#RRGGBB", "rgb()", "rgba()")
            r = g = b = None
            s = bg_color.strip().lower()
            if s.startswith('#'):
                s = s[1:]
                if len(s) == 3:
                    r, g, b = [int(c*2, 16) for c in s]
                elif len(s) == 6:
                    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
            elif s.startswith('rgb'):
                # Простейший разбор "rgba(r, g, b, a)" или "rgb(r, g, b)"
                parts = s[s.find('(')+1 : s.rfind(')')].split(',')
                if len(parts) >= 3:
                    try:
                        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
                    except ValueError:
                        pass
            if r is not None:
                avg = (r + g + b) // 3
                return "#000000" if avg > 128 else "#ffffff"
            # Если не удалось распарсить, используем белый
            return "#ffffff"

        if isinstance(bg_color, (tuple, list)) and len(bg_color) >= 3:
            r, g, b = bg_color[:3]
            avg = (r + g + b) // 3
            if avg > 128:
                target = avg - 128
            else:
                target = avg + 127
            # Генерируем контрастный цвет, аналогично старой логике
            text = []
            for c in (r, g, b):
                if target >= c:
                    text.append(target + (target - c) // 10)
                else:
                    text.append(target - (c - target) // 10)
            return BaseWidgetFactory.color_to_str(tuple(text))

        # Если не удалось определить, возвращаем белый
        return "#ffffff"

    @staticmethod
    def apply_common_settings(widget, object_name=None, cursor_shape=None, extra_style=""):
        """
        Применяет к виджету общие настройки: objectName, курсор, дополнительный CSS.
        Если extra_style задан, он добавляется к уже существующему стилю виджета.
        """
        if object_name:
            widget.setObjectName(object_name)
        if cursor_shape is not None:
            widget.setCursor(cursor_shape)
        if extra_style:
            current_style = widget.styleSheet()
            widget.setStyleSheet(current_style + extra_style)

class ButtonFactory(BaseWidgetFactory):
    """Фабрика для создания кнопок."""

    @staticmethod
    @staticmethod
    def create_button(parent, text, bg_color, text_color=None,
                      padding="8px 16px", fixed_size=None, alignment=None,
                      object_name=None, cursor_shape=None, border_radius=5,
                      border="none", font_size=None, font_weight=None,
                      extra_style="", checkable=False, checked=False,
                      tooltip=None, min_size=None, max_size=None,
                      hover_color=None):
        btn = QPushButton(text, parent)
        # Устанавливаем общие параметры
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
        if alignment:
            btn.setStyleSheet(f"text-align: {alignment};")

        # Применяем стиль через общий метод
        ButtonFactory._apply_button_style(
            btn, bg_color, text_color, padding, border_radius, border,
            font_size, font_weight, extra_style, hover_color
        )
        return btn

    @staticmethod
    def create_process_button(
            parent,
            step_id: str,
            text: str,
            condition_checker: Callable[[], Tuple[bool, str]],
            action: Callable,
            logger: ILogger,
            bg_color,
            text_color=None,
            padding="8px 16px",
            fixed_size=None,
            alignment=None,
            object_name=None,
            cursor_shape=None,
            border_radius=5,
            border="none",
            font_size=None,
            font_weight=None,
            extra_style="",
            hover_color=None,
            tooltip=None,
            min_size=None,
            max_size=None,
            initial_state: ButtonState = ButtonState.GRAY,
    ) -> ProcessButton:
        """
        Создаёт ProcessButton с заданным стилем.
        """
        # Создаём кнопку с передачей bg_color
        btn = ProcessButton(
            step_id=step_id,
            text=text,
            condition_checker=condition_checker,
            action=action,
            logger=logger,
            bg_color=bg_color,
            parent=parent,
            initial_state=initial_state,
        )
        # Общие настройки (object_name, tooltip, размеры и т.д.)
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
        if alignment:
            btn.setStyleSheet(f"text-align: {alignment};")

        # Применяем базовый стиль через общий метод
        ButtonFactory._apply_button_style(
            btn, bg_color, text_color, padding, border_radius, border,
            font_size, font_weight, extra_style, hover_color
        )

        # Сохраняем базовый стиль в кнопке (для последующего использования в состояниях)
        btn._base_style = btn.styleSheet()

        # Применяем начальное состояние (перерисовывает кнопку)
        btn.update_state(initial_state)

        return btn

    @staticmethod
    def create_datetime_button(parent, callback):
        """
        Создаёт кнопку для отображения текущей даты и времени.
        Подключает переданный callback к сигналу clicked.
        """
        btn = ButtonFactory.create_button(
            parent,
            text="",  # текст будет обновляться снаружи
            bg_color=(255, 255, 255, 0.1),  # полупрозрачный белый
            text_color="#ffffff",
            padding="8px 12px",
            border_radius=10,
            border="1px solid rgba(255, 255, 255, 0.3)",
            font_size=14,
            font_weight="bold",
            object_name="datetime_btn",
            cursor_shape=Qt.PointingHandCursor,
            # Дополнительный hover-стиль, так как автоматический не подойдёт из-за полупрозрачности
            extra_style="""
                QPushButton#datetime_btn:hover {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def _apply_button_style(btn, bg_color, text_color=None, padding="8px 16px",
                            border_radius=5, border="none", font_size=None,
                            font_weight=None, extra_style="", hover_color=None):
        """
        Применяет стиль к любой кнопке (QPushButton или ProcessButton).
        """
        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        text_c = BaseWidgetFactory.calc_text_color(bg_color, text_color)
        hover_c = hover_color if hover_color else BaseWidgetFactory.calc_hover_color(bg_color)

        selector = f"QPushButton#{btn.objectName()}" if btn.objectName() else "QPushButton"

        style = f"""
                {selector} {{
                    background-color: {bg_c};
                    color: {text_c};
                    padding: {padding};
                    border: {border};
                    border-radius: {border_radius}px;
            """
        if font_size:
            style += f"font-size: {font_size}px;"
        if font_weight:
            style += f"font-weight: {font_weight};"
        style += "}"

        if hover_c:
            style += f"""
                {selector}:hover {{
                    background-color: {hover_c};
                }}
                """
        if extra_style:
            style += extra_style

        btn.setStyleSheet(style)

    @staticmethod
    def create_buttons_from_config(parent, configs, handlers=None):
        """
        Создаёт несколько кнопок на основе списка конфигураций.

        Формат элемента конфигурации (кортеж длиной от 3 до 8):
            (attr, text, color [, padding, fixed_size, object_name, cursor_shape, extra_style])

        Если кортеж короче, недостающие параметры берутся по умолчанию.
        """
        if handlers is None:
            handlers = {}
        created = {}

        for cfg in configs:
            # Обязательные первые три элемента
            attr = cfg[0]
            text = cfg[1]
            color = cfg[2]

            # Опциональные элементы
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
    def create_delete_button(parent, callback, size=(22, 22), bg_color=(176, 80, 80)):
        """
        Создаёт стандартную кнопку удаления (крестик) для строк списков.

        Параметры:
            parent    – родительский виджет.
            callback  – функция, вызываемая при нажатии.
            size      – кортеж (ширина, высота) кнопки.
            bg_color  – цвет фона кнопки.

        Возвращает:
            QPushButton с текстом "✕", стилизованный под кнопку удаления.
        """
        btn = ButtonFactory.create_button(
            parent,
            text="✕",
            bg_color=bg_color,
            fixed_size=size,
            padding="0px"  # убираем внутренние отступы, чтобы крестик был по центру
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_add_button(parent, callback, size=(40, 40), bg_color=(255, 255, 255, 0.15),
                          border="1px solid rgba(255, 255, 255, 0.3)",
                          font_size=18, hover_color=(255, 255, 255, 0.3)):
        """
        Создаёт стандартную круглую кнопку добавления "+".

        Параметры:
            parent      – родительский виджет.
            callback    – функция, вызываемая при нажатии.
            size        – кортеж (ширина, высота).
            bg_color    – цвет фона кнопки.
            border      – рамка.
            font_size   – размер шрифта.
            hover_color – цвет фона при наведении.

        Возвращает:
            QPushButton с текстом "+", стилизованный как кнопка добавления.
        """
        btn = ButtonFactory.create_button(
            parent,
            text="+",
            bg_color=bg_color,
            fixed_size=size,
            border_radius=size[0] // 2,  # делаем круглой (радиус = половина ширины)
            border=border,
            font_size=font_size,
            hover_color=hover_color
        )
        # Добавляем белый цвет текста, если не определён автоматически
        btn.setStyleSheet(btn.styleSheet() + f" QPushButton {{ color: white; }}")
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_complete_button(parent, callback, size=(26, 26), bg_color=(70, 150, 90)):
        """
        Создаёт кнопку выполнения задачи (галочка).
        """
        btn = ButtonFactory.create_button(
            parent,
            text="✓",
            bg_color=bg_color,
            fixed_size=size,
            padding="0px",
            font_size=14,
            font_weight="bold",
            hover_color=(90, 170, 110)
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_edit_button(parent, callback, size=(26, 26), bg_color=(120, 120, 150)):
        """
        Создаёт кнопку редактирования (карандаш).
        """
        btn = ButtonFactory.create_button(
            parent,
            text="✎",
            bg_color=bg_color,
            fixed_size=size,
            padding="0px",
            font_size=14,
            hover_color=(140, 140, 170)
        )
        btn.clicked.connect(callback)
        return btn

    @staticmethod
    def create_pause_button(parent, callback, paused=False, size=(26, 26), bg_color=(180, 150, 70)):
        """
        Создаёт кнопку паузы/возобновления (⏸/▶).
        """
        text = "▶" if paused else "⏸"
        btn = ButtonFactory.create_button(
            parent,
            text=text,
            bg_color=bg_color,
            fixed_size=size,
            padding="0px",
            font_size=14,
            hover_color=(200, 170, 90)
        )
        btn.clicked.connect(callback)
        return btn

class StatusLabel(QLabel):
    """
    Специализированная метка для отображения статусных сообщений.
    Имеет встроенный сигнал status_update, подключённый к setText.
    """
    status_update = Signal(str)

    def __init__(self, parent=None, text="", bg_color=(0, 0, 0, 0),
                 text_color="#d4d4d4", padding="10px", border_radius=0,
                 alignment=Qt.AlignCenter, font_size=None, font_weight=None):
        super().__init__(text, parent)
        self.setAlignment(alignment)
        self.setWordWrap(True)

        # Применяем стиль
        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)

        style = f"""
            QLabel {{
                background-color: {bg_c};
                color: {text_color};
                padding: {padding};
                border-radius: {border_radius}px;
        """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_weight is not None:
            style += f"font-weight: {font_weight};"
        style += "}"
        self.setStyleSheet(style)

        # Подключаем сигнал к обновлению текста
        self.status_update.connect(self.setText)

class LabelFactory(BaseWidgetFactory):
    """Фабрика для создания стилизованных меток (QLabel)."""

    @staticmethod
    def create_label(parent, text="", bg_color=(64, 48, 66), text_color=None,
                     padding="4px 8px", border_radius=5, fixed_size=None,
                     alignment=Qt.AlignCenter, font_family=None, font_size=None,
                     object_name=None, cursor_shape=None, border="none",
                     font_weight=None, extra_style="", word_wrap=False,
                     tooltip=None, min_size=None, max_size=None):
        """
        Универсальное создание стилизованной метки.

        Параметры:
            parent        – родительский виджет.
            text          – текст метки.
            bg_color      – цвет фона (кортеж (r,g,b) или (r,g,b,a) или строка).
            text_color    – цвет текста (если None, подбирается автоматически).
            padding       – внутренние отступы (CSS-подобная строка).
            border_radius – радиус скругления углов (целое число).
            fixed_size    – фиксированный размер (width, height) или None.
            alignment     – выравнивание текста (Qt.Align...).
            font_family   – семейство шрифта.
            font_size     – размер шрифта в пикселях.
            object_name   – objectName для селекторной стилизации.
            cursor_shape  – курсор при наведении.
            border        – стиль рамки (например, "1px solid #5a4a5c").
            font_weight   – насыщенность шрифта.
            extra_style   – дополнительный CSS.
            word_wrap     – переносить ли текст по словам.
            tooltip       – всплывающая подсказка.
            min_size      – минимальный размер (width, height) или None.
            max_size      – максимальный размер (width, height) или None.
        """
        lbl = QLabel(text, parent)

        # Устанавливаем objectName до применения стиля
        if object_name:
            lbl.setObjectName(object_name)
        if cursor_shape is not None:
            lbl.setCursor(cursor_shape)
        if tooltip:
            lbl.setToolTip(tooltip)
        if min_size:
            lbl.setMinimumSize(*min_size)
        if max_size:
            lbl.setMaximumSize(*max_size)
        if fixed_size:
            lbl.setFixedSize(*fixed_size)

        lbl.setAlignment(alignment)
        lbl.setWordWrap(word_wrap)

        # Получаем цветовые строки через базовые методы
        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        tc = BaseWidgetFactory.calc_text_color(bg_color, text_color)

        # Селектор стиля
        selector = f"QLabel#{object_name}" if object_name else "QLabel"

        # Собираем основной стиль
        style = f"""
            {selector} {{
                background-color: {bg_c};
                color: {tc};
                padding: {padding};
                border: {border};
                border-radius: {border_radius}px;
        """
        if font_family:
            style += f"font-family: {font_family};"
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_weight is not None:
            style += f"font-weight: {font_weight};"
        style += "}"

        lbl.setStyleSheet(style)

        if extra_style:
            lbl.setStyleSheet(lbl.styleSheet() + extra_style)

        return lbl

    @staticmethod
    def create_header_label(parent, text, alignment=Qt.AlignCenter, **kwargs):
        """
        Создаёт метку-заголовок окна с единым стилем.

        Параметры:
            parent    – родительский виджет.
            text      – текст заголовка.
            alignment – выравнивание текста (по умолчанию Qt.AlignCenter).
            **kwargs  – дополнительные параметры, передаваемые в create_label.

        Возвращает:
            QLabel с прозрачным фоном и светло-серым текстом.
        """
        return LabelFactory.create_label(
            parent,
            text=text,
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            alignment=alignment,
            **kwargs
        )


    @staticmethod
    def create_status_label(parent, text="", **kwargs):
        """
        Создаёт статусную метку с встроенным сигналом status_update.

        Параметры:
            parent  – родительский виджет.
            text    – начальный текст.
            **kwargs – дополнительные параметры для StatusLabel (bg_color, text_color, padding и т.д.).

        Возвращает:
            StatusLabel с подключённым сигналом.
        """
        return StatusLabel(parent, text=text, **kwargs)

class ProgressFactory(BaseWidgetFactory):
    """Фабрика для создания индикаторов прогресса (QProgressBar)."""

    @staticmethod
    def create_progress_bar(parent, min_value=0, max_value=100, value=0,
                            orientation=Qt.Horizontal, text_visible=True,
                            bg_color=(60, 50, 70, 0.9), chunk_color=(100, 80, 120),
                            text_color=None, border="none", border_radius=5,
                            padding="0px", fixed_size=None, object_name=None,
                            cursor_shape=None, tooltip=None,
                            font_size=None, font_weight=None,
                            extra_style=""):
        """
        Создаёт стилизованный прогресс-бар.

        Параметры:
            parent        – родительский виджет.
            min_value     – минимальное значение.
            max_value     – максимальное значение.
            value         – текущее значение (должно быть в пределах [min_value, max_value]).
            orientation   – ориентация (Qt.Horizontal или Qt.Vertical).
            text_visible  – отображать ли текст (процент выполнения).
            bg_color      – цвет фона канала прогресса.
            chunk_color   – цвет заполнителя (прогресса).
            text_color    – цвет текста (если None, подбирается автоматически на основе фона).
            border        – рамка.
            border_radius – радиус скругления углов.
            padding       – внутренние отступы.
            fixed_size    – фиксированный размер (ширина, высота).
            object_name   – objectName для точечной стилизации.
            cursor_shape  – курсор при наведении.
            tooltip       – всплывающая подсказка.
            font_size     – размер шрифта текста.
            font_weight   – насыщенность шрифта.
            extra_style   – дополнительный CSS.

        Возвращает:
            QProgressBar с заданными параметрами.
        """
        progress = QProgressBar(parent)
        progress.setRange(min_value, max_value)
        progress.setValue(value)
        progress.setOrientation(orientation)
        progress.setTextVisible(text_visible)

        if object_name:
            progress.setObjectName(object_name)
        if cursor_shape is not None:
            progress.setCursor(cursor_shape)
        if tooltip:
            progress.setToolTip(tooltip)
        if fixed_size:
            progress.setFixedSize(*fixed_size)

        # Определяем цвет текста
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color, forced="#ffffff")
        else:
            text_color = text_color

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        chunk_c = BaseWidgetFactory.color_to_str(chunk_color)

        selector = f"QProgressBar#{object_name}" if object_name else "QProgressBar"

        style = f"""
            {selector} {{
                background-color: {bg_c};
                color: {text_color};
                border: {border};
                border-radius: {border_radius}px;
                padding: {padding};
                text-align: center;
        """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_weight is not None:
            style += f"font-weight: {font_weight};"
        style += "}"
        style += f"""
            {selector}::chunk {{
                background-color: {chunk_c};
                border-radius: {border_radius}px;
            }}
        """

        progress.setStyleSheet(style)
        if extra_style:
            progress.setStyleSheet(progress.styleSheet() + extra_style)

        return progress

class InputWidgetFactory(BaseWidgetFactory):
    """Фабрика для создания элементов ввода: QLineEdit, QCheckBox, QComboBox."""

    @staticmethod
    def create_line_edit(parent, text="", placeholder="",
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=3,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         read_only=False, max_length=None,
                         alignment=None, font_size=None, font_family=None,
                         extra_style="", min_size=None, max_size=None):
        """
        Создаёт стилизованное однострочное текстовое поле.

        Параметры:
            parent        – родительский виджет.
            text          – начальный текст.
            placeholder   – текст-подсказка, когда поле пустое.
            bg_color      – цвет фона.
            text_color    – цвет текста.
            border        – стиль рамки.
            border_radius – радиус скругления.
            padding       – внутренние отступы.
            fixed_size    – фиксированный размер (ширина, высота).
            object_name   – objectName для точечной стилизации.
            cursor_shape  – курсор при наведении.
            read_only     – только для чтения.
            max_length    – максимальная длина ввода.
            alignment     – выравнивание текста (Qt.Align...).
            font_size     – размер шрифта.
            font_family   – семейство шрифта.
            extra_style   – дополнительный CSS.
            min_size      – минимальный размер.
            max_size      – максимальный размер.
        """
        line_edit = QLineEdit(text, parent)

        if object_name:
            line_edit.setObjectName(object_name)
        if cursor_shape is not None:
            line_edit.setCursor(cursor_shape)
        if read_only:
            line_edit.setReadOnly(True)
        if max_length:
            line_edit.setMaxLength(max_length)
        if placeholder:
            line_edit.setPlaceholderText(placeholder)
        if alignment is not None:
            line_edit.setAlignment(alignment)
        if fixed_size:
            line_edit.setFixedSize(*fixed_size)
        if min_size:
            line_edit.setMinimumSize(*min_size)
        if max_size:
            line_edit.setMaximumSize(*max_size)

        # Получаем цвет текста с учётом фона (можно использовать calc_text_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        bg_c = BaseWidgetFactory.color_to_str(bg_color)

        selector = f"QLineEdit#{object_name}" if object_name else "QLineEdit"
        style = f"""
            {selector} {{
                background-color: {bg_c};
                color: {text_color};
                border: {border};
                border-radius: {border_radius}px;
                padding: {padding};
        """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_family:
            style += f"font-family: {font_family};"
        style += "}"

        line_edit.setStyleSheet(style)
        if extra_style:
            line_edit.setStyleSheet(line_edit.styleSheet() + extra_style)

        return line_edit

    @staticmethod
    def create_checkbox(parent, text, checked=False,
                        bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
                        border="none", border_radius=0, padding="0px",
                        fixed_size=None, object_name=None, cursor_shape=None,
                        font_size=None, font_weight=None,
                        extra_style="", tooltip=None,
                        indicator_size=(16, 16), indicator_bg_color=(200, 200, 200),
                        indicator_border="1px solid #888888",
                        indicator_checked_bg_color=(180, 180, 180),
                        indicator_border_radius=3):
        """
        Создаёт стилизованный чекбокс.

        Параметры:
            parent        – родительский виджет.
            text          – текст рядом с чекбоксом.
            checked       – начальное состояние (True/False).
            bg_color      – цвет фона (по умолчанию прозрачный).
            text_color    – цвет текста.
            border        – рамка.
            border_radius – радиус скругления фона.
            padding       – внутренние отступы.
            fixed_size    – фиксированный размер.
            object_name   – objectName.
            cursor_shape  – курсор.
            font_size     – размер шрифта.
            font_weight   – насыщенность шрифта.
            extra_style   – дополнительный CSS.
            tooltip       – подсказка.
            indicator_size              – размер квадратика (ширина, высота).
        indicator_bg_color          – цвет фона индикатора в обычном состоянии.
        indicator_border            – рамка индикатора.
        indicator_checked_bg_color  – цвет фона индикатора в отмеченном состоянии.
        indicator_border_radius     – радиус скругления углов индикатора.
        """
        checkbox = QCheckBox(text, parent)
        checkbox.setChecked(checked)

        if object_name:
            checkbox.setObjectName(object_name)
        if cursor_shape is not None:
            checkbox.setCursor(cursor_shape)
        if tooltip:
            checkbox.setToolTip(tooltip)
        if fixed_size:
            checkbox.setFixedSize(*fixed_size)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QCheckBox#{object_name}" if object_name else "QCheckBox"

        indicator_bg_c = BaseWidgetFactory.color_to_str(indicator_bg_color)
        indicator_checked_c = BaseWidgetFactory.color_to_str(indicator_checked_bg_color)

        style = f"""
               {selector} {{
                   background-color: {bg_c};
                   color: {text_color};
                   border: {border};
                   border-radius: {border_radius}px;
                   padding: {padding};
           """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_weight is not None:
            style += f"font-weight: {font_weight};"
        style += "}"

        # Стиль индикатора (квадратика)
        style += f"""
               {selector}::indicator {{
                   width: {indicator_size[0]}px;
                   height: {indicator_size[1]}px;
                   background-color: {indicator_bg_c};
                   border: {indicator_border};
                   border-radius: {indicator_border_radius}px;
               }}
               {selector}::indicator:checked {{
                   background-color: {indicator_checked_c};
               }}
           """

        checkbox.setStyleSheet(style)
        if extra_style:
            checkbox.setStyleSheet(checkbox.styleSheet() + extra_style)

        return checkbox

    @staticmethod
    def create_combo_box(parent, items=None, current_index=0,
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=3,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         font_size=None, font_family=None,
                         extra_style="", tooltip=None):
        """
        Создаёт стилизованный выпадающий список (QComboBox).
        Пока не используется, но добавлен для расширяемости.
        """
        combo = QComboBox(parent)
        if items:
            combo.addItems(items)
            combo.setCurrentIndex(current_index)

        if object_name:
            combo.setObjectName(object_name)
        if cursor_shape is not None:
            combo.setCursor(cursor_shape)
        if tooltip:
            combo.setToolTip(tooltip)
        if fixed_size:
            combo.setFixedSize(*fixed_size)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QComboBox#{object_name}" if object_name else "QComboBox"

        style = f"""
            {selector} {{
                background-color: {bg_c};
                color: {text_color};
                border: {border};
                border-radius: {border_radius}px;
                padding: {padding};
        """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        if font_family:
            style += f"font-family: {font_family};"
        style += "}"

        combo.setStyleSheet(style)
        if extra_style:
            combo.setStyleSheet(combo.styleSheet() + extra_style)

        return combo

    @staticmethod
    def create_default_line_edit(parent, text="", **kwargs):
        """
        Создаёт поле ввода с тёмным стилем, используемым по умолчанию.

        Параметры:
            parent  – родительский виджет.
            text    – начальный текст.
            **kwargs – дополнительные параметры, передаваемые в create_line_edit.

        Возвращает:
            QLineEdit с предустановленным тёмным стилем.
        """
        return InputWidgetFactory.create_line_edit(
            parent,
            text=text,
            bg_color=(60, 50, 70, 0.9),
            text_color="#d4d4d4",
            border="1px solid #5a4a5c",
            border_radius=3,
            padding="3px",
            **kwargs
        )

    @staticmethod
    def create_text_edit(parent, text="", placeholder="",
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=5,
                         padding="5px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         read_only=False, font_size=None, extra_style="",
                         enabled=True):
        """
        Создаёт стилизованное многострочное текстовое поле (QTextEdit).
        """
        te = QTextEdit(parent)
        if text:
            te.setPlainText(text)
        if placeholder:
            te.setPlaceholderText(placeholder)
        if object_name:
            te.setObjectName(object_name)
        if cursor_shape is not None:
            te.setCursor(cursor_shape)
        if read_only:
            te.setReadOnly(True)
        if fixed_size:
            te.setFixedSize(*fixed_size)
        te.setEnabled(enabled)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)

        selector = f"QTextEdit#{object_name}" if object_name else "QTextEdit"
        style = f"""
                {selector} {{
                    background-color: {bg_c};
                    color: {text_color};
                    border: {border};
                    border-radius: {border_radius}px;
                    padding: {padding};
            """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        style += "}"
        te.setStyleSheet(style)
        if extra_style:
            te.setStyleSheet(te.styleSheet() + extra_style)
        return te

    @staticmethod
    def create_spin_box(parent, min_value=0, max_value=999, value=0,
                        prefix="", suffix="",
                        bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                        border="1px solid #5a4a5c", border_radius=5,
                        padding="3px", fixed_size=None,
                        object_name=None, cursor_shape=None,
                        font_size=None, extra_style=""):
        """
        Создаёт стилизованное числовое поле (QSpinBox).
        """
        spin = QSpinBox(parent)
        spin.setRange(min_value, max_value)
        spin.setValue(value)
        spin.setButtonSymbols(QAbstractSpinBox.UpDownArrows)  # <-- добавлено
        if prefix:
            spin.setPrefix(prefix)
        if suffix:
            spin.setSuffix(suffix)
        if object_name:
            spin.setObjectName(object_name)
        if cursor_shape is not None:
            spin.setCursor(cursor_shape)
        if fixed_size:
            spin.setFixedSize(*fixed_size)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QSpinBox#{object_name}" if object_name else "QSpinBox"
        style = f"""
               {selector} {{
                   background-color: {bg_c};
                   color: {text_color};
                   border: {border};
                   border-radius: {border_radius}px;
                   padding: {padding};
                   padding-right: 20px;   /* <-- добавлено */
           """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        style += "}"

        spin.setStyleSheet(style)
        if extra_style:
            spin.setStyleSheet(spin.styleSheet() + extra_style)

        return spin

    @staticmethod
    def create_datetime_edit(parent, value=None,
                             bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                             border="1px solid #5a4a5c", border_radius=5,
                             padding="3px", fixed_size=None,
                             object_name=None, cursor_shape=None,
                             font_size=None, extra_style=""):
        """
        Создаёт стилизованное поле выбора даты/времени (QDateTimeEdit).
        """
        dt = QDateTimeEdit(parent)
        dt.setButtonSymbols(QAbstractSpinBox.UpDownArrows)  # показываем кнопки вверх/вниз
        if value is not None:
            dt.setDateTime(value)
        else:
            dt.setDateTime(QDateTime.currentDateTime())
        if object_name:
            dt.setObjectName(object_name)
        if cursor_shape is not None:
            dt.setCursor(cursor_shape)
        if fixed_size:
            dt.setFixedSize(*fixed_size)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QDateTimeEdit#{object_name}" if object_name else "QDateTimeEdit"

        style = f"""
                {selector} {{
                    background-color: {bg_c};
                    color: {text_color};
                    border: {border};
                    border-radius: {border_radius}px;
                    padding: {padding};
                    padding-right: 20px;   /* освобождаем место под кнопки */
            """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        style += "}"

        # Стили для внутренних кнопок, чтобы они имели отдельные зоны клика


        dt.setStyleSheet(style)
        if extra_style:
            dt.setStyleSheet(dt.styleSheet() + extra_style)

        return dt

    @staticmethod
    def create_date_edit(parent, value=None,
                         bg_color=(60, 50, 70, 0.9), text_color="#d4d4d4",
                         border="1px solid #5a4a5c", border_radius=5,
                         padding="3px", fixed_size=None,
                         object_name=None, cursor_shape=None,
                         font_size=None, extra_style="",
                         display_format="dd.MM.yyyy"):
        """
        Создаёт стилизованное поле выбора даты (QDateEdit).
        """
        de = QDateEdit(parent)
        if value is None:
            value = QDate.currentDate()
        de.setDate(value)
        de.setDisplayFormat(display_format)

        if object_name:
            de.setObjectName(object_name)
        if cursor_shape is not None:
            de.setCursor(cursor_shape)
        if fixed_size:
            de.setFixedSize(*fixed_size)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QDateEdit#{object_name}" if object_name else "QDateEdit"

        style = f"""
                {selector} {{
                    background-color: {bg_c};
                    color: {text_color};
                    border: {border};
                    border-radius: {border_radius}px;
                    padding: {padding};
            """
        if font_size is not None:
            style += f"font-size: {font_size}px;"
        style += "}"

        de.setStyleSheet(style)
        if extra_style:
            de.setStyleSheet(de.styleSheet() + extra_style)
        return de

class ListWidgetFactory(BaseWidgetFactory):
    """Фабрика для создания списков и прокручиваемых областей."""

    @staticmethod
    def create_list_widget(parent, fixed_width=None, fixed_height=None,
                           min_size=None, max_size=None,
                           horizontal_scroll=True, vertical_scroll=True,
                           selection_mode=QListWidget.SingleSelection,
                           bg_color=(30, 20, 35, 0.3), text_color="#d4d4d4",
                           border_radius=5, padding="0px", border="none",
                           font_size=10, object_name=None, cursor_shape=None,
                           extra_style=""):
        """
        Создаёт стилизованный QListWidget.

        Параметры:
            parent            – родительский виджет.
            fixed_width       – фиксированная ширина (в пикселях) или None.
            fixed_height      – фиксированная высота (в пикселях) или None.
            min_size          – минимальный размер (ширина, высота).
            max_size          – максимальный размер (ширина, высота).
            horizontal_scroll – разрешить горизонтальную прокрутку.
            vertical_scroll   – разрешить вертикальную прокрутку.
            selection_mode    – режим выделения элементов.
            bg_color          – цвет фона.
            text_color        – цвет текста.
            border_radius     – радиус скругления.
            padding           – внутренние отступы.
            border            – рамка.
            font_size         – размер шрифта.
            object_name       – objectName.
            cursor_shape      – курсор.
            extra_style       – дополнительный CSS.
        """
        list_widget = QListWidget(parent)

        if object_name:
            list_widget.setObjectName(object_name)
        if cursor_shape is not None:
            list_widget.setCursor(cursor_shape)
        if fixed_width:
            list_widget.setFixedWidth(fixed_width)
        if fixed_height:
            list_widget.setFixedHeight(fixed_height)
        if min_size:
            list_widget.setMinimumSize(*min_size)
        if max_size:
            list_widget.setMaximumSize(*max_size)
        if not horizontal_scroll:
            list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if not vertical_scroll:
            list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setSelectionMode(selection_mode)

        # Политика размера: если задана фиксированная ширина, ставим Fixed
        if fixed_width:
            list_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        else:
            list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        if text_color is None:
            text_color = BaseWidgetFactory.calc_text_color(bg_color)
        selector = f"QListWidget#{object_name}" if object_name else "QListWidget"

        style = f"""
            {selector} {{
                background-color: {bg_c};
                color: {text_color};
                border: {border};
                border-radius: {border_radius}px;
                padding: {padding};
                font-size: {font_size}px;
            }}
            {selector}::item {{
                padding: 2px;
            }}
        """
        list_widget.setStyleSheet(style)
        if extra_style:
            list_widget.setStyleSheet(list_widget.styleSheet() + extra_style)

        return list_widget

    @staticmethod
    def create_scroll_area(parent, widget=None, bg_color=(0,0,0,0),
                           border="none", border_radius=0,
                           widget_resizable=True, object_name=None,
                           cursor_shape=None, extra_style=""):
        """
        Создаёт прокручиваемую область с прозрачным фоном и помещает в неё виджет.

        Параметры:
            parent           – родительский виджет.
            widget           – виджет, который будет помещён в область (если задан).
            bg_color         – цвет фона области.
            border           – рамка.
            border_radius    – радиус скругления.
            widget_resizable – разрешить автоматическое изменение размеров виджета.
            object_name      – objectName.
            cursor_shape     – курсор.
            extra_style      – дополнительный CSS.
        """
        scroll = QScrollArea(parent)
        if object_name:
            scroll.setObjectName(object_name)
        if cursor_shape is not None:
            scroll.setCursor(cursor_shape)
        scroll.setWidgetResizable(widget_resizable)

        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        selector = f"QScrollArea#{object_name}" if object_name else "QScrollArea"
        style = f"""
            {selector} {{
                background: {bg_c};
                border: {border};
                border-radius: {border_radius}px;
            }}
        """
        scroll.setStyleSheet(style)
        if extra_style:
            scroll.setStyleSheet(scroll.styleSheet() + extra_style)

        if widget is not None:
            scroll.setWidget(widget)

        return scroll

    def create_scroll_container(parent, spacing=2, margins=(0, 0, 0, 0)):
        """
        Создаёт прокручиваемую область с внутренним виджетом и вертикальным layout.

        Параметры:
            parent  – родительский виджет (обычно окно).
            spacing – расстояние между элементами в layout.
            margins – отступы layout (left, top, right, bottom).

        Возвращает:
            (scroll_area, content_widget, content_layout)
            scroll_area     – QScrollArea, настроенная для отображения виджета.
            content_widget  – QWidget, который помещён внутрь scroll_area.
            content_layout  – QVBoxLayout, привязанный к content_widget.
        """
        # Создаём контейнерный виджет и layout
        content_widget = QWidget(parent)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(*margins)
        content_layout.setSpacing(spacing)

        # Создаём прокручиваемую область и помещаем в неё виджет
        scroll_area = ListWidgetFactory.create_scroll_area(
            parent, widget=content_widget, widget_resizable=True
        )

        return scroll_area, content_widget, content_layout






class LayoutFactory:
    """
    Фабрика для создания контейнеров с различными компоновками.
    Все методы возвращают QWidget, который можно вставлять в родительские макеты.
    """

    # ------------------------------------------------------------------
    # Горизонтальная компоновка (QHBoxLayout)
    # ------------------------------------------------------------------
    @staticmethod
    def create_row(parent, *widgets, spacing=10, margins=(0, 0, 0, 0),
                   alignment=Qt.AlignCenter, fixed_width=None, fixed_height=None,
                   stretch_factors=None, background_color="transparent",
                   object_name=None):
        """
        Создаёт горизонтальный контейнер (QWidget с QHBoxLayout).

        Все виджеты размещаются в одну строку слева направо.

        Параметры:
            parent           – родительский виджет.
            *widgets         – виджеты, которые нужно разместить.
            spacing          – расстояние между виджетами (px).
            margins          – отступы контейнера (left, top, right, bottom).
            alignment        – выравнивание всей строки (Qt.AlignLeft, Qt.AlignCenter и т.д.).
            fixed_width      – фиксированная ширина контейнера (если нужна).
            fixed_height     – фиксированная высота контейнера.
            stretch_factors  – список коэффициентов растяжения для виджетов (аналогично addWidget(w, stretch)).
            background_color – цвет фона контейнера (строка CSS, например "transparent").
            object_name      – objectName для точечной стилизации.

        Возвращает:
            QWidget с установленным QHBoxLayout.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            if stretch_factors and i < len(stretch_factors):
                layout.addWidget(w, stretch_factors[i])
            else:
                layout.addWidget(w)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    # ------------------------------------------------------------------
    # Вертикальная компоновка (QVBoxLayout)
    # ------------------------------------------------------------------
    @staticmethod
    def create_column(parent, *widgets, spacing=10, margins=(0, 0, 0, 0),
                      alignment=Qt.AlignCenter, fixed_width=None, fixed_height=None,
                      stretch_factors=None, background_color="transparent",
                      object_name=None):
        """
        Создаёт вертикальный контейнер (QWidget с QVBoxLayout).

        Виджеты размещаются сверху вниз.

        Параметры аналогичны create_row, за исключением направления.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            if stretch_factors and i < len(stretch_factors):
                layout.addWidget(w, stretch_factors[i])
            else:
                layout.addWidget(w)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    # ------------------------------------------------------------------
    # Сеточная компоновка (QGridLayout)
    # ------------------------------------------------------------------
    @staticmethod
    def create_grid(parent, widgets, columns, spacing=10, margins=(0, 0, 0, 0),
                    alignment=Qt.AlignCenter, fixed_width=None, fixed_height=None,
                    background_color="transparent", object_name=None):
        """
        Создаёт контейнер с сеткой (QGridLayout).

        Виджеты автоматически размещаются построчно с заданным количеством столбцов.
        Подходит для карточек, плиток, форм с нестандартным расположением.

        Параметры:
            parent           – родительский виджет.
            widgets          – список виджетов.
            columns          – количество столбцов.
            spacing          – расстояние между ячейками.
            margins          – отступы.
            alignment        – выравнивание всей сетки.
            fixed_width      – фиксированная ширина.
            fixed_height     – фиксированная высота.
            background_color – цвет фона.
            object_name      – objectName.

        Возвращает:
            QWidget с QGridLayout.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QGridLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            row = i // columns
            col = i % columns
            layout.addWidget(w, row, col)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    # ------------------------------------------------------------------
    # Формовая компоновка (QFormLayout)
    # ------------------------------------------------------------------
    @staticmethod
    def create_form(parent, rows, spacing=10, margins=(0, 0, 0, 0),
                    alignment=Qt.AlignLeft, fixed_width=None, fixed_height=None,
                    background_color="transparent", object_name=None):
        """
        Создаёт контейнер с формой (QFormLayout).

        Каждая строка состоит из метки (подписи) и виджета поля ввода.
        Удобно для диалогов с парами «Название: [поле]».

        Параметры:
            parent           – родительский виджет.
            rows             – список кортежей (label_widget, field_widget) или (label_text, field_widget).
                               Если первый элемент кортежа – строка, будет создана QLabel с этим текстом.
            spacing          – расстояние между строками.
            margins          – отступы.
            alignment        – выравнивание формы.
            fixed_width      – фиксированная ширина.
            fixed_height     – фиксированная высота.
            background_color – цвет фона.
            object_name      – objectName.

        Возвращает:
            QWidget с QFormLayout.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QFormLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for label, field in rows:
            if isinstance(label, str):
                label_widget = QLabel(label)
                # Можно добавить стилизацию, но для простоты оставляем стандартную
                layout.addRow(label_widget, field)
            else:
                layout.addRow(label, field)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    # ------------------------------------------------------------------
    # Стековая компоновка (QStackedLayout)
    # ------------------------------------------------------------------
    @staticmethod
    def create_stacked(parent, widgets, current_index=0, margins=(0, 0, 0, 0),
                       fixed_width=None, fixed_height=None,
                       background_color="transparent", object_name=None):
        """
        Создаёт контейнер со стеком виджетов (QStackedLayout).

        Одновременно отображается только один виджет, остальные скрыты.
        Переключение осуществляется программно через layout.setCurrentIndex().

        Параметры:
            parent           – родительский виджет.
            widgets          – список виджетов для стека.
            current_index    – индекс видимого изначально виджета.
            margins          – отступы.
            fixed_width      – фиксированная ширина.
            fixed_height     – фиксированная высота.
            background_color – цвет фона.
            object_name      – objectName.

        Возвращает:
            QWidget с QStackedLayout.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QStackedLayout(container)
        layout.setContentsMargins(*margins)

        for w in widgets:
            layout.addWidget(w)

        layout.setCurrentIndex(current_index)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def add_centered_widget(main_layout, widget):
        """
        Добавляет виджет в макет, центрируя его горизонтально.

        Параметры:
            main_layout – QVBoxLayout или QHBoxLayout, в который добавляется виджет.
            widget      – виджет, который нужно отцентрировать.

        Возвращает:
            Ничего (изменяет переданный макет).
        """
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(widget)
        h_layout.addStretch()
        main_layout.addLayout(h_layout)

class WindowFactory:
    """Фабрика для настройки и управления дочерними окнами."""

    @staticmethod
    def setup_child_window(child, title, bg_color=(64, 48, 66, 0.8),
                           close_callback=None, frameless=True,
                           stay_on_top=True, translucent_background=True,
                           close_button=True, close_button_color="#fd5e53",
                           return_layout=True):
        """
        Настраивает дочернее окно: рамка, прозрачность, кнопка закрытия, стиль.

        Параметры:
            child                  – экземпляр окна (QMainWindow или QDialog).
            title                  – заголовок окна.
            bg_color               – цвет фона центрального виджета (кортеж (r,g,b) или (r,g,b,a)).
            close_callback         – функция, вызываемая при нажатии кнопки закрытия (если None, окно просто закрывается).
            frameless              – True – без системной рамки; False – обычное окно.
            stay_on_top            – True – окно всегда поверх родителя.
            translucent_background – True – фон окна прозрачный (для закруглённых углов).
            close_button           – True – добавить стандартную кнопку закрытия «✕».
            close_button_color     – цвет фона кнопки закрытия.
            return_layout          – True – возвращает main_layout для дальнейшего наполнения.

        Возвращает:
            Если return_layout=True – QVBoxLayout центрального виджета, иначе None.
        """
        # Флаги окна
        flags = 0
        if frameless:
            flags |= Qt.FramelessWindowHint
        if stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        child.setWindowFlags(flags)

        if translucent_background:
            child.setAttribute(Qt.WA_TranslucentBackground)

        child.setWindowTitle(title)

        # Центральный виджет с заданным фоном
        central = QWidget()
        r, g, b, a = bg_color if len(bg_color) == 4 else (*bg_color, 0.8)
        central.setStyleSheet(f"""
            QWidget {{
                background-color: rgba({r}, {g}, {b}, {a});
                border-radius: 15px;
            }}
        """)
        child.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Кнопка закрытия
        if close_button:
            close_btn = QPushButton("✕")
            close_btn.setFixedSize(25, 25)
            close_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {close_button_color};
                    color: white;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                }}
                QPushButton:hover {{
                    background-color: #c10020;
                }}
            """)
            if close_callback:
                close_btn.clicked.connect(close_callback)
            else:
                close_btn.clicked.connect(child.close)

            close_layout = QHBoxLayout()
            close_layout.addStretch()
            close_layout.addWidget(close_btn)
            main_layout.addLayout(close_layout)

        if return_layout:
            return main_layout
        return None

    @staticmethod
    def show_child_window(parent, child, modal=True):
        if modal:
            child.setWindowModality(Qt.WindowModal)

        parent_rect = parent.frameGeometry()
        child.setGeometry(10, 10,
                          parent_rect.width() - 20,
                          parent_rect.height() - 50)
        child.show()
        child.activateWindow()

class FileDialogFactory:
    """Фабрика для создания и показа диалогов выбора файлов и папок."""
    SUPPORTED_FILES_FILTER = (
        "Поддерживаемые файлы (*.xlsx *.xls *.csv);;"
        "Excel (*.xlsx);;"
        "Excel 97-2003 (*.xls);;"
        "CSV (*.csv)"
    )

    @staticmethod
    def open_directory_dialog(parent, title="Выберите папку", default_dir=None,
                              options=None):
        """
        Открывает диалог выбора существующей папки.

        Параметры:
            parent      – родительский виджет.
            title       – заголовок окна диалога.
            default_dir – начальная папка (если None, используется домашняя папка).
            options     – дополнительные QFileDialog.Option (например, ShowDirsOnly).

        Возвращает:
            Строку с путём к выбранной папке или None, если пользователь отменил выбор.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        if options is not None:
            path = QFileDialog.getExistingDirectory(parent, title, default_dir, options)
        else:
            path = QFileDialog.getExistingDirectory(parent, title, default_dir)
        return path if path else None

    @staticmethod
    def open_file_dialog(parent, title="Выберите файл", default_dir=None,
                         filter="Все файлы (*.*)"):
        """
        Открывает диалог выбора одного файла.

        Параметры:
            parent      – родительский виджет.
            title       – заголовок окна.
            default_dir – начальная папка.
            filter      – фильтр файлов (например, "Excel (*.xlsx)").

        Возвращает:
            Строку с путём к выбранному файлу или None, если отменено.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(parent, title, default_dir, filter)
        return file_path if file_path else None

    @staticmethod
    def open_files_dialog(parent, title="Выберите файлы", default_dir=None,
                          filter="Все файлы (*.*)", multiple=True):
        """
        Открывает диалог выбора одного или нескольких файлов.

        Параметры:
            parent      – родительский виджет.
            title       – заголовок окна.
            default_dir – начальная папка.
            filter      – фильтр файлов (строка или список строк для нескольких фильтров).
            multiple    – True – разрешить выбор нескольких файлов, False – одного.

        Возвращает:
            Список путей к выбранным файлам или пустой список, если отменено.
            Если multiple=False, возвращает список с одним элементом (для единообразия).
        """
        if default_dir is None:
            default_dir = str(Path.home())

        # Поддержка нескольких фильтров, если передан список
        if isinstance(filter, (list, tuple)):
            filter_str = ";;".join(filter)
        else:
            filter_str = filter

        if multiple:
            files, _ = QFileDialog.getOpenFileNames(parent, title, default_dir, filter_str)
            return files if files else []
        else:
            file_path, _ = QFileDialog.getOpenFileName(parent, title, default_dir, filter_str)
            return [file_path] if file_path else []

    @staticmethod
    def open_save_file_dialog(parent, title="Сохранить файл", default_dir=None,
                              default_file="", filter="Все файлы (*.*)"):
        """
        Открывает диалог сохранения файла.

        Параметры:
            parent       – родительский виджет.
            title        – заголовок окна.
            default_dir  – начальная папка.
            default_file – имя файла по умолчанию.
            filter       – фильтр типов файлов.

        Возвращает:
            Строку с путём для сохранения или None, если отменено.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        if default_file:
            start = str(Path(default_dir) / default_file)
        else:
            start = default_dir
        file_path, _ = QFileDialog.getSaveFileName(parent, title, start, filter)
        return file_path if file_path else None



class ThreadFactory:
    """
    Фабрика для запуска функций в фоновых потоках.
    Обеспечивает безопасное взаимодействие с интерфейсом Qt.
    """

    @staticmethod
    def create_thread(parent, buttons, target_func, args=(), kwargs=None,
                      on_finished=None, error_callback=None):
        if kwargs is None:
            kwargs = {}

        # Блокируем кнопки
        for btn_name in buttons:
            btn = getattr(parent, btn_name, None)
            if btn:
                btn.setEnabled(False)

        thread_error = None

        def wrapper():
            nonlocal thread_error
            try:
                target_func(*args, **kwargs)
            except Exception as e:
                thread_error = str(e)

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()

        def check():
            if thread.is_alive():
                QTimer.singleShot(200, check)
            else:
                for btn_name in buttons:
                    btn = getattr(parent, btn_name, None)
                    if btn:
                        btn.setEnabled(True)
                if thread_error is not None:
                    if error_callback:
                        error_callback(thread_error)
                elif on_finished:
                    on_finished()

        check()

    @staticmethod
    def run_in_thread(target_func, args=(), kwargs=None,
                      on_finished=None, error_callback=None):
        """
        Простой запуск функции в фоновом потоке без блокировки кнопок.

        Параметры:
            target_func    – функция для выполнения.
            args           – позиционные аргументы.
            kwargs         – именованные аргументы.
            on_finished    – вызывается в главном потоке после успешного завершения.
            error_callback – вызывается при ошибке (получает текст исключения).

        Возвращает:
            Объект threading.Thread (можно сохранить, но обычно не требуется).
        """
        if kwargs is None:
            kwargs = {}

        def wrapper():
            try:
                result = target_func(*args, **kwargs)
                if on_finished:
                    QTimer.singleShot(0, lambda: on_finished(result))
            except Exception as e:
                if error_callback:
                    QTimer.singleShot(0, lambda: error_callback(str(e)))

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return thread


