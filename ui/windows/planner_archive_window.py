"""
Окно архива задач планировщика.

UI-каркас без данных. Наследник _BasePlannerListWindow.
"""

from ui.windows.planner_base_window import _BasePlannerListWindow


from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget
from PySide6.QtCore import Qt
from ui.factories.factories import (
    LabelFactory, ButtonFactory, LayoutFactory, InputWidgetFactory,
    DeadlineFieldsWidget,
    )
from ui.windows.message_dialog import MessageDialog
from ui.windows.planner_base_window import _BasePlannerListWindow
from models.planner_task import PlannerTask, TaskStatus, TaskPriority
from ui.factories.window_factories import ExtendedWindowFactory

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

        if not task.is_recurring_instance():
            restore_btn = ButtonFactory.create_button(
                container, "↺", bg_color=(100, 130, 150),
                fixed_size=(26, 26), padding="0px", font_size=14,
            )
            restore_btn.clicked.connect(
                lambda checked=False, t=task: self._on_restore_task(t)
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
            deadline_datetime = dialog.get_deadline_data()
        elif task.is_generator():
            dialog = PlannerRecurrenceEditDialog(self, task)
            if dialog.exec() != QDialog.Accepted:
                return
            recurrence_data = dialog.get_recurrence_data()

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

class DeadlineEditDialog(QDialog):
    """Диалог редактирования дедлайна.

    Роль: открывается из PlannerArchiveWindow при восстановлении
          дедлайн-задачи. Позволяет задать новый дедлайн; приоритет
          остаётся DEADLINE без возможности смены.
    """

    def __init__(self, parent=None, task=None, planner_service=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerArchiveWindow).
            task — PlannerTask для восстановления.
            planner_service — не используется сейчас, оставлено на будущее.
        """
        super().__init__(parent)
        self._task = task
        self._service = planner_service
        bg_color = (70, 80, 90, 0.95)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Восстановление дедлайна",
            bg_color=bg_color,
            close_button=False,
            ok_cancel=True,
            ok_callback=self.accept,
            cancel_callback=self.reject,
            draggable=True,
            return_content_layout=True,
            default_width=420,
            default_height=280,
        )

        # Название задачи (read-only).
        title_lbl = LabelFactory.create_label(
            self,
            text=f"Задача: {task.title}",
            bg_color=(0, 0, 0, 0),
            text_color="#ffffff",
            alignment=Qt.AlignCenter,
            word_wrap=True,
            font_size=13,
            font_weight="bold",
        )
        content_layout.addWidget(title_lbl)

        # Строка «Тип дедлайна»: label + combo.
        type_row = QWidget()
        type_row_layout = QHBoxLayout(type_row)
        type_row_layout.setContentsMargins(0, 0, 0, 0)
        type_row_layout.setSpacing(6)
        type_row_layout.addWidget(LabelFactory.create_label(
            type_row, "Тип:",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4", font_size=11,
        ))
        # Combo типа — темнее фона диалога (70, 80, 90), чтобы визуально
        # читалось как поле ввода, а не сливалось с фоном.
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            type_row,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=(50, 60, 70, 0.95),
            border="1px solid #3a4556",
        )
        type_row_layout.addWidget(self.deadline_type_combo, 1)
        content_layout.addWidget(type_row)

        # Поля ввода — та же сине-серая палитра, что у combo.
        self._fields = DeadlineFieldsWidget(
            self,
            initial=task.deadline_datetime,
            mode="inclusive",
            field_bg=(50, 60, 70, 0.95),
            field_border="1px solid #3a4556",
        )
        content_layout.addWidget(self._fields)

        # Триггер.
        self.deadline_type_combo.currentTextChanged.connect(
            lambda text: self._fields.set_mode(
                "inclusive" if text == "До даты включительно" else "duration"
            )
        )

    def get_deadline_data(self):
        """Возвращает новую строку дедлайна или None."""
        mode = ("inclusive"
                if self.deadline_type_combo.currentText() == "До даты включительно"
                else "duration")
        return self._fields.get_deadline_data(mode)

class PlannerRecurrenceEditDialog(QDialog):
    """Диалог редактирования правила повторения.

    Роль: открывается из PlannerArchiveWindow при восстановлении
          регулярной задачи. Позволяет задать новое правило.
    """

    def __init__(self, parent=None, task: PlannerTask = None):
        super().__init__(parent)
        self._task = task
        bg_color = (70, 80, 90, 0.95)

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Восстановление регулярной задачи",
            bg_color=bg_color,
            close_button=False,
            ok_cancel=True,
            ok_callback=self.accept,
            cancel_callback=self.reject,
            draggable=True,
            return_content_layout=True,
            default_width=420,
            default_height=300,
        )

        content_layout.addWidget(LabelFactory.create_label(
            self, f"Задача: {task.title}",
            bg_color=(0, 0, 0, 0), text_color="#ffffff",
            alignment=Qt.AlignCenter, font_size=13, font_weight="bold",
            word_wrap=True,
        ))

        # Поля правила — из фабрики, с предзаполнением из задачи.
        initial = None
        if task and task.recurrence_type:
            initial = {
                "type": task.recurrence_type,
                "value": task.recurrence_value,
                "weekdays": task.recurrence_weekdays,
                "monthdays": task.recurrence_monthdays,
                "use_last_day": task.recurrence_use_last_day,
            }
        self._fields = ButtonFactory.create_recurrence_fields(
            self, initial,
            field_bg=(50, 60, 70, 0.95),
            field_border="1px solid #3a4556",
            button_border="1px solid #6a7a8a",
        )
        content_layout.addWidget(self._fields.rule_combo)
        content_layout.addWidget(self._fields)

    def get_recurrence_data(self):
        """Возвращает правило повторения."""
        return self._fields.get_recurrence_data()