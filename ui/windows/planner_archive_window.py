"""
Окно архива задач планировщика.

UI-каркас без данных. Наследник _BasePlannerListWindow.
"""

from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget
from PySide6.QtCore import Qt

from ui.factories.button_factory import ButtonFactory
from ui.windows.message_dialog import MessageDialog
from ui.base.planner_base_window import _BasePlannerListWindow
from models.planner_task import PlannerTask, TaskStatus, TaskPriority
from ui.windows.planner_task_dialogs import (
    DeadlineEditDialog, PlannerRecurrenceEditDialog,
)
from utils.filter_utils import FieldDef
from ui.styles import ColorCalculator, WindowStyle


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

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = "PlannerArchiveWindow.planner_archive_window"
    LOGGER_DOMAIN = "planner"

    # В архиве чек-лист и темы можно только просматривать
    EDITABLE = False

    # Колонки архива: действия (↺, ✕), название, чек-лист, приоритет, тема, статус, дата.
    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "checklist", "priority", "theme", "status", "date", "specifications"],
    }
    # Расширяем базовые билдеры колонкой действий.
    COLUMN_BUILDERS = {
        **_BasePlannerListWindow.COLUMN_BUILDERS,
        "actions": "_build_actions",
    }

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, archive_service=None,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerWindow).
            archive_service — PlannerArchiveService. Обязателен.
            log_manager_v2 — LogManagerV2 или None.

        Роль: сохраняет сервис, строит каркас через базовый класс,
              загружает задачи.
        """
        # Проверка обязательного аргумента — до любых использований.
        if archive_service is None:
            raise ValueError("archive_service обязателен")
        self.service = archive_service

        # Цвет от родителя (PlannerWindow), делаем его чуть темнее/серее
        parent_bg = WindowStyle.resolve_parent_bg(parent, (63, 60, 57, 0.95))
        bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r - 30,
            g_fn=lambda g: g - 15,
            b_fn=lambda b: b - 125,
            alpha=0.95,
        )

        # ---------- СОСТОЯНИЕ И БАЗОВЫЙ КАРКАС ----------
        super().__init__(
            parent, "Архив", bg_color=bg_color,
            log_manager_v2=log_manager_v2,
            main_config=getattr(parent, "main_config", None),
        )

        # ---------- ДАННЫЕ ----------
        # Очистка от старых экземпляров
        self.service.delete_old_instances(days=30)
        # Первая загрузка задач архива.
        self._reload_tasks()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ИСТОЧНИКИ И БИЛДЕРЫ
    # ============================================================

    def _get_tasks(self):
        """Возвращает задачи архива."""
        return self.service.get_archive_tasks()

    def _get_filter_field_defs(self) -> list:
        """Возвращает список FieldDef для панели фильтров архива.

        Четыре категории — «Тип задачи», «Дата создания»,
        «Тип завершения», «Дата завершения».
        """
        return [
            FieldDef(
                name="priority",
                label="Тип задачи",
                extractor=lambda t: t.priority.display_name,
            ),
            FieldDef(
                name="created_date",
                label="Дата создания",
                extractor=lambda t: t.created_date or "Не указана",
            ),
            FieldDef(
                name="status",
                label="Тип завершения",
                extractor=lambda t: t.status.display_name,
            ),
            FieldDef(
                name="completed_date",
                label="Дата завершения",
                extractor=lambda t: t.completed_date or "Не указана",
            ),
        ]

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

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================

    def _on_restore_task(self, task: PlannerTask) -> None:
        """Восстанавливает задачу из архива.

        CANCELLED — возвращается в активные с тем же task_id.
        COMPLETED — создаётся новая задача в активных, оригинал
                    остаётся в архиве. Перед восстановлением проверяет,
                    была ли задача уже восстановлена.
        Для дедлайн-задач показывает DeadlineEditDialog.
        """
        # 1. Проверка повторного восстановления (COMPLETED или CANCELLED).
        if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            spawned = self.service.get_spawned_tasks(task.task_id)
            if spawned:
                reply = MessageDialog.question(
                    self,
                    f"Задача «{task.title}» уже была восстановлена. "
                    f"Создать ещё одну задачу с теми же параметрами?",
                    title_text="Уже восстановлена",
                    bg_color=self.bg_color,
                )
                if reply != "yes":
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
        if reply == "yes":
            self.service.delete_forever(task.task_id)
            self._reload_tasks()

    # ============================================================
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def closeEvent(self, event):
        """При закрытии архива — обновляем список задач в PlannerWindow.

        Родитель (PlannerWindow) не знает, что мы меняли активные задачи
        через restore_task. После закрытия архива просим родителя
        перерисовать список.
        """
        parent = self.parent()
        if parent is not None and hasattr(parent, "_reload_tasks"):
            parent._reload_tasks()
        super().closeEvent(event)