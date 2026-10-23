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
from ui.base.planner_base_window import _BasePlannerListWindow
from ui.windows.planner_themes_dialog import PlannerThemesDialog
from ui.windows.planner_task_dialogs import NewTaskDialog
from utils.log_tools.decorators import log_button_action
from utils.filter_utils import FieldDef
from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from ui.styles import ColorCalculator, WindowStyle


class PlannerWindow(_BasePlannerListWindow):
    """Окно планировщика задач.

    Роль: отображает активные задачи, позволяет создавать и удалять,
          открывает окно архива.
    """

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = "PlannerWindow.planner_window"
    LOGGER_DOMAIN = "planner"

    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "checklist", "priority", "theme", "status", "date", "specifications"],
    }

    # Билдеры колонок (расширяем базовые)
    COLUMN_BUILDERS = {
        **_BasePlannerListWindow.COLUMN_BUILDERS,
        "actions": "_build_actions",
    }

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, planner_service=None,
                 archive_service=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            planner_service — сервис активных задач. Обязателен.
            archive_service — сервис архива. Передаётся в архивное окно.
        """
        if planner_service is None:
            raise ValueError("planner_service обязателен")

        # Цвет от родителя
        parent_bg = WindowStyle.resolve_parent_bg(parent, (50, 50, 50))
        bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r + 10,
            g_fn=lambda g: g + 5,
            b_fn=lambda b: b - 5,
            alpha=0.95,
        )

        self.service = planner_service
        self.archive_service = archive_service
        self._archive_window = None

        super().__init__(
            parent, "Планировщик", bg_color=bg_color,
            log_manager_v2=log_manager_v2,
            main_config=getattr(parent, "main_config", None),
        )

        # ---------- ЭЛЕМЕНТЫ UI ----------
        self.new_task_btn = ButtonFactory.create_button(
            self, "Новая задача", bg_color=(90, 80, 70), padding="8px 16px",
        )
        self.btn_more = ButtonFactory.create_button(
            self, "Дополнительно", bg_color=(40, 40, 40), padding="8px 16px",
        )
        self.archive_btn = ButtonFactory.create_button(
            self, "Архив", bg_color=(40, 40, 40), padding="8px 16px",
        )

        # ---------- МАКЕТ ----------
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.new_task_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_more)
        bottom_layout.addWidget(self.archive_btn)
        self._main_layout.addLayout(bottom_layout)

        # ---------- ПОДКЛЮЧЕНИЕ СИГНАЛОВ ----------
        self.new_task_btn.clicked.connect(self._on_new_task)
        self.btn_more.clicked.connect(self._on_open_themes_dialog)
        self.archive_btn.clicked.connect(self._on_open_archive)

        # Первая загрузка задач.
        self._reload_tasks()

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================

    @log_button_action("btn_more", "Ошибка при открытии окна тем: {e}")
    def _on_open_themes_dialog(self):
        """Открывает окно настройки тем задач."""
        if self.parent() is None or not hasattr(self.parent(), "main_config"):
            return

        main_config = self.parent().main_config
        dialog = PlannerThemesDialog(
            self, main_config, log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()

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
                checklist_required=result["checklist_required"],
                checklist=[],
            )
            self._reload_tasks()

    def _on_open_archive(self):
        """Открывает окно архива модально относительно PlannerWindow."""
        from ui.windows.planner_archive_window import PlannerArchiveWindow
        self._archive_window = PlannerArchiveWindow(
            self,
            archive_service=self.archive_service,
            log_manager_v2=self.log_manager_v2,
        )
        self._archive_window.setWindowModality(Qt.WindowModal)
        WindowFactory.show_child_window(self, self._archive_window, cover_parent=True)
        self._sync_archive_geometry()

    def _on_task_done(self, task: PlannerTask) -> None:
        """Кнопка ✓ — задача завершается и уходит в архив."""
        self.service.archive_task(task.task_id, TaskStatus.COMPLETED)
        self._reload_tasks()

    def _on_task_delete(self, task: PlannerTask) -> None:
        """Кнопка ✕ — задача отменяется и уходит в архив."""
        self.service.archive_task(task.task_id, TaskStatus.CANCELLED)
        self._reload_tasks()

    def _on_recurring_pause(self, task: PlannerTask) -> None:
        """Переключает паузу/возобновление регулярного генератора."""
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
                event_date=result["event_date"],
            )
            if task.checklist_required != result["checklist_required"]:
                self.service.set_checklist_required(
                    task.task_id, result["checklist_required"],
                )
            self._reload_tasks()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: БИЛДЕРЫ И ИСТОЧНИКИ
    # ============================================================

    def _get_tasks(self):
        """Возвращает активные задачи без экземпляров регулярных."""
        return [t for t in self.service.get_tasks() if not t.is_recurring_instance()]

    def _get_filter_field_defs(self):
        """Категории фильтра для PlannerWindow."""
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
        ]

    def _build_actions(self, task: PlannerTask) -> QWidget:
        """Кнопки действий: для генератора ⏸/▶, иначе ✓."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if task.is_generator():
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

    # ============================================================
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def _sync_archive_geometry(self):
        """Синхронизирует геометрию архива с PlannerWindow."""
        if self._archive_window is None or not self._archive_window.isVisible():
            return
        geo = self.frameGeometry()
        self._archive_window.setGeometry(
            geo.x() - 10, geo.y() - 10, geo.width(), geo.height()
        )

    def resizeEvent(self, event):
        """При изменении размера PlannerWindow — тянем за собой архив."""
        super().resizeEvent(event)
        self._sync_archive_geometry()

    def closeEvent(self, event):
        """Чистит active_child у MainWindow, затем — базовая логика."""
        if self.parent() and hasattr(self.parent(), "active_child"):
            self.parent().active_child = None
        super().closeEvent(event)