"""
Фабрики простых элементов: меток и статусных надписей.

Содержит два класса:
    StatusLabel  — QLabel со встроенным сигналом status_update.
    LabelFactory — метки и заголовки.

Крупные фабрики вынесены отдельно:
    ButtonFactory — в button_factory.py.
    InputWidgetFactory — в input_factory.py.

QSS собирается через ui.styles.WidgetStyle.apply_label.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel

from ui.styles import WidgetStyle


class StatusLabel(QLabel):
    """QLabel для отображения статусных сообщений.

    Назначение:
        Имеет встроенный сигнал status_update(str), подключённый
        к setText. Это позволяет эмитить сообщение из любого
        потока — Qt доставит его в главный через queued connection.

    Роль в программе:
        Используется в окнах (ChzMPWindow, ReturnsWindow) для
        коротких подсказок. Не путать со StatusLog — там QTextEdit
        для прокручиваемого лога.

    Сигналы:
        status_update(str) — эмитится вызывающим кодом, ловится
                             самим же виджетом и обновляет текст.
    """
    status_update = Signal(str)

    def __init__(self, parent=None, text="", bg_color=(0, 0, 0, 0),
                 text_color="#d4d4d4", padding="10px", border_radius=0,
                 alignment=Qt.AlignCenter, font_size=None,
                 font_weight=None):
        """Конструктор.

        Вход:
            parent — родитель.
            text — начальный текст.
            bg_color — фон. Прозрачный по умолчанию.
            text_color — цвет текста. None → контрастный к фону.
            padding — внутренние отступы (CSS).
            border_radius — радиус скругления в px.
            alignment — Qt.AlignmentFlag.
            font_size — размер шрифта в px.
            font_weight — насыщенность шрифта.

        Роль: QSS собирается через WidgetStyle.apply_label,
              затем подключается status_update к setText.

        REPLACE: ручная сборка QSS заменена на WidgetStyle.apply_label.
        """
        super().__init__(text, parent)
        self.setAlignment(alignment)
        self.setWordWrap(True)

        WidgetStyle.apply_label(
            self, bg_color, text_color, padding, border_radius,
            font_size=font_size, font_weight=font_weight,
        )

        # Публичный канал для обновления текста из любого потока.
        self.status_update.connect(self.setText)


class LabelFactory:
    """Фабрика для создания стилизованных QLabel.

    Роль: единая точка создания меток и заголовков.

    Не наследует BaseWidgetFactory — QSS собирается через
    WidgetStyle.apply_label.

    Публичный API:
        create_label — универсальная метка.
        create_header_label — заголовок окна.
        create_status_label — StatusLabel с сигналом.
    """

    @staticmethod
    def create_label(parent, text="", bg_color=(64, 48, 66),
                     text_color=None, padding="4px 8px", border_radius=5,
                     fixed_size=None, alignment=Qt.AlignCenter,
                     font_family=None, font_size=None, object_name=None,
                     cursor_shape=None, border="none", font_weight=None,
                     extra_style="", word_wrap=False, tooltip=None,
                     min_size=None, max_size=None):
        """Универсальное создание стилизованной метки.

        Вход:
            parent — родитель.
            text — текст.
            bg_color — фон (кортеж или строка).
            text_color — цвет текста. None → контрастный.
            padding — внутренние отступы.
            border_radius — радиус скругления.
            fixed_size — (w, h) или None.
            alignment — Qt.AlignmentFlag.
            font_family, font_size, font_weight — шрифт.
            object_name — objectName.
            cursor_shape — Qt.CursorShape.
            border — CSS-рамка.
            extra_style — дополнительный CSS.
            word_wrap — переносить ли текст.
            tooltip — подсказка.
            min_size, max_size — ограничения размеров.

        Выход: QLabel с QSS.

        REPLACE: QSS собирается через WidgetStyle.apply_label.
        """
        lbl = QLabel(text, parent)

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

        WidgetStyle.apply_label(
            lbl, bg_color, text_color, padding, border_radius, border,
            font_size, font_family, font_weight, extra_style=extra_style,
        )
        return lbl

    @staticmethod
    def create_header_label(parent, text, alignment=Qt.AlignCenter,
                            **kwargs):
        """Создаёт метку-заголовок окна.

        Вход:
            parent — родитель.
            text — текст заголовка.
            alignment — Qt.AlignmentFlag.
            **kwargs — остальные параметры в create_label.

        Выход: QLabel с прозрачным фоном и светло-серым текстом.
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
        """Создаёт StatusLabel с сигналом status_update.

        Вход:
            parent — родитель.
            text — начальный текст.
            **kwargs — параметры StatusLabel.

        Выход: StatusLabel.
        """
        return StatusLabel(parent, text=text, **kwargs)