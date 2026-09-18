from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QApplication
)
from PySide6.QtCore import Qt, QEvent

from ui.factories.factories import (
    ButtonFactory, LabelFactory, BaseWidgetFactory
)


class _BaseMessageDialog(QDialog):
    """Общий предок для диалогов сообщений.

    Назначение:
        Содержит всё, что одинаково у MessageDialog и NotificationDialog:
        расчёт цветов от фона родителя, стилизацию фона и обводки,
        создание лейбла и заголовка, перетаскивание.

    Роль в программе:
        Не используется напрямую. Наследники переопределяют поведение
        окна (модальность, кнопки) и предоставляют свои точки входа.
    """

    def __init__(self, parent=None, text: str = "",
                 title_text: str = None,
                 bg_color: tuple = None,
                 min_size: tuple = None,
                 draggable: bool = True,
                 border_color_override: tuple = None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            text — текст сообщения (единственный элемент содержимого).
            title_text — опциональный заголовок.
            bg_color — опциональный фон родителя (иначе ищется у parent).
            min_size — минимальный размер (w, h).
            draggable — разрешить перетаскивание. По умолчанию True.
            border_color_override — переопределить цвет обводки.

        Роль: вычисляет цвета, создаёт содержимое, подключает dragging.
              Наследник уже должен быть готов вызывать _setup_ui.
        """
        super().__init__(parent)

        self._parent_bg = self._resolve_parent_bg(parent, bg_color)
        self._dialog_bg = self._calc_dialog_bg(self._parent_bg)
        self._border_color = border_color_override or self._calc_dialog_border(self._parent_bg)

        # Флаги окна (модальность, тип) — в наследнике.
        self._setup_window_flags()
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._setup_ui(text, title_text, min_size)

        if draggable:
            self._setup_dragging()

    # ---------- Расчёт цветов (общие) ----------

    @staticmethod
    def _resolve_parent_bg(parent, bg_color) -> tuple:
        """Возвращает bg_color: аргумент → parent.bg_color → parent.window().bg_color → fallback.

        Вход: parent — родительское окно; bg_color — явный цвет или None.
        Выход: кортеж (r, g, b, a).
        Роль: единая точка поиска фона родителя. Fallback — (64, 48, 66, 0.8).
        """
        if bg_color is not None:
            return bg_color
        if parent is not None:
            if hasattr(parent, "bg_color"):
                return parent.bg_color
            top = parent.window()
            if top is not None and hasattr(top, "bg_color"):
                return top.bg_color
        return (64, 48, 66, 0.8)

    @staticmethod
    def _calc_dialog_bg(parent_bg: tuple) -> tuple:
        """Фон диалога: +60/−60 от родителя, alpha 0.95."""
        r, g, b = parent_bg[:3]
        avg = (r + g + b) // 3
        shift = 60 if avg <= 128 else -60

        def clamp(v):
            return max(0, min(255, v))

        return clamp(r + shift), clamp(g + shift), clamp(b + shift), 0.95

    @staticmethod
    def _calc_dialog_border(parent_bg: tuple) -> tuple:
        """Обводка: красноватая, +40+20+20 / −20−40−40, alpha 0.9."""
        r, g, b = parent_bg[:3]
        avg = (r + g + b) // 3

        def clamp(v):
            return max(0, min(255, v))

        if avg <= 128:
            return (clamp(r + 40), clamp(g + 20), clamp(b + 20), 0.9)
        return (clamp(r - 20), clamp(g - 40), clamp(b - 40), 0.9)

    def _calc_button_bg(self) -> tuple:
        """Цвет кнопок — производный от фона диалога."""
        r, g, b = self._dialog_bg[:3]
        avg = (r + g + b) // 3
        shift = 25 if avg <= 128 else -25

        def clamp(v):
            return max(0, min(255, v))

        return (clamp(r + shift), clamp(g + shift), clamp(b + shift), 0.9)

    # ---------- Сборка UI ----------

    def _setup_ui(self, text, title_text, min_size) -> None:
        """Строит содержимое: фон с обводкой, опциональный заголовок, лейбл.

        Вход: text, title_text, min_size.
        Роль: единая точка сборки. В конце вызывает _build_content(layout)
              — хук для наследников (например, добавление кнопок).
        """
        central = QWidget()
        # Даём objectName, чтобы стиль не протекал на дочерние QWidget.
        central.setObjectName("message_dialog_root")
        bg_c = BaseWidgetFactory.color_to_str(self._dialog_bg)
        border_c = BaseWidgetFactory.color_to_str(self._border_color)
        central.setStyleSheet(f"""
                    QWidget#message_dialog_root {{
                        background-color: {bg_c};
                        border: 2px solid {border_c};
                        border-radius: 10px;
                    }}
                """)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        if title_text:
            layout.addWidget(LabelFactory.create_header_label(self, title_text))

        text_color = BaseWidgetFactory.calc_text_color(self._dialog_bg)
        label = LabelFactory.create_label(
            self, text=text, bg_color=(0, 0, 0, 0),
            text_color=text_color, word_wrap=True,
            alignment=Qt.AlignCenter,
        )
        layout.addWidget(label)

        # Хук для наследников — например, добавить кнопки.
        self._build_content(layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(central)

        if min_size:
            self.setMinimumSize(*min_size)
        else:
            self.setMinimumSize(320, 180)

            # Подгоняем окно под содержимое ДО показа.
        self.adjustSize()

    # ---------- Хуки для наследников ----------

    def _setup_window_flags(self) -> None:
        """Устанавливает флаги окна. Переопределяется в наследниках.

        Роль: базовый класс не знает, модальный диалог или Popup —
              это решение наследника.
        """
        raise NotImplementedError("Наследник должен реализовать _setup_window_flags")

    def _build_content(self, layout) -> None:
        """Добавляет содержимое после лейбла. По умолчанию — ничего.

        Вход: layout — QVBoxLayout внутри центрального виджета.
        Роль: точка расширения. MessageDialog добавляет сюда кнопки.
        """
        pass

    def _setup_dragging(self) -> None:
        """Перетаскивание за центральный виджет."""
        def mousePressEvent(event):
            if event.button() == Qt.LeftButton:
                self._drag_pos = (
                    event.globalPosition().toPoint()
                    - self.frameGeometry().topLeft()
                )
                event.accept()

        def showEvent(self, event):
            """Центрирует окно относительно родителя и поднимает поверх.

            Роль: без явного raise_() при вложенном exec() (MessageDialog
                  открывается поверх модального NewTaskDialog) диалог может
                  уйти за родителя или остаться невидимым.
            """
            super().showEvent(event)
            parent = self.parent()
            if parent is not None:
                pr = parent.frameGeometry()
                x = pr.x() + (pr.width() - self.width()) // 2
                y = pr.y() + (pr.height() - self.height()) // 2
                self.move(x, y)
            self.raise_()
            self.activateWindow()

        def mouseMoveEvent(event):
            if hasattr(self, "_drag_pos") and event.buttons() & Qt.LeftButton:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()

        central = self.findChild(QWidget)
        if central:
            central.mousePressEvent = mousePressEvent
            central.mouseMoveEvent = mouseMoveEvent


class MessageDialog(_BaseMessageDialog):
    """Модальный диалог с кнопками. Возвращает результат exec().

    Назначение:
        Замена QMessageBox с кнопками. Пользователь выбирает вариант,
        диалог возвращает QDialog.Result.

    Роль в программе:
        Вопросы, подтверждения, предупреждения с выбором.
        Модальный на уровне приложения, без системной рамки.
    """

    def __init__(self, parent=None, text: str = "",
                 buttons: list = None,
                 title_text: str = None,
                 bg_color: tuple = None,
                 min_size: tuple = None,
                 draggable: bool = True,
                 border_color_override: tuple = None):
        """Конструктор.

        Вход:
            buttons — список кортежей (текст, роль). По умолчанию Да/Нет.
                      Пустой список [] — без кнопок.
            остальные — как в базовом классе.

        Роль: сохраняет список кнопок до вызова super().__init__,
              чтобы _build_content мог их использовать.
        """
        # По умолчанию — Да/Нет.
        if buttons is None:
            buttons = [
                ("Да", QDialogButtonBox.AcceptRole),
                ("Нет", QDialogButtonBox.RejectRole),
            ]
        # Сохраняем ДО super — _build_content вызывается из базового __init__.
        self._buttons = buttons

        super().__init__(
            parent, text, title_text, bg_color, min_size,
            draggable, border_color_override,
        )

    def _setup_window_flags(self) -> None:
        """Модальный диалог на уровне приложения, без рамки.

        Qt.Dialog обязателен: без него Qt не считает окно диалогом,
        и setWindowModality не действует — окно показывается как
        обычное top-level окно и не блокирует родителя.
        """
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)

    def _build_content(self, layout) -> None:
        """Добавляет блок кнопок по центру, если они есть.

        Вход: layout — QVBoxLayout.
        Роль: единственная точка отличия от уведомления.
        """
        if not self._buttons:
            return
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_bg = self._calc_button_bg()
        for btn_text, role in self._buttons:
            btn = ButtonFactory.create_button(
                self, btn_text, bg_color=btn_bg,
                padding="8px 20px", border_radius=5,
            )
            # Замыкаем роль через параметр по умолчанию — иначе lambda
            # поймает последнее значение из цикла.
            btn.clicked.connect(
                lambda checked=False, r=role: self._on_button_clicked(r)
            )
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_button_clicked(self, role) -> None:
        """Обработка нажатия кнопки.

        Вход: role — роль из QDialogButtonBox.
        Роль: RejectRole → reject(), остальные → accept().
        """
        if role == QDialogButtonBox.RejectRole:
            self.reject()
        else:
            self.accept()

    # ---------- Статические фабрики ----------

    @staticmethod
    def question(parent, text, bg_color=None, buttons=None,
                 title_text=None, min_size=None) -> int:
        """Диалог вопроса. Возвращает результат exec()."""
        dialog = MessageDialog(
            parent, text, buttons, title_text, bg_color, min_size
        )
        return dialog.exec()

    @staticmethod
    def info(parent, text, bg_color=None, buttons=None,
             title_text=None, min_size=None) -> int:
        """Информационный диалог. Синоним question."""
        return MessageDialog.question(
            parent, text, bg_color, buttons, title_text, min_size
        )

    @staticmethod
    def warning(parent, text, bg_color=None, buttons=None,
                title_text=None, min_size=None) -> int:
        """Предупреждение. Синоним question."""
        return MessageDialog.question(
            parent, text, bg_color, buttons, title_text, min_size
        )


class NotificationDialog(_BaseMessageDialog):
    """Не модальное уведомление. Без кнопок, закрывается кликом вне.

    Назначение:
        Показать пользователю краткое сообщение и не блокировать его.
        Уведомление закрывается при клике вне окна, по Esc или при
        клике по другой части интерфейса.

    Реализация закрытия по клику вне:
        Qt.Popup не используется — в связке с Qt.Dialog он ведёт себя
        непредсказуемо, а без родителя-QMainWindow часто вообще не
        срабатывает. Вместо этого ставим eventFilter на QApplication
        и ловим клики вне границ окна вручную.
    """

    def _setup_window_flags(self) -> None:
        """Не модальное окно поверх остальных, без системной рамки."""
        # Qt.Dialog — базовый тип (нужен для WA_TranslucentBackground).
        # WindowStaysOnTopHint — поверх родителя.
        # FramelessWindowHint — без системного заголовка.
        # Qt.Popup НЕ используется — конфликтует с Qt.Dialog.
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        )

    def __init__(self, *args, **kwargs):
        """Конструктор. После базовой инициализации ставит eventFilter
        на QApplication, чтобы ловить клики вне окна.
        """
        super().__init__(*args, **kwargs)
        # Ставим фильтр на приложение: клик по любому окну/виджету
        # пройдёт через нас, и мы проверим координаты.
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        """Ловит MouseButtonPress вне границ окна и закрывает его.

        Вход: obj — объект, на котором произошло событие; event — событие.
        Выход: True — событие поглощено; False — пропускаем дальше.

        Роль: имитирует поведение Qt.Popup без его побочных эффектов.
        """
        if event.type() == QEvent.MouseButtonPress and self.isVisible():
            # Переводим глобальные координаты клика в локальные окна.
            local = self.mapFromGlobal(event.globalPosition().toPoint())
            if not self.rect().contains(local):
                self.close()
                # Возвращаем False — пусть клик дойдёт до того, по кому
                # кликнули (например, по кнопке родителя). Если хочется
                # «съесть» клик — верни True.
                return False
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """Снимает eventFilter при закрытии, чтобы не копить мёртвые фильтры."""
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    @staticmethod
    def notify(parent, text, bg_color=None,
               title_text=None, min_size=None) -> None:
        """Показывает уведомление. Не блокирует вызывающий код.

        Вход:
            parent — родительское окно.
            text — текст уведомления.
            bg_color, title_text, min_size — как у MessageDialog.

        Выход: нет.
        Роль: создаёт NotificationDialog и вызывает QWidget.show()
              (не exec — уведомление не блокирует).
              WA_DeleteOnClose — Qt удалит окно при закрытии.
        """
        dialog = NotificationDialog(
            parent=parent,
            text=text,
            title_text=title_text,
            bg_color=bg_color,
            min_size=min_size,
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()