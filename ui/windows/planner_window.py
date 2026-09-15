from PySide6.QtWidgets import (
    QMainWindow, QDialog, QWidget, QHBoxLayout, QVBoxLayout,
    QScrollArea, QSizePolicy, QLabel
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory,
    InputWidgetFactory, LayoutFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from services.planner_service import PlannerService


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
        "default": ["actions", "description", "priority", "status", "date"],
    }

    # Карта: идентификатор колонки → имя метода-строителя.
    COLUMN_BUILDERS = {
        "actions": "_build_actions",
        "description": "_build_description",
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
            planner_service — сервис планировщика. Если None — создаётся
                              собственный экземпляр (fallback).

        Роль: создаёт UI-каркас: заголовок в шапке, крестик, скролл
              с задачами и кнопку «Новая задача» внизу слева.
        """
        super().__init__(parent)
        self.service = planner_service or PlannerService()

        main_layout = WindowFactory.setup_child_window(
            self, "Планировщик",
            bg_color=(70, 60, 50, 0.95)
        )

        # NEW: прокручиваемая область задач.
        # widget_resizable=False — содержимое не подстраивается под ширину
        # окна, появляется горизонтальный скролл при сужении окна.
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setMinimumHeight(300)

        content_widget = QWidget()
        content_widget.setObjectName("tasks_content")
        content_widget.setMinimumWidth(900)

        self.tasks_layout = QVBoxLayout(content_widget)
        self.tasks_layout.setContentsMargins(5, 5, 5, 5)
        self.tasks_layout.setSpacing(5)
        # Растяжка внизу — строки прижимаются к верхней кромке.
        self.tasks_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # NEW: нижняя панель с кнопкой «Новая задача».
        bottom_layout = QHBoxLayout()
        self.new_task_btn = ButtonFactory.create_button(
            self, "Новая задача", bg_color=(80, 100, 130),
            padding="8px 16px"
        )
        self.new_task_btn.clicked.connect(self._on_new_task)
        bottom_layout.addWidget(self.new_task_btn)
        bottom_layout.addStretch()
        main_layout.addLayout(bottom_layout)

        # Заполняем задачи из сервиса.
        for task in self.service.get_tasks():
            self._add_task_row(task)

    # ---------- Публичные методы ----------

    def _on_new_task(self):
        """Открывает модальный диалог «Новая задача».

        Роль: диалог блокирует только PlannerWindow (Qt.WindowModal),
              не блокируя MainWindow. После exec() смотрим результат —
              при Accepted в следующих задачах будем вызывать add_task.
        """
        dialog = NewTaskDialog(self, self.service)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.exec()

    # ---------- Построение строк ----------

    def _build_task_row(self, task: dict) -> QWidget:
        """Строит виджет одной строки задачи.

        Вход: task — словарь с данными задачи.
        Выход: QWidget с горизонтальным layout.
        Роль: собирает строку из колонок, определённых для типа задачи.
        """
        columns = self.TASK_TYPE_COLUMNS.get(
            task.get("task_type", "default"),
            self.TASK_TYPE_COLUMNS["default"]
        )
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        for col_id in columns:
            builder_name = self.COLUMN_BUILDERS[col_id]
            widget = getattr(self, builder_name)(task)
            if widget is not None:
                # Описание растягивается, остальные — по содержимому.
                if col_id == "description":
                    layout.addWidget(widget, 1)
                else:
                    layout.addWidget(widget)
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
        layout.addWidget(ButtonFactory.create_edit_button(container, lambda: None))
        layout.addWidget(ButtonFactory.create_delete_button(container, lambda: None))
        return container

    def _build_description(self, task: dict):
        """Описание задачи — растягивающаяся метка с переносом слов."""
        lbl = LabelFactory.create_label(
            self,
            text=task.get("description", ""),
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            word_wrap=True,
            font_family="Consolas",
            font_size=11
        )
        lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return lbl

    def _build_priority(self, task: dict):
        """Приоритет задачи — цветной лейбл."""
        priority = task.get("priority", "")
        color = self.PRIORITY_COLORS.get(priority, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=priority, bg_color=color,
            font_weight="bold", min_size=(100, 0)
        )

    def _build_status(self, task: dict):
        """Статус задачи — цветной лейбл."""
        status = task.get("status", "")
        color = self.STATUS_COLORS.get(status, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=status, bg_color=color,
            font_weight="bold", min_size=(100, 0)
        )

    def _build_date(self, task: dict):
        """Дата создания задачи — нейтральный лейбл по центру."""
        date_str = task.get("created_date", "")
        return LabelFactory.create_label(
            self, text=date_str, bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4", alignment=Qt.AlignCenter, min_size=(100, 0)
        )

    # ---------- Очистка ----------

    def cleanup(self):
        """Очистка состояния при закрытии. Пока нечего чистить."""
        pass

    def closeEvent(self, event):
        """Обработка закрытия окна."""
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

    def __init__(self, parent=None, planner_service=None):
        """Конструктор.

        Вход:
            parent — родитель (PlannerWindow).
            planner_service — сервис для получения списка приоритетов.

        Роль: строит форму с тремя полями и подключает показ скрытого
              поля «Подробное описание» к editingFinished у «Задачи».
        """
        super().__init__(parent)
        self.service = planner_service

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
        self.full_desc_edit.setVisible(False)
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
        self.task_edit.editingFinished.connect(self._show_full_description)

        # NEW: форма из двух полей — «Задача» и «Приоритет».
        form = LayoutFactory.create_form(
            self,
            rows=[
                ("Задача:", self.task_edit),
                ("Приоритет:", self.priority_combo),
            ],
            spacing=10,
            margins=(10, 10, 10, 10),
        )
        content_layout.addWidget(form)

    def _show_full_description(self):
        """Показывает скрытое поле «Подробное описание» и подгоняет размер.

        Роль: обработчик editingFinished у task_edit. Идемпотентен —
              повторные вызовы просто снова ставят setVisible(True).
        """
        self.full_desc_edit.setVisible(True)
        # Подгоняем размер диалога после появления нового поля.
        self.adjustSize()