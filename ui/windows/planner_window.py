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

from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory,
    InputWidgetFactory, LayoutFactory, ListWidgetFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from services.planner_service import PlannerService
from models.planner_task import PlannerTask, TaskPriority
from ui.windows.message_dialog import MessageDialog, NotificationDialog
from ui.windows.planner_base_window import _BasePlannerListWindow


class PlannerWindow(_BasePlannerListWindow):
    """Окно планировщика задач.

    Роль: отображает активные задачи, позволяет создавать и удалять,
          открывает окно архива.
    """

    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "priority", "status", "date"],
    }

    # Расширяем базовые билдеры колонкой действий.
    COLUMN_BUILDERS = {
        **_BasePlannerListWindow.COLUMN_BUILDERS,
        "actions": "_build_actions",
    }

    def __init__(self, parent=None, planner_service=None):
        if planner_service is None:
            raise ValueError("planner_service обязателен")
        self.service = planner_service

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
        return self.service.get_tasks()

    # ---------- Билдер actions ----------

    def _build_actions(self, task: PlannerTask) -> QWidget:
        """Кнопки действий: ✓, ✎, ✕."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

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
            self.service.create_task(
                title=dialog.get_title(),
                description=dialog.get_description(),
                priority=priority,
            )
            self._reload_tasks()

    def _on_open_archive(self):
        """Открывает окно архива модально относительно PlannerWindow.

        Архив перекрывает планировщик полностью — cover_parent=True.
        """
        from ui.windows.planner_archive_window import PlannerArchiveWindow
        window = PlannerArchiveWindow(self)
        window.setWindowModality(Qt.WindowModal)
        WindowFactory.show_child_window(self, window, cover_parent=True)
        geo = window.geometry()
        window.setGeometry(geo.x() - 10, geo.y() - 10, geo.width(), geo.height())

    def _on_task_done(self, task: PlannerTask) -> None:
        """Заглушка: сейчас удаляет. В будущем — архивация как COMPLETED."""
        self.service.archive_task(task.task_id)
        self._reload_tasks()

    def _on_task_delete(self, task: PlannerTask) -> None:
        """Заглушка: сейчас удаляет. В будущем — архивация как CANCELLED."""
        self.service.archive_task(task.task_id)
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
            else ["Высокий", "Средний", "Низкий"]
        )
        self.priority_combo = InputWidgetFactory.create_combo_box(
            self,
            items=priorities,
            current_index=1,
            bg_color=(85, 60, 42, 0.9),
            border="1px solid #6b4a33",
        )

        # NEW: триггер — при потере фокуса полем «Задача» показать
        # «Подробное описание».
        self.task_edit.textChanged.connect(self._on_title_changed)

        # NEW: форма из двух полей — «Задача» и «Приоритет».
        label_kwargs = {
            "bg_color": (145, 105, 75, 0.0),
            "text_color": "#dabdab",
            "padding": "4px 8px",
            "border_radius": 3,
            "alignment": Qt.AlignLeft | Qt.AlignVCenter,
            "fixed_size": (120, 24),  # NEW: фиксированный размер
        }
        task_label = LabelFactory.create_label(self, "Задача:", **label_kwargs)
        priority_label = LabelFactory.create_label(self, "Приоритет:", **label_kwargs)

        form = LayoutFactory.create_form(
            self,
            rows=[
                (task_label, self.task_edit),
                (priority_label, self.priority_combo),
            ],
            spacing=10,
            margins=(10, 10, 10, 10),
        )
        content_layout.addWidget(form)

        if not self.creator:
            self.task_edit.setText(self.task.title)
            self.full_desc_edit.setPlainText(self.task.description)
            # Приоритет ищем по display_name — устойчивее, чем по индексу.
            # Если в будущем поменяется состав TaskPriority — цикл всё равно
            # найдёт нужное значение.
            for i in range(self.priority_combo.count()):
                if self.priority_combo.itemText(i) == self.task.priority.display_name:
                    self.priority_combo.setCurrentIndex(i)
                    break

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