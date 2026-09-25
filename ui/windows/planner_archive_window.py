"""
Окно архива задач планировщика.

UI-каркас без данных. Наследник _BasePlannerListWindow.
"""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget
from PySide6.QtCore import Qt
from ui.factories.button_factory import ButtonFactory
from ui.windows.message_dialog import MessageDialog
from ui.windows.planner_base_window import _BasePlannerListWindow
from models.planner_task import PlannerTask, TaskStatus, TaskPriority
from ui.windows.planner_task_dialogs import (
    DeadlineEditDialog, PlannerRecurrenceEditDialog,
)

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
        "default": ["actions", "title", "priority", "status", "date", "specifications"],
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
        # Проверка обязательного аргумента — до любых использований.
        if archive_service is None:
            raise ValueError("archive_service обязателен")
        self.service = archive_service
        super().__init__(parent, "Архив", bg_color=self.ARCHIVE_BG_COLOR)
        #очистка от старых экземпляров
        self.service.delete_old_instances(days=30)
        # Первая загрузка задач архива.
        self._reload_tasks()

    # ---------- Источник данных ----------

    def _get_tasks(self):
        return self.service.get_archive_tasks()

    # ---------- Билдер actions ----------

    def _build_actions(self, task: PlannerTask) -> QWidget:
        """Кнопки: ↺ (восстановить), ✕ (удалить навсегда).

        У экземпляров регулярных задач кнопки ↺ нет — восстановить
        экземпляр нельзя.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if not task.is_recurring_instance() and not task.is_event():
            restore_btn = ButtonFactory.create_restore_button(
                container,
                lambda checked=False, t=task: self._on_restore_task(t),
            )
            layout.addWidget(restore_btn)

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
                    остаётся в архиве. Перед восстановлением проверяет,
                    была ли задача уже восстановлена (в активных есть
                    задача со spawner_task = task.task_id).
        Для дедлайн-задач показывает DeadlineEditDialog.
        """
        # 1. Проверка повторного восстановления COMPLETED.
        if task.status == TaskStatus.COMPLETED:
            spawned = self.service.get_spawned_tasks(task.task_id)
            if spawned:
                reply = MessageDialog.question(
                    self,
                    f"Задача «{task.title}» уже была восстановлена. "
                    f"Создать ещё одну задачу с теми же параметрами?",
                    title_text="Уже восстановлена",
                    bg_color=self.bg_color,
                )
                if reply != QDialog.Accepted:
                    return

        # 2. Диалоги редактирования при восстановлении.
        deadline_datetime = None
        recurrence_data = None
        if task.priority == TaskPriority.DEADLINE:
            dialog = DeadlineEditDialog(self, task)
            if dialog.exec() != QDialog.Accepted:
                return
            deadline_datetime = dialog.get_result()["deadline_datetime"]
        elif task.is_generator():
            dialog = PlannerRecurrenceEditDialog(self, task)
            if dialog.exec() != QDialog.Accepted:
                return
            recurrence_data = dialog.get_result()["recurrence_data"]

        self.service.restore_task(
            task.task_id,
            deadline_datetime=deadline_datetime,
            recurrence_data=recurrence_data,
        )
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