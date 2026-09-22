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
from typing import Optional
from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory,
    InputWidgetFactory, LayoutFactory, ListWidgetFactory,
    DeadlineFieldsWidget,
    )
from ui.factories.window_factories import ExtendedWindowFactory
from services.planner_service import PlannerService
from models.planner_task import PlannerTask, TaskPriority, TaskStatus, TaskType
from ui.windows.message_dialog import MessageDialog, NotificationDialog
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
            # ⏸ если ACTIVE, ▶ если PAUSED.
            symbol = "⏸" if task.status == TaskStatus.ACTIVE else "▶"
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
            priority = self.service.get_priority_by_display_name(
                dialog.get_priority()
            )
            # NEW: определение типа задачи по приоритету.
            task_type = TaskType.REGULAR
            if priority == TaskPriority.RECURRING:
                task_type = TaskType.RECURRING
            elif priority == TaskPriority.DEADLINE:
                task_type = TaskType.DEADLINE

            self.service.create_task(
                title=dialog.get_title(),
                description=dialog.get_description(),
                priority=priority,
                deadline_datetime=dialog.get_deadline_data(),
                task_type=task_type,
                recurrence_data=dialog.get_recurrence_data(),
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
        Роль: ACTIVE → PAUSED, PAUSED → ACTIVE.
        """
        new_status = (TaskStatus.PAUSED if task.status == TaskStatus.ACTIVE
                      else TaskStatus.ACTIVE)
        self.service.update_status(task.task_id, new_status)
        self._reload_tasks()

    def _on_edit_task(self, task: PlannerTask) -> None:
        """Редактирование задачи."""
        dialog = NewTaskDialog(self, self.service, task=task)
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted:
            priority = self.service.get_priority_by_display_name(
                dialog.get_priority()
            )
            self.service.update_task(
                task_id=task.task_id,
                title=dialog.get_title(),
                description=dialog.get_description(),
                priority=priority,
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


class NewTaskDialog(QDialog):
    """Диалог-заглушка «Новая задача».

    Назначение:
        Показывает форму с полями: «Задача» (QLineEdit), «Приоритет»
        (QComboBox) и условно появляющимся «Подробное описание» (QTextEdit).
        Ничего не сохраняет — OK/Отмена через accept/reject.

    Роль в программе:
        Открывается из PlannerWindow по кнопке «Новая задача» через
        setWindowModality(Qt.WindowModal) + exec(). Модальность блокирует
        только PlannerWindow.
    """

    def __init__(self, parent=None, planner_service=None, task=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerWindow).
            planner_service — сервис для получения списка приоритетов.

        Роль: строит форму с тремя полями и подключает показ скрытого
              поля «Подробное описание» к editingFinished у «Задачи».
        """
        super().__init__(parent)
        self.service = planner_service
        self.task = task
        self.creator = task is None
        self.bg_color = (111, 78, 55, 0.95)
        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Новая задача",
            bg_color=self.bg_color,
            # NEW: крестик убран — единое поведение остальных диалогов.
            close_button=False,
            ok_cancel=True,
            # Заглушки: обе кнопки вызывают accept/reject.
            ok_callback=self.accept,
            cancel_callback=self.reject,
            draggable= True,
            return_content_layout=True,
            default_width=400,
            default_height=350,
        )

        # NEW: скрытое поле «Подробное описание».
        # Label создаём вручную — чтобы иметь ссылку для setVisible.
        # LayoutFactory.create_form принимает QLabel как первый элемент,
        # если это не str (см. его код).
        self.full_desc_edit = InputWidgetFactory.create_text_edit(
            self,
            placeholder="Подробное описание...",
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        self.full_desc_edit.setReadOnly(True)
        content_layout.addWidget(self.full_desc_edit)

        # NEW: поле «Задача» — без placeholder.
        self.task_edit = InputWidgetFactory.create_line_edit(
            self,
            bg_color=(85, 60, 42, 0.9),
            text_color="#d4d4d4",
            border="1px solid #6b4a33",
            border_radius=3,
            padding="3px",
        )

        # NEW: комбобокс приоритета. Дефолт — «Средний» (индекс 1).
        priorities = (
            self.service.get_priorities() if self.service
            else ["Дедлайн", "Высокий", "Средний", "Низкий"]
        )
        self.priority_combo = InputWidgetFactory.create_combo_box(
            self,
            items=priorities,
            current_index=2,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )

        # NEW: combo типа дедлайна — в ряду с приоритетом.
        # Изначально скрыт, появляется при выборе DEADLINE.
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        self.deadline_type_combo.setVisible(False)

        self._recurrence_fields = ButtonFactory.create_recurrence_fields(self)
        self._recurrence_fields.setVisible(False)

        # Строка «Приоритет» — контейнер из двух combo.
        priority_row = QWidget()
        priority_row_layout = QHBoxLayout(priority_row)
        priority_row_layout.setContentsMargins(0, 0, 0, 0)
        priority_row_layout.setSpacing(6)
        priority_row_layout.addWidget(self.priority_combo, 1)
        priority_row_layout.addWidget(self.deadline_type_combo, 1)

        self.task_edit.textChanged.connect(self._on_title_changed)

        # Поля ввода дедлайна — под формой, показываются при DEADLINE.
        self._deadline_fields = DeadlineFieldsWidget(self)
        self._deadline_fields.setVisible(False)

        label_kwargs = {
            "bg_color": (145, 105, 75, 0.0),
            "text_color": "#dabdab",
            "padding": "4px 8px",
            "border_radius": 3,
            "alignment": Qt.AlignLeft | Qt.AlignVCenter,
            "fixed_size": (120, 24),
        }
        task_label = LabelFactory.create_label(self, "Задача:", **label_kwargs)
        priority_label = LabelFactory.create_label(self, "Приоритет:", **label_kwargs)

        form = LayoutFactory.create_form(
            self,
            rows=[
                (task_label, self.task_edit),
                (priority_label, priority_row),
            ],
            spacing=10,
            margins=(10, 10, 10, 10),
        )
        content_layout.addWidget(form)
        content_layout.addWidget(self._deadline_fields)
        content_layout.addWidget(self._recurrence_fields)
        # Триггеры.
        self.priority_combo.currentTextChanged.connect(self._on_priority_changed)
        self.deadline_type_combo.currentTextChanged.connect(self._on_deadline_type_changed)

        # Предзаполнение при редактировании (один блок, без дублирования).
        if not self.creator:
            self.task_edit.setText(self.task.title)
            self.full_desc_edit.setPlainText(self.task.description)
            for i in range(self.priority_combo.count()):
                if self.priority_combo.itemText(i) == self.task.priority.display_name:
                    self.priority_combo.setCurrentIndex(i)
                    break
            # Показать поля дедлайна, если задача дедлайновая.
            self._on_priority_changed(self.priority_combo.currentText())
            if self.task.priority == TaskPriority.DEADLINE and self.task.deadline_datetime:
                self._deadline_fields._load_initial(self.task.deadline_datetime)

    def get_title(self) -> str:
        """Возвращает введённое название, очищенное от пробелов."""
        return self.task_edit.text().strip()

    def get_description(self) -> str:
        """Возвращает подробное описание."""
        return self.full_desc_edit.toPlainText().strip()

    def get_priority(self) -> str:
        """Возвращает выбранный приоритет как строку (display_name)."""
        return self.priority_combo.currentText()

    def accept(self):
        """Проверяет title. Пустое название — предупреждение.

        Поведение кнопок MessageDialog:
            «Да»  (Accepted) — закрыть только предупреждение,
                               остаться в диалоге создания.
            «Нет» (Rejected) — закрыть предупреждение и отменить
                               создание задачи (закрыть этот диалог).
        """
        if not self.get_title():
            result = MessageDialog.warning(
                self,
                "Название задачи не может быть пустым.\n"
                "Хотите продолжить создание задачи?",
                bg_color=self.bg_color,
            )
            if result == QDialog.Rejected:
                # «Нет» — пользователь решил не продолжать.
                # reject() закроет NewTaskDialog с результатом Rejected,
                # и в _on_new_task ветка создания задачи не сработает.
                self.reject()
            return
        super().accept()

    def _on_title_changed(self, text: str) -> None:
        """Разрешает редактирование описания, только если название непустое.

        Вход: text — текущий текст поля «Задача».
        Выход: нет.

        Роль: переключает readOnly у full_desc_edit. Текст описания
              НЕ очищается — при возврате названия поле снова доступно
              с прежним содержимым. adjustSize() убран: диалог больше
              не «прыгает», поле видно всегда.
        """
        # strip() — чтобы одни пробелы не считались «непустым» названием.
        self.full_desc_edit.setReadOnly(not bool(text.strip()))

    def _on_priority_changed(self, text: str) -> None:
        """Показывает combo типа и поля дедлайна, если выбран DEADLINE."""
        # combo типа дедлайна — в ряду с приоритетом.
        self.deadline_type_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["До даты включительно", "Срок"],
            current_index=0,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )
        self.deadline_type_combo.setVisible(False)

        # Триггеры.
        self.priority_combo.currentTextChanged.connect(self._on_priority_changed)
        self.deadline_type_combo.currentTextChanged.connect(self._on_deadline_type_changed)
        self.rule_combo.currentTextChanged.connect(self._on_rule_changed)

    def _on_deadline_type_changed(self, text: str) -> None:
        """Переключает режим полей ввода в DeadlineFieldsWidget."""
        mode = "inclusive" if text == "До даты включительно" else "duration"
        self._deadline_fields.set_mode(mode)

    def _on_priority_changed(self, text: str) -> None:
        """Показывает нужные поля в зависимости от приоритета."""
        is_deadline = (text == TaskPriority.DEADLINE.display_name)
        is_recurring = (text == TaskPriority.RECURRING.display_name)

        self.deadline_type_combo.setVisible(is_deadline)
        self._deadline_fields.setVisible(is_deadline)

        # Виджет правила — только для RECURRING.
        self._recurrence_fields.setVisible(is_recurring)

    def get_deadline_data(self) -> Optional[str]:
        """Возвращает строку дедлайна или None.

        Для не-DEADLINE приоритетов всегда None.
        """
        if self.priority_combo.currentText() != TaskPriority.DEADLINE.display_name:
            return None
        mode = ("inclusive"
                if self.deadline_type_combo.currentText() == "До даты включительно"
                else "duration")
        return self._deadline_fields.get_deadline_data(mode)

    def get_recurrence_data(self) -> Optional[dict]:
        """Возвращает правило повторения или None.

        Делегирует в PlannerRecurrenceFieldsWidget.
        Для не-RECURRING приоритетов возвращает None.
        """
        if self.priority_combo.currentText() != TaskPriority.RECURRING.display_name:
            return None
        return self._recurrence_fields.get_recurrence_data()