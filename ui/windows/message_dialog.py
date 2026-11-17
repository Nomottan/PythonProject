from PySide6.QtWidgets import (
    QHBoxLayout, QDialogButtonBox, QApplication,
)
from PySide6.QtCore import Qt, QEvent

from ui.base.base_message_dialog import BaseMessageDialog
from ui.factories.factories import ButtonFactory

class MessageDialog(BaseMessageDialog):
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

        # WA_DeleteOnClose: после ответа объект удаляется Qt'ом,
        # чтобы не копить мёртвые диалоги в WindowManager.
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _is_modal(self) -> bool:
        """MessageDialog всегда WindowModal (блокирует родителя)."""
        return True

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


class NotificationDialog(BaseMessageDialog):
    """Не модальное уведомление без рамки."""

    def _is_modal(self) -> bool:
        return False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # База уже применила флаги и зарегистрировала в WindowManager

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.MouseButtonPress and self.isVisible():
            local = self.mapFromGlobal(event.globalPosition().toPoint())
            if not self.rect().contains(local):
                self.close()
                return False
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    @staticmethod
    def notify(parent, text, bg_color=None,
               title_text=None, min_size=None) -> None:
        dialog = NotificationDialog(
            parent=parent,
            text=text,
            title_text=title_text,
            bg_color=bg_color,
            min_size=min_size,
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()