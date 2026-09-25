"""
Окно планировщика задач.

Наследник _BasePlannerListWindow. Отображает активные задачи,
позволяет создавать и редактировать, открывает окно архива.
"""

from PySide6.QtWidgets import (
    QMainWindow, QDialog, QWidget, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QLabel, QLayout
)
from PySide6.QtCore import Qt, QTimer
from ui.factories.factories import WindowFactory, ButtonFactory
from ui.windows.planner_task_dialogs import NewTaskDialog
from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from ui.windows.planner_base_window import _BasePlannerListWindow

class PlannerWindow(_BasePlannerListWindow):
    """Окно планировщика задач.

    Роль: отображает активные задачи, позволяет создавать и удалять,
          открывает окно архива.
    """

    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "priority", "status", "date", "specifications"],
    }

    # Расширяем базовые билдеры колонкой действий.
    COLUMN_BUILDERS = {
        **_BasePlannerListWindow.COLUMN_BUILDERS,
        "actions": "_build_actions",
    }

    def __init__(self, parent=None, planner_service=None, archive_service=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            planner_service — сервис активных задач. Обязателен.
            archive_service — сервис архива. Передаётся в архивное окно.
        """
        if planner_service is None:
            raise ValueError("planner_service обязателен")
        self.service = planner_service
        self.archive_service = archive_service
        self._archive_window = None

        super().__init__(
            parent, "Планировщик", bg_color=(70, 60, 50, 0.95),
        )

        # Нижняя панель: «Новая задача» + «Архив» + растяжка.
        bottom_layout = QHBoxLayout()
        self.new_task_btn = ButtonFactory.create_button(
            self, "Новая задача", bg_color=(90, 80, 70), padding="8px 16px",
        )
        self.new_task_btn.clicked.connect(self._on_new_task)
        bottom_layout.addWidget(self.new_task_btn)
        bottom_layout.addStretch()
        self.archive_btn = ButtonFactory.create_button(
            self, "Архив", bg_color=(40, 40, 40), padding="8px 16px",
        )
        self.archive_btn.clicked.connect(self._on_open_archive)
        bottom_layout.addWidget(self.archive_btn)


        self._main_layout.addLayout(bottom_layout)

        # Первая загрузка задач.
        self._reload_tasks()

    # ---------- Источник данных ----------

    def _get_tasks(self):
        """Возвращает активные задачи без экземпляров регулярных.

        Экземпляры показываются только в мини-планировщике; в основном
        списке их не должно быть.
        """
        return [t for t in self.service.get_tasks() if not t.is_recurring_instance()]

    # ---------- Билдер actions ----------

    def _build_actions(self, task: PlannerTask) -> QWidget:
        """Кнопки действий: для генератора ⏸/▶, иначе ✓.

        Вход: task — PlannerTask.
        Выход: QWidget с кнопками.
        Роль: для регулярного генератора вместо ✓ — пауза/возобновление.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if task.is_generator():
            # ⏸ для ACTIVE и WAITING (генератор работает),
            # ▶ только для PAUSED (пользователь может возобновить).
            symbol = "▶" if task.status == TaskStatus.PAUSED else "⏸"
            pause_btn = ButtonFactory.create_button(
                container, symbol, bg_color=(150, 130, 70, 0.85),
                fixed_size=(26, 26), padding="0px", font_size=14,
            )
            pause_btn.clicked.connect(
                lambda checked=False, t=task: self._on_recurring_pause(t)
            )
            layout.addWidget(pause_btn)
        else:
            layout.addWidget(ButtonFactory.create_complete_button(
                container, lambda checked=False, t=task: self._on_task_done(t),
            ))

        layout.addWidget(ButtonFactory.create_edit_button(
            container, lambda checked=False, t=task: self._on_edit_task(t),
        ))
        layout.addWidget(ButtonFactory.create_delete_button(
            container, lambda checked=False, t=task: self._on_task_delete(t),
        ))
        return container

    # ---------- Обработчики ----------

    def _on_new_task(self):
        """Открывает диалог, создаёт задачу, перерисовывает список."""
        dialog = NewTaskDialog(self, self.service)
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            priority = result["priority"]
            if priority == TaskPriority.RECURRING:
                task_type = TaskType.RECURRING
            elif priority == TaskPriority.DEADLINE:
                task_type = TaskType.DEADLINE
            elif priority == TaskPriority.EVENT:
                task_type = TaskType.EVENT
            else:
                task_type = TaskType.REGULAR

            self.service.create_task(
                title=result["title"],
                description=result["description"],
                priority=priority,
                deadline_datetime=result["deadline_datetime"],
                task_type=task_type,
                recurrence_data=result["recurrence_data"],
                event_date=result["event_date"],
            )
            self._reload_tasks()

    def _on_open_archive(self):
        """Открывает окно архива модально относительно PlannerWindow.

        Архив перекрывает планировщик полностью — cover_parent=True,
        плюс сдвиг на 10 пикселей влево и вверх, чтобы точно закрыть
        рамку PlannerWindow.

        Ссылку на архив сохраняем — чтобы в resizeEvent тянуть её
        за PlannerWindow.
        """
        from ui.windows.planner_archive_window import PlannerArchiveWindow
        self._archive_window = PlannerArchiveWindow(
            self, archive_service=self.archive_service
        )
        self._archive_window.setWindowModality(Qt.WindowModal)
        WindowFactory.show_child_window(self, self._archive_window, cover_parent=True)
        self._sync_archive_geometry()

    def _sync_archive_geometry(self):
        """Синхронизирует геометрию архива с PlannerWindow.

        Роль: архив перекрывает PlannerWindow со сдвигом −10 по X и Y.
              Вызывается при открытии и при каждом resize PlannerWindow.
        """
        if self._archive_window is None or not self._archive_window.isVisible():
            return
        geo = self.frameGeometry()
        self._archive_window.setGeometry(
            geo.x() - 10, geo.y() - 10, geo.width(), geo.height()
        )

    def _on_task_done(self, task: PlannerTask) -> None:
        """Кнопка ✓ — задача завершается и уходит в архив.

        status = COMPLETED, completed_date = сегодня.
        """
        self.service.archive_task(task.task_id, TaskStatus.COMPLETED)
        self._reload_tasks()

    def _on_task_delete(self, task: PlannerTask) -> None:
        """Кнопка ✕ — задача отменяется и уходит в архив.

        status = CANCELLED, completed_date = сегодня.
        """
        self.service.archive_task(task.task_id, TaskStatus.CANCELLED)
        self._reload_tasks()

    def _on_recurring_pause(self, task: PlannerTask) -> None:
        """Переключает паузу/возобновление регулярного генератора.

        Вход: task — PlannerTask-генератор.

        Роль:
            - Из ACTIVE или WAITING → PAUSED (пользователь остановил).
            - Из PAUSED → WAITING (возобновление). При этом
              PlannerService.update_status сам пересчитает
              next_generation_date с «догоном» пропущенных дат.

        В ACTIVE генератор вернётся автоматически, когда
        PlannerRecurrenceService при следующем тике увидит у него
        живой экземпляр. Явно этого делать не нужно.
        """
        if task.status == TaskStatus.PAUSED:
            new_status = TaskStatus.WAITING
        else:
            new_status = TaskStatus.PAUSED
        self.service.update_status(task.task_id, new_status)
        self._reload_tasks()

    def _on_edit_task(self, task: PlannerTask) -> None:
        """Открывает диалог редактирования задачи и сохраняет результат."""
        dialog = NewTaskDialog(self, self.service, task=task)
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            self.service.update_task(
                task_id=task.task_id,
                title=result["title"],
                description=result["description"],
                priority=result["priority"],
                deadline_datetime=result["deadline_datetime"],
                recurrence_data=result["recurrence_data"],
                event_date=result["event_date"],   # NEW
            )
            self._reload_tasks()

    def resizeEvent(self, event):
        """При изменении размера PlannerWindow — тянем за собой архив.

        Роль: MainWindow.resizeEvent меняет размер PlannerWindow,
              но не знает про открытое окно архива (оно — child
              PlannerWindow, а не MainWindow). Синхронизируем
              геометрию архива вручную.
        """
        super().resizeEvent(event)
        self._sync_archive_geometry()

    # ---------- Закрытие ----------

    def closeEvent(self, event):
        """Чистит active_child у MainWindow, затем — базовая логика."""
        if self.parent() and hasattr(self.parent(), "active_child"):
            self.parent().active_child = None
        super().closeEvent(event)