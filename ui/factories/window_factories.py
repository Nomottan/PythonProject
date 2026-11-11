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
    QMainWindow, QDialog,
)

from .button_factory import ButtonFactory, ActionButtonType
from .element_factory import LabelFactory
from ui.styles import WidgetStyle, WindowStyle


class WindowFactory:
    """Фабрика для настройки и управления дочерними окнами.

    Роль: единая точка настройки дочернего окна — рамка,
          прозрачный фон, кнопка закрытия «✕», заголовок,
          каркас main_layout.

    Публичный API:
        setup_child_window — настраивает каркас окна.

    Флаги, модальность и геометрия дочерних окон — ответственность
    WindowManager при register_window.
    """

    @staticmethod
    def setup_child_window(child, title, bg_color=(64, 48, 66, 0.8),
                           close_callback=None, close_button=True,
                           close_button_color=None,
                           return_layout=True,
                           parent=None):
        """Настраивает дочернее окно (каркас).

        Флаги, модальность и геометрия теперь управляются WindowManager.
        Здесь только создается центральный виджет и кнопка закрытия.
        """
        child.setWindowTitle(title)

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
            if close_button:
                close_btn = ButtonFactory.create_action_button(
                    child,
                    ActionButtonType.DELETE,
                    close_callback if close_callback else child.close,
                    bg_color=close_button_color
                )
                top_layout.addWidget(close_btn)

        main_layout.addLayout(top_layout)

        if return_layout:
            return main_layout
        return None

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
                     on_close=None,
                     return_layout=None, return_content_layout=True,
                     default_width=400, default_height=350):
        """Настраивает каркас окна с расширенными возможностями (UI-часть).

        Вход:
            window — QDialog или QMainWindow, которое настраиваем.
            parent — Qt-родитель (для совместимости).
            title — заголовок окна.
            bg_color — цвет фона центрального виджета (кортеж).
            close_button — добавлять ли кнопку закрытия «✕».
            add_button — добавлять ли кнопку «+» (опционально).
            add_button_text — текст кнопки добавления.
            add_callback — callback для кнопки добавления.
            action_button — текст большой кнопки действия (опционально).
            action_callback — callback для большой кнопки.
            action_button_alignment — выравнивание кнопки действия
                                      ("stretch", "center", "left", "right").
            ok_cancel — добавлять ли кнопки ОК/Отмена.
            ok_callback — callback для ОК (по умолчанию accept/close).
            cancel_callback — callback для Отмены (по умолчанию reject/close).
            draggable — разрешить перетаскивание за центральный виджет.
            close_on_click_outside — закрывать при клике вне окна.
            on_close — callback, вызываемый перед физическим закрытием.
            return_layout — если True и return_content_layout=False,
                            вернёт главный layout.
            return_content_layout — если True, вернёт layout для контента.
            default_width, default_height — стартовые размеры окна.

        Выход:
            content_layout — QVBoxLayout для пользовательского контента (по умолчанию).
            main_layout — QVBoxLayout всего окна (если return_layout=True).
            None — если оба флага возврата False.

        Роль:
            Формирует визуальную структуру: центральный виджет, верхнюю панель
            с заголовком и крестиком, контейнер для контента, кнопки действий
            и ОК/Отмена. Подключает dragging и click-outside.
            ВАЖНО: Не управляет флагами окна (frameless, stay_on_top),
            не задает модальность (setWindowModality) и не центрирует окно.
            Этими задачами теперь занимается исключительно WindowManager
            при регистрации окна.
        """
        window.setWindowTitle(title)

        # 1. Центральный виджет.
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

        # 2. Верхняя панель.
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
            close_btn = ButtonFactory.create_action_button(
                window,
                ActionButtonType.DELETE,
                window.close
            )
            top_layout.addWidget(close_btn)

        main_layout.addLayout(top_layout)

        # 3. Контейнер для пользовательского контента.
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        main_layout.addWidget(content_widget)

        # 4. Кнопка действия (action_button).
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

        # 5. Кнопки OK/Отмена.
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

        # 6. Перетаскивание.
        if draggable:
            ExtendedWindowFactory._setup_dragging(window, central)

        # 7. Закрытие при клике вне окна.
        if close_on_click_outside:
            ExtendedWindowFactory._setup_click_outside_close(window)

        # 8. Размер. Геометрию выставляет WindowManager при
        # register_window; здесь только Qt-дефолтный минимум —
        # маленький, чтобы окно не клампилось к default_width
        # и не вылезало за MainWindow.
        window.resize(default_width, default_height)
        window.setMinimumSize(200, 150)

        # 9. Callback при закрытии.
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

            # Открыт popup (раскрытый QComboBox, QMenu и т. п.) —
            # клик по нему формально вне rect() диалога, но это
            # не «клик вне окна»: не закрываем.
            if QApplication.activePopupWidget() is not None:
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