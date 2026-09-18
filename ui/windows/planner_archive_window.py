"""
Окно архива задач планировщика.

UI-каркас без данных. Наследник _BasePlannerListWindow.
"""

from ui.windows.planner_base_window import _BasePlannerListWindow


from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget

from ui.factories.factories import ButtonFactory
from ui.windows.message_dialog import MessageDialog
from ui.windows.planner_base_window import _BasePlannerListWindow
from models.planner_task import PlannerTask


class PlannerArchiveWindow(_BasePlannerListWindow):
    """Окно архива задач планировщика.

    Назначение:
        Показывает архив завершённых/отменённых задач. Позволяет
        восстанавливать и удалять навсегда.

    Роль в программе:
        Открывается из PlannerWindow по кнопке «Архив» модально
        (Qt.WindowModal). Визуально идентично PlannerWindow, кроме
        обесцвеченного фона и отсутствия нижних кнопок.
    """

    # 70% обесцвечивания от PlannerWindow.bg_color = (70, 60, 50):
    # avg = 60; r = 70*0.3 + 60*0.7 = 63, g = 60, b = 57.
    ARCHIVE_BG_COLOR = (63, 60, 57, 0.95)

    # Колонки архива: действия (↺, ✕), название, приоритет, статус, дата.
    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "priority", "status", "date"],
    }

    # Расширяем базовые билдеры колонкой действий.
    COLUMN_BUILDERS = {
        **_BasePlannerListWindow.COLUMN_BUILDERS,
        "actions": "_build_actions",
    }

    def __init__(self, parent=None, archive_service=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerWindow).
            archive_service — PlannerArchiveService. Обязателен.

        Роль: сохраняет сервис, строит каркас через базовый класс,
              загружает задачи.
        """
        if archive_service is None:
            raise ValueError("archive_service обязателен")
        self.service = archive_service
        super().__init__(parent, "Архив", bg_color=self.ARCHIVE_BG_COLOR)
        # Первая загрузка задач архива.
        self._reload_tasks()

    # ---------- Источник данных ----------

    def _get_tasks(self):
        return self.service.get_archive_tasks()

    # ---------- Билдер actions ----------

    def _build_actions(self, task: PlannerTask) -> QWidget:
        """Кнопки: ↺ (восстановить), ✕ (удалить навсегда)."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Кнопка восстановления.
        restore_btn = ButtonFactory.create_button(
            container, "↺", bg_color=(100, 130, 150),
            fixed_size=(26, 26), padding="0px", font_size=14,
        )
        restore_btn.clicked.connect(
            lambda checked=False, t=task: self._on_restore_task(t)
        )
        layout.addWidget(restore_btn)

        # Кнопка удаления навсегда.
        delete_btn = ButtonFactory.create_delete_button(
            container,
            lambda checked=False, t=task: self._on_delete_forever(t),
        )
        layout.addWidget(delete_btn)
        return container

    # ---------- Обработчики ----------

    def _on_restore_task(self, task: PlannerTask) -> None:
        """Восстанавливает задачу из архива.

        CANCELLED — возвращается в активные с тем же task_id.
        COMPLETED — создаётся новая задача в активных, оригинал
                    остаётся в архиве.
        """
        self.service.restore_task(task.task_id)
        self._reload_tasks()

    def _on_delete_forever(self, task: PlannerTask) -> None:
        """Удаляет задачу из архива навсегда, с подтверждением."""
        reply = MessageDialog.question(
            self,
            f"Удалить задачу «{task.title}» навсегда?",
            title_text="Подтверждение удаления",
            bg_color=self.bg_color,
        )
        if reply == QDialog.Accepted:
            self.service.delete_forever(task.task_id)
            self._reload_tasks()

    def closeEvent(self, event):
        """При закрытии архива — обновляем список задач в PlannerWindow.

        Родитель (PlannerWindow) не знает, что мы меняли активные задачи
        через restore_task. После закрытия архива просим родителя
        перерисовать список.

        Вход: event — событие закрытия.
        Выход: нет.
        Роль: связь архив → планировщик без глобальных сигналов.
              Проверка hasattr защищает от ситуации, когда родитель
              не PlannerWindow (например, в будущем архив откроют
              из другого окна).
        """
        parent = self.parent()
        if parent is not None and hasattr(parent, "_reload_tasks"):
            parent._reload_tasks()
        super().closeEvent(event)