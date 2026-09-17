from PySide6.QtWidgets import (
    QMainWindow, QDialog, QWidget, QHBoxLayout, QVBoxLayout,
    QSizePolicy, QLabel, QMessageBox, QLayout
)
from PySide6.QtCore import Qt, QTimer

from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory,
    InputWidgetFactory, LayoutFactory, ListWidgetFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from services.planner_service import PlannerService
from models.planner_task import PlannerTask, TaskPriority


class PlannerWindow(QMainWindow):
    """Окно планировщика задач.

    Назначение:
        Отображает список задач в прокручиваемой области, предоставляет
        кнопку «Новая задача» для открытия диалога-заглушки.

    Роль в программе:
        Открывается по кнопке даты/времени в главном окне. Данные берёт
        из PlannerService. Конструкция строки задачи — через конфигурацию
        колонок, чтобы добавление нового типа задачи было одной записью.
    """

    # Конфигурация колонок по типу задачи.
    # Добавление нового типа — одна запись в этом словаре.
    TASK_TYPE_COLUMNS = {
        "default": ["actions", "title", "priority", "status", "date"],
    }

    # Карта: идентификатор колонки → имя метода-строителя.
    COLUMN_BUILDERS = {
        "actions": "_build_actions",
        "title": "_build_title",
        "priority": "_build_priority",
        "status": "_build_status",
        "date": "_build_date",
    }

    # Цвета приоритетов.
    PRIORITY_COLORS = {
        "Высокий": (180, 70, 70, 0.85),
        "Средний": (180, 150, 70, 0.85),
        "Низкий":  (100, 150, 100, 0.85),
    }

    # Цвета статусов.
    STATUS_COLORS = {
        "Активная":  (80, 100, 160, 0.85),
        "Выполнена": (100, 150, 100, 0.85),
        "Отменена":  (120, 120, 120, 0.85),
    }

    # Нейтральный цвет для неизвестных значений (fallback).
    NEUTRAL_COLOR = (120, 120, 120, 0.85)

    def __init__(self, parent=None, planner_service=None):
        """Конструктор.

        Вход:
            parent — родительское окно (MainWindow).
            planner_service — сервис планировщика. Обязателен.

        Роль: создаёт UI-каркас: заголовок, крестик, скролл с задачами
              и кнопку «Новая задача» внизу. Подключает таймер автообновления.
        """
        super().__init__(parent)
        if planner_service is None:
            raise ValueError("planner_service обязателен")
        self.service = planner_service
        self.bg_color = (70, 60, 50, 0.95)

        main_layout = WindowFactory.setup_child_window(
            self, "Планировщик",
            bg_color=self.bg_color
        )

        # NEW: прокручиваемая область задач.
        scroll = ListWidgetFactory.create_scroll_area(
            self, bg_color=self.bg_color, widget_resizable=False
        )
        scroll.setMinimumHeight(300)

        content_widget = QWidget()
        content_widget.setObjectName("tasks_content")
        content_widget.setMinimumWidth(900)

        self.tasks_layout = QVBoxLayout(content_widget)
        self.tasks_layout.setContentsMargins(5, 5, 5, 5)
        self.tasks_layout.setSpacing(5)
        # NEW: layout сам следит за размером content_widget — при добавлении
        # строк минимум растёт, и виджет автоматически пересчитывает высоту.
        # Без этого widgetResizable=False не даёт контейнеру расти,
        # и задачи остаются за пределами видимой области.
        self.tasks_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        # Растяжка внизу — строки прижимаются к верхней кромке.
        self.tasks_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # NEW: нижняя панель с кнопкой «Новая задача».
        bottom_layout = QHBoxLayout()
        self.new_task_btn = ButtonFactory.create_button(
            self, "Новая задача", bg_color=(90, 80, 70),
            padding="8px 16px"
        )
        self.new_task_btn.clicked.connect(self._on_new_task)
        bottom_layout.addWidget(self.new_task_btn)
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        # NEW: заполняем задачи через единый метод.
        self._reload_tasks()

        # NEW: таймер автообновления раз в 5 минут.
        self._timer = QTimer(self)
        self._timer.setInterval(5 * 60 * 1000)
        self._timer.timeout.connect(self._reload_tasks)
        self._timer.start()

    # ---------- Публичные методы ----------
    def _reload_tasks(self):
        """Очищает список строк и перерисовывает задачи из сервиса.

        Единая точка обновления: вызывается при открытии окна,
        после создания задачи и по таймеру. Stretch в конце сохраняется.
        """
        # Удаляем все виджеты, кроме stretch (последний элемент).
        while self.tasks_layout.count() > 1:
            item = self.tasks_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for task in self.service.get_tasks():
            self._add_task_row(task)

    def _on_new_task(self):
        """Открывает диалог, создаёт задачу, перерисовывает список."""
        dialog = NewTaskDialog(self, self.service)
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted:
            priority = self.service.get_priority_by_display_name(dialog.get_priority())
            self.service.create_task(
                title=dialog.get_title(),
                description=dialog.get_description(),
                priority=priority,
            )
            self._reload_tasks()

    # ---------- Построение строк ----------

    def _build_task_row(self, task: PlannerTask) -> QWidget:
        columns = self.TASK_TYPE_COLUMNS["default"]
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        for col_id in columns:
            builder_name = self.COLUMN_BUILDERS[col_id]
            widget = getattr(self, builder_name)(task)
            if widget is not None:
                if col_id == "title":
                    layout.addWidget(widget, 1)
                else:
                    layout.addWidget(widget)
        layout.addStretch(1)
        return row

    def _add_task_row(self, task: dict):
        """Добавляет строку задачи перед растяжкой.

        Вход: task — словарь задачи.
        Роль: вставляет строку в tasks_layout, сохраняя stretch в конце.
        """
        row = self._build_task_row(task)
        self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, row)

    # ---------- Методы-билдеры колонок ----------

    def _build_actions(self, task: dict) -> QWidget:
        """Кнопки действий: ✓ (выполнено), ✎ (редактировать), ✕ (удалить).

        Пока — заглушки lambda: None. Логика появится в следующих задачах.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        layout.addWidget(ButtonFactory.create_complete_button(container, lambda: None))
        layout.addWidget(ButtonFactory.create_edit_button(
            container,
            lambda checked=False, t=task: self._on_edit_task(t)
        ))
        layout.addWidget(ButtonFactory.create_delete_button(container, lambda: None))
        return container

    def _build_title(self, task: PlannerTask):
        """Название задачи — растягивающаяся метка с переносом слов.

        Вход: task — PlannerTask.
        Выход: QLabel с названием.
        Роль: главная текстовая колонка строки. Раньше здесь было
              подробное описание — заменено на название задачи.
        """
        lbl = LabelFactory.create_label(
            self,
            text=task.title,
            bg_color=(95, 80, 65, 0.7),  # NEW: мягкий тёплый фон
            text_color="#e8dcc8",  # NEW: светлый тёплый текст
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            word_wrap=True,
            font_family="Consolas",
            font_size=11,
            padding="4px 8px",  # NEW: воздух вокруг текста
            border_radius=4,
        )
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lbl

    def _build_priority(self, task: PlannerTask):
        priority = task.priority.display_name
        color = self.PRIORITY_COLORS.get(priority, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=priority, bg_color=color,
            font_weight="bold", min_size=(100, 0)
        )

    def _build_status(self, task: PlannerTask):
        status = task.status.display_name
        color = self.STATUS_COLORS.get(status, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=status, bg_color=color,
            font_weight="bold", min_size=(100, 0)
        )

    def _build_date(self, task: PlannerTask):
        return LabelFactory.create_label(
            self,
            text=task.created_date,
            bg_color=(95, 80, 65, 0.7),      # NEW: тот же фон, что у названия
            text_color="#e8dcc8",            # NEW: тот же светлый текст
            alignment=Qt.AlignCenter,
            min_size=(100, 0),
            padding="4px 8px",
            border_radius=4,
        )

    def _on_edit_task(self, task: PlannerTask):
        """Открывает диалог в режиме редактирования и сохраняет изменения.

        Вход: task — PlannerTask, которую редактируем.
        Выход: нет.

        Роль: если пользователь подтвердил — вызывает service.update_task
              и перерисовывает список. При отмене ничего не меняется.
        """
        dialog = NewTaskDialog(self, self.service, task=task)
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted:
            priority = self.service.get_priority_by_display_name(dialog.get_priority())
            self.service.update_task(
                task_id=task.task_id,
                title=dialog.get_title(),
                description=dialog.get_description(),
                priority=priority,
            )
            self._reload_tasks()
    # ---------- Очистка ----------

    def cleanup(self):
        """Очистка состояния при закрытии. Пока нечего чистить."""
        pass

    def closeEvent(self, event):
        """Обработка закрытия окна: остановка таймера, очистка."""
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()


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

        content_layout = ExtendedWindowFactory.setup_window(
            window=self,
            parent=parent,
            title="Новая задача",
            bg_color=(111, 78, 55, 0.95),
            # NEW: крестик убран — единое поведение остальных диалогов.
            close_button=False,
            ok_cancel=True,
            # Заглушки: обе кнопки вызывают accept/reject.
            ok_callback=self.accept,
            cancel_callback=self.reject,
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
        """Проверяет title. Если пуст — warning и не закрывает."""
        if not self.get_title():
            QMessageBox.warning(self, "Ошибка", "Название задачи не может быть пустым.")
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