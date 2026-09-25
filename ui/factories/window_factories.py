"""
Фабрики настройки окон.

Содержит два класса:
    WindowFactory          — базовая настройка дочерних окон
                             (рамка, прозрачность, кнопка закрытия,
                             заголовок, каркас main_layout).
    ExtendedWindowFactory  — расширенная настройка (кнопки OK/Cancel,
                             action_button, перетаскивание,
                             закрытие по клику вне окна).

ExtendedWindowFactory наследует WindowFactory — семантическая
группировка фабрик окон.

QSS центрального виджета и кнопки закрытия собирается через
ui.styles.WidgetStyle и ui.styles.WindowStyle.
"""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QApplication,
    QMainWindow, QDialog, QPushButton,
)

from .button_factory import ButtonFactory
from .element_factory import LabelFactory
from ui.styles import WidgetStyle


class WindowFactory:
    """Фабрика для настройки и управления дочерними окнами.

    Роль: единая точка настройки дочернего окна — рамка,
          прозрачный фон, кнопка закрытия «✕», заголовок,
          геометрия относительно родителя.

    Публичный API:
        setup_child_window — настраивает каркас окна.
        show_child_window — показывает окно и, при наличии
                            active_child у родителя, помечает его.
    """

    @staticmethod
    def setup_child_window(child, title, bg_color=(64, 48, 66, 0.8),
                           close_callback=None, frameless=True,
                           stay_on_top=True, translucent_background=True,
                           close_button=True, close_button_color="#fd5e53",
                           return_layout=True):
        """Настраивает дочернее окно.

        Вход:
            child — QMainWindow или QDialog.
            title — заголовок.
            bg_color — цвет фона центрального виджета (кортеж).
            close_callback — функция на клик по «✕».
            frameless — без системной рамки.
            stay_on_top — поверх родителя.
            translucent_background — прозрачный фон.
            close_button — добавлять ли кнопку закрытия.
            close_button_color — цвет кнопки закрытия.
            return_layout — вернуть ли main_layout.

        Выход: QVBoxLayout или None.

        Роль: строит каркас окна: флаги, центральный виджет с
              фоном и border-radius, top_layout с заголовком и
              кнопкой закрытия.

        REPLACE: QSS центрального виджета и кнопки закрытия
        собираются через WidgetStyle.apply_window_central и
        WidgetStyle.apply_close_button.
        """
        flags = 0
        if frameless:
            flags |= Qt.FramelessWindowHint
        if stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        child.setWindowFlags(flags)

        if translucent_background:
            child.setAttribute(Qt.WA_TranslucentBackground)

        child.setWindowTitle(title)

        # Центральный виджет — фон и border-radius через WidgetStyle.
        central = QWidget()
        WidgetStyle.apply_window_central(central, bg_color)
        child.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)

        top_layout.addStretch()
        top_layout.addWidget(LabelFactory.create_header_label(child, title))
        top_layout.addStretch()

        if close_button:
            close_btn = QPushButton("✕")
            close_btn.setFixedSize(25, 25)
            WidgetStyle.apply_close_button(close_btn, close_button_color)
            if close_callback:
                close_btn.clicked.connect(close_callback)
            else:
                close_btn.clicked.connect(child.close)
            top_layout.addWidget(close_btn)

        main_layout.addLayout(top_layout)

        if return_layout:
            return main_layout
        return None

    @staticmethod
    def show_child_window(parent, child, modal=True, cover_parent=False):
        """Показывает дочернее окно с геометрией относительно родителя.

        Вход:
            parent — родительское окно.
            child — дочернее окно.
            modal — оставлен для совместимости, не используется.
            cover_parent — если True, окно полностью перекрывает
                           родителя.

        Выход: нет.

        Роль: единая точка показа. Устанавливает parent.active_child
              = child (для LoggerV2 UI-каналов), выставляет
              геометрию и активирует окно.
        """
        parent_rect = parent.frameGeometry()

        if cover_parent:
            child.setGeometry(parent_rect)
        else:
            child.setGeometry(10, 10,
                              parent_rect.width() - 20,
                              parent_rect.height() - 50)

        if hasattr(parent, "active_child"):
            parent.active_child = child

        child.show()
        child.activateWindow()


class ExtendedWindowFactory(WindowFactory):
    """Расширенная фабрика настройки окон.

    Наследует WindowFactory. Расширяет каркас: кнопки OK/Cancel,
    action_button, кнопка добавления, перетаскивание, закрытие
    по клику вне окна, callback при закрытии.

    Роль в программе:
        Используется в диалогах редактирования и BaseEditDialog.
    """

    @staticmethod
    def setup_window(window, parent, title, bg_color=(64, 48, 66, 0.8),
                     close_button=True, add_button=False,
                     add_button_text="+", add_callback=None,
                     action_button=None, action_callback=None,
                     action_button_alignment="stretch",
                     ok_cancel=False, ok_callback=None,
                     cancel_callback=None,
                     draggable=False, close_on_click_outside=False,
                     modal=False, frameless=True, transparent=True,
                     stay_on_top=True, center=True, on_close=None,
                     return_layout=None, return_content_layout=True,
                     default_width=400, default_height=350):
        """Настраивает каркас окна с расширенными возможностями.

        Вход — см. поля класса. Все параметры опциональны.

        Выход: content_layout, main_layout или None в зависимости
               от флагов return_*.

        Роль: создаёт центральный виджет, top_layout с заголовком,
              close_button (опц.), add_button (опц.), content_widget
              для пользовательского содержимого, action_button и
              ok/cancel (опц.), подключает draggable / click_outside /
              on_close.

        REPLACE: QSS центрального виджета собирается через
        WidgetStyle.apply_window_central.
        """
        # 1. Флаги окна.
        flags = 0
        if frameless:
            flags |= Qt.FramelessWindowHint
        if stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        window.setWindowFlags(flags)

        if transparent:
            window.setAttribute(Qt.WA_TranslucentBackground)

        window.setWindowTitle(title)

        # 2. Центральный виджет.
        central = QWidget()
        WidgetStyle.apply_window_central(central, bg_color)
        if isinstance(window, QMainWindow):
            window.setCentralWidget(central)
        else:
            layout = QVBoxLayout(window)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(central)
            window.setLayout(layout)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 4. Верхняя панель.
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)

        if add_button:
            add_btn = ButtonFactory.create_button(
                window, add_button_text, (100, 80, 120, 0.7),
                padding="4px 8px", fixed_size=(30, 30)
            )
            if add_callback:
                add_btn.clicked.connect(add_callback)
            top_layout.addWidget(add_btn)

        top_layout.addStretch()

        if close_button:
            close_btn = ButtonFactory.create_button(
                window, "✕", (200, 60, 60, 0.8),
                padding="4px 8px", fixed_size=(30, 30)
            )
            close_btn.clicked.connect(window.close)
            top_layout.addWidget(close_btn)

        main_layout.addLayout(top_layout)

        # 5. Контейнер для пользовательского контента.
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        main_layout.addWidget(content_widget)

        # 6. Кнопка действия (action_button).
        if action_button:
            action_btn = ButtonFactory.create_button(
                window, action_button, (70, 120, 90, 0.8),
                padding="6px 12px"
            )
            if action_callback:
                action_btn.clicked.connect(action_callback)
            else:
                action_btn.clicked.connect(window.close)

            if action_button_alignment == "stretch":
                main_layout.addWidget(action_btn)
            else:
                btn_layout = QHBoxLayout()
                if action_button_alignment == "center":
                    btn_layout.addStretch()
                    btn_layout.addWidget(action_btn)
                    btn_layout.addStretch()
                elif action_button_alignment == "left":
                    btn_layout.addWidget(action_btn)
                    btn_layout.addStretch()
                elif action_button_alignment == "right":
                    btn_layout.addStretch()
                    btn_layout.addWidget(action_btn)
                else:
                    btn_layout.addStretch()
                    btn_layout.addWidget(action_btn)
                    btn_layout.addStretch()
                main_layout.addLayout(btn_layout)

        # 7. Кнопки OK/Отмена.
        if ok_cancel:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            ok_btn = ButtonFactory.create_button(
                window, "ОК", (70, 120, 90, 0.8), padding="6px 12px"
            )
            if ok_callback:
                ok_btn.clicked.connect(ok_callback)
            else:
                ok_btn.clicked.connect(
                    window.accept if isinstance(window, QDialog)
                    else window.close
                )
            btn_layout.addWidget(ok_btn)

            cancel_btn = ButtonFactory.create_button(
                window, "Отмена", (150, 80, 80, 0.8), padding="6px 12px"
            )
            if cancel_callback:
                cancel_btn.clicked.connect(cancel_callback)
            else:
                cancel_btn.clicked.connect(
                    window.reject if isinstance(window, QDialog)
                    else window.close
                )
            btn_layout.addWidget(cancel_btn)
            main_layout.addLayout(btn_layout)

        # 8. Перетаскивание.
        if draggable:
            ExtendedWindowFactory._setup_dragging(window, central)

        # 9. Закрытие при клике вне окна.
        if close_on_click_outside:
            ExtendedWindowFactory._setup_click_outside_close(window)

        # 11. Размер и центрирование.
        window.resize(default_width, default_height)
        window.setMinimumSize(default_width, default_height)

        if center and parent:
            ExtendedWindowFactory._center_window(window, parent)

        # 12. Callback при закрытии.
        if on_close:
            original_close = window.closeEvent

            def new_close(event):
                if not getattr(window, '_cancel_on_close', False):
                    on_close()
                if original_close:
                    original_close(event)
                else:
                    event.accept()

            window.closeEvent = new_close

        if return_content_layout:
            return content_layout
        elif return_layout:
            return main_layout
        return None

    # ---------- Вспомогательные методы ----------

    @staticmethod
    def _center_window(window, parent):
        """Центрирует окно относительно родителя."""
        parent_geom = parent.frameGeometry()
        w = window.width()
        h = window.height()
        x = parent_geom.x() + (parent_geom.width() - w) // 2
        y = parent_geom.y() + (parent_geom.height() - h) // 2
        window.setGeometry(x, y, w, h)

    @staticmethod
    def _setup_dragging(window, widget):
        """Подключает перетаскивание окна за указанный виджет."""
        def mousePressEvent(event):
            if event.button() == Qt.LeftButton:
                window._drag_pos = (
                    event.globalPosition().toPoint()
                    - window.frameGeometry().topLeft()
                )
                event.accept()

        def mouseMoveEvent(event):
            if (hasattr(window, '_drag_pos')
                    and event.buttons() & Qt.LeftButton):
                new_pos = event.globalPosition().toPoint() - window._drag_pos
                window.move(new_pos)
                event.accept()

        widget.mousePressEvent = mousePressEvent
        widget.mouseMoveEvent = mouseMoveEvent

    @staticmethod
    def _setup_click_outside_close(window):
        """Закрывает окно при клике вне его границ.

        Роль: подменяет window.eventFilter, ставит фильтр на
              QApplication. При клике вне rect() ставит флаг
              _cancel_on_close=True и закрывает окно. Событие
              пропускается дальше — чтобы клик дошёл до цели
              (например, до крестика родителя).
        """
        def event_filter(obj, event):
            if event.type() != QEvent.MouseButtonPress:
                return False
            if not window.isVisible():
                return False

            local_pos = window.mapFromGlobal(event.globalPosition().toPoint())
            if window.rect().contains(local_pos):
                return False

            window._cancel_on_close = True
            window.close()
            return False

        window.eventFilter = event_filter
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(window)

        original_close = window.closeEvent

        def new_close(event):
            app_ref = QApplication.instance()
            if app_ref is not None:
                app_ref.removeEventFilter(window)
            if original_close:
                original_close(event)
            else:
                event.accept()

        window.closeEvent = new_close