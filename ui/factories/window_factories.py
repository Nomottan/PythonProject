# window_factories.py
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QApplication, QMainWindow, QDialog
from ui.factories.factories import ButtonFactory, LabelFactory

class ExtendedWindowFactory:
    """
    Универсальная фабрика для настройки окон (QMainWindow или QDialog).
    Поддерживает:
    - кнопку закрытия (close_button)
    - кнопку добавления (add_button)
    - кнопку действия (action_button) с выравниванием (stretch/center/left/right)
    - пару кнопок ОК/Отмена (ok_cancel)
    - перетаскивание (draggable)
    - закрытие при клике вне окна (close_on_click_outside)
    - модальность (modal)
    - центрирование (center)
    - callback при закрытии (on_close)
    - возврат макета для контента (return_content_layout)
    - размер по умолчанию (default_width, default_height)
    """

    @staticmethod
    def setup_window(window, parent, title, bg_color=(64, 48, 66, 0.8),
                     close_button=True, add_button=False, add_button_text="+",
                     add_callback=None, action_button=None, action_callback=None,
                     action_button_alignment="stretch",
                     ok_cancel=False, ok_callback=None, cancel_callback=None,
                     draggable=False, close_on_click_outside=False, modal=False,
                     frameless=True, transparent=True, stay_on_top=True,
                     center=True, on_close=None,
                     return_layout=None, return_content_layout=True,
                     default_width=400, default_height=350):

        # 1. Флаги окна
        flags = 0
        if frameless:
            flags |= Qt.FramelessWindowHint
        if stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        window.setWindowFlags(flags)

        if transparent:
            window.setAttribute(Qt.WA_TranslucentBackground)

        window.setWindowTitle(title)

        # 2. Центральный виджет
        central = QWidget()
        r, g, b, a = bg_color if len(bg_color) == 4 else (*bg_color, 0.8)
        central.setStyleSheet(f"""
            QWidget {{
                background-color: rgba({r}, {g}, {b}, {a});
                border-radius: 15px;
            }}
        """)
        if isinstance(window, QMainWindow):
            window.setCentralWidget(central)
        else:  # QDialog
            layout = QVBoxLayout(window)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(central)
            window.setLayout(layout)

        # 3. Основной макет
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 4. Верхняя панель (кнопки закрытия и добавления)
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

        # 5. Контейнер для пользовательского контента
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        main_layout.addWidget(content_widget)

        # 6. Кнопка действия (action_button) с выравниванием
        if action_button:
            action_btn = ButtonFactory.create_button(
                window, action_button, (70, 120, 90, 0.8), padding="6px 12px"
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
                    # fallback: центр
                    btn_layout.addStretch()
                    btn_layout.addWidget(action_btn)
                    btn_layout.addStretch()
                main_layout.addLayout(btn_layout)

        # 7. Кнопки ОК/Отмена (всегда прижаты к правому краю)
        if ok_cancel:
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            ok_btn = ButtonFactory.create_button(
                window, "ОК", (70, 120, 90, 0.8), padding="6px 12px"
            )
            if ok_callback:
                ok_btn.clicked.connect(ok_callback)
            else:
                ok_btn.clicked.connect(window.accept if isinstance(window, QDialog) else window.close)
            btn_layout.addWidget(ok_btn)

            cancel_btn = ButtonFactory.create_button(
                window, "Отмена", (150, 80, 80, 0.8), padding="6px 12px"
            )
            if cancel_callback:
                cancel_btn.clicked.connect(cancel_callback)
            else:
                cancel_btn.clicked.connect(window.reject if isinstance(window, QDialog) else window.close)
            btn_layout.addWidget(cancel_btn)
            main_layout.addLayout(btn_layout)

        # 8. Перетаскивание
        if draggable:
            ExtendedWindowFactory._setup_dragging(window, central)

        # 9. Закрытие при клике вне окна
        if close_on_click_outside:
            ExtendedWindowFactory._setup_click_outside_close(window)

        # 10. Модальность
        if modal:
            if isinstance(window, QDialog):
                window.setModal(True)
            else:
                window.setWindowModality(Qt.ApplicationModal)

        # 11. Размер и центрирование
        window.resize(default_width, default_height)
        window.setMinimumSize(default_width, default_height)

        if center and parent:
            ExtendedWindowFactory._center_window(window, parent)

        # 12. Callback при закрытии
        if on_close:
            original_close = window.closeEvent
            def new_close(event):
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
        parent_geom = parent.frameGeometry()
        w = window.width()
        h = window.height()
        x = parent_geom.x() + (parent_geom.width() - w) // 2
        y = parent_geom.y() + (parent_geom.height() - h) // 2
        window.setGeometry(x, y, w, h)

    @staticmethod
    def _setup_dragging(window, widget):
        def mousePressEvent(event):
            if event.button() == Qt.LeftButton:
                window._drag_pos = event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                event.accept()
        def mouseMoveEvent(event):
            if hasattr(window, '_drag_pos') and event.buttons() & Qt.LeftButton:
                new_pos = event.globalPosition().toPoint() - window._drag_pos
                window.move(new_pos)
                event.accept()
        widget.mousePressEvent = mousePressEvent
        widget.mouseMoveEvent = mouseMoveEvent

    @staticmethod
    def _setup_click_outside_close(window):
        def eventFilter(obj, event):
            if event.type() == QEvent.MouseButtonPress:
                if not window.rect().contains(window.mapFromGlobal(event.globalPosition().toPoint())):
                    window.close()
                    return True
            return False
        window.installEventFilter(window)
        QApplication.instance().installEventFilter(window)
        window._click_filter = eventFilter
        original_close = window.closeEvent
        def new_close(event):
            QApplication.instance().removeEventFilter(window)
            if original_close:
                original_close(event)
            else:
                event.accept()
        window.closeEvent = new_close

