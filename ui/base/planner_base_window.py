"""
Базовое окно со списком задач для планировщика.

Модуль содержит класс _BasePlannerListWindow — общую часть для
PlannerWindow и PlannerArchiveWindow: скролл, tasks_layout, цвета,
билдеры строк, _reload_tasks, _build_task_row, таймер автообновления,
closeEvent.

Роль в программе:
    Оба окна планировщика — наследники. Логгер V2 создаётся в
    базовом __init__, если передан log_manager_v2 и задан
    LOGGER_SOURCE у наследника.

Переезд: раньше файл лежал в ui/windows/, теперь в ui/base/ —
базовый класс логически относится к ui.base наравне с
BaseEditDialog и BaseServiceWindow. Старый путь удалён.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QLayout
)
from PySide6.QtCore import Qt, QTimer

from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory, ListWidgetFactory,
    BaseWidgetFactory,
)
from models.planner_task import TaskPriority


class _BasePlannerListWindow(QMainWindow):
    """Базовое окно со списком задач.

    Общая часть для PlannerWindow и PlannerArchiveWindow.

    Наследники определяют:
        LOGGER_SOURCE / LOGGER_DOMAIN — идентификация для LoggerV2.
        TASK_TYPE_COLUMNS — список колонок.
        _get_tasks() — источник данных.
        При необходимости расширяют COLUMN_BUILDERS.
    """

    # Интервал автообновления — 5 минут.
    RELOAD_INTERVAL_MS = 5 * 60 * 1000

    # Сдвиг каналов для акцентного фона (название задачи, дата).
    ACCENT_SHIFT = 25
    ACCENT_ALPHA = 0.7

    # NEW: идентификация для LoggerV2. Наследники переопределяют.
    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None

    PRIORITY_COLORS = {
        "Событие": (240, 240, 40, 0.85),
        "Регулярная": (80, 160, 220, 0.85),
        "Дедлайн": (220, 130, 60, 0.85),
        "Высокий": (180, 70, 70, 0.85),
        "Средний": (180, 150, 70, 0.85),
        "Низкий": (100, 150, 100, 0.85),
    }

    STATUS_COLORS = {
        "Активная": (80, 100, 160, 0.85),
        "Выполнена": (100, 150, 100, 0.85),
        "Отменена": (120, 120, 120, 0.85),
        "Просрочено": (200, 70, 70, 0.85),
        "Истекло": (200, 70, 70, 0.85),
        "Пауза": (150, 130, 70, 0.85),
        "Ожидание": (100, 100, 150, 0.85),
    }

    # Нейтральный цвет для неизвестных значений.
    NEUTRAL_COLOR = (120, 120, 120, 0.85)

    # Базовые строители колонок. Наследники могут дополнить.
    COLUMN_BUILDERS = {
        "title": "_build_title",
        "priority": "_build_priority",
        "status": "_build_status",
        "date": "_build_date",
        "specifications": "_build_specifications",
    }

    def __init__(self, parent=None, title="", bg_color=(64, 48, 66, 0.8),
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок окна.
            bg_color — цвет фона. Передаётся в WindowFactory и в скролл.
            log_manager_v2 — LogManagerV2 или None. Если задан и
                             LOGGER_SOURCE у наследника — создаётся
                             self.logger.

        Роль: строит общий каркас (заголовок, крестик, скролл,
              tasks_layout), запускает таймер автообновления.

        REPLACE: добавлены log_manager_v2 и создание self.logger.
        """
        super().__init__(parent)
        self.bg_color = bg_color

        # NEW: логгер V2.
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None and self.LOGGER_SOURCE is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )

        # Акцентный цвет для названий задач и даты — вычисляется
        # от фона окна.
        self._accent_bg = self._calc_accent_color(bg_color)
        self._accent_text = BaseWidgetFactory.calc_text_color(self._accent_bg)

        main_layout = WindowFactory.setup_child_window(
            self, title, bg_color=self.bg_color,
        )

        # Прокручиваемая область задач.
        scroll = ListWidgetFactory.create_scroll_area(
            self, bg_color=self.bg_color, widget_resizable=False,
        )
        scroll.setMinimumHeight(300)

        content_widget = QWidget()
        content_widget.setObjectName("tasks_content")
        content_widget.setMinimumWidth(900)

        self.tasks_layout = QVBoxLayout(content_widget)
        self.tasks_layout.setContentsMargins(5, 5, 5, 5)
        self.tasks_layout.setSpacing(5)
        self.tasks_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        # Растяжка внизу — строки прижимаются к верхней кромке.
        self.tasks_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Сохраняем главный layout — наследники добавят свои кнопки.
        self._main_layout = main_layout

        # Таймер автообновления — общий для всех наследников.
        self._timer = QTimer(self)
        self._timer.setInterval(self.RELOAD_INTERVAL_MS)
        self._timer.timeout.connect(self._reload_tasks)
        self._timer.start()

    # ---------- Вспомогательные ----------

    @classmethod
    def _calc_accent_color(cls, bg_color) -> tuple:
        """Вычисляет акцентный цвет от фона окна.

        Вход: bg_color — кортеж (r, g, b) или (r, g, b, a).
        Выход: кортеж (r+shift, g+shift, b+shift, alpha).

        Роль: используется для фона названия задачи и даты, чтобы
              они визуально отделялись от основного фона.
        """
        if not isinstance(bg_color, (tuple, list)) or len(bg_color) < 3:
            return (95, 80, 65, cls.ACCENT_ALPHA)
        r, g, b = bg_color[:3]

        def clamp(v):
            return max(0, min(255, int(v)))

        return (
            clamp(r + cls.ACCENT_SHIFT),
            clamp(g + cls.ACCENT_SHIFT),
            clamp(b + cls.ACCENT_SHIFT),
            cls.ACCENT_ALPHA,
        )

    # ---------- Абстрактный метод ----------

    def _get_tasks(self):
        """Возвращает список задач для отрисовки. Наследник реализует."""
        raise NotImplementedError

    # ---------- Отрисовка ----------

    def _reload_tasks(self):
        """Очищает строки (кроме растяжки) и перерисовывает задачи."""
        while self.tasks_layout.count() > 1:
            item = self.tasks_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for task in self._get_tasks():
            self._add_task_row(task)

    def _add_task_row(self, task):
        """Добавляет строку перед растяжкой."""
        row = self._build_task_row(task)
        self.tasks_layout.insertWidget(self.tasks_layout.count() - 1, row)

    def _build_task_row(self, task):
        """Собирает строку из колонок, определённых в TASK_TYPE_COLUMNS."""
        columns = self.TASK_TYPE_COLUMNS.get(
            "default", self.TASK_TYPE_COLUMNS["default"]
        )
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        for col_id in columns:
            builder_name = self.COLUMN_BUILDERS.get(col_id)
            if builder_name is None:
                continue
            widget = getattr(self, builder_name)(task)
            if widget is not None:
                # Название растягивается, остальные — по содержимому.
                if col_id == "title":
                    layout.addWidget(widget, 1)
                else:
                    layout.addWidget(widget)
        layout.addStretch(1)
        return row

    # ---------- Билдеры колонок ----------

    def _build_title(self, task):
        """Название задачи — кликабельная кнопка.

        Вход: task — PlannerTask.
        Выход: QPushButton с названием.
        Роль: клик открывает NotificationDialog с описанием.
        """
        btn = ButtonFactory.create_button(
            self,
            text=task.title,
            bg_color=self._accent_bg,
            text_color=self._accent_text,
            padding="4px 8px",
            border_radius=4,
            alignment="left",
            font_family="Consolas",
            font_size=11,
        )
        btn.setMaximumWidth(300)
        btn.setToolTip(task.title)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        btn.clicked.connect(
            lambda checked=False, t=task: self._on_title_clicked(t)
        )
        return btn

    def _build_priority(self, task):
        """Приоритет задачи — цветной лейбл."""
        priority = task.priority.display_name
        color = self.PRIORITY_COLORS.get(priority, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=priority, bg_color=color,
            font_weight="bold", min_size=(100, 0),
        )

    def _build_status(self, task):
        """Статус задачи — цветной лейбл."""
        status = task.status.display_name
        color = self.STATUS_COLORS.get(status, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=status, bg_color=color,
            font_weight="bold", min_size=(100, 0),
        )

    def _build_date(self, task):
        """Дата создания задачи — лейбл с акцентным фоном."""
        return LabelFactory.create_label(
            self,
            text=task.created_date,
            bg_color=self._accent_bg,
            text_color=self._accent_text,
            alignment=Qt.AlignCenter,
            min_size=(100, 0),
            padding="4px 8px",
            border_radius=4,
        )

    DEADLINE_DATE_BG = (130, 40, 40, 0.85)

    def _on_title_clicked(self, task):
        """Клик по названию — уведомление с описанием.

        Вход: task — PlannerTask.
        Роль: общее поведение для обоих окон. Наследники могут
              переопределить, если нужно другое действие.
        """
        from ui.windows.message_dialog import NotificationDialog
        text = task.description or "Подробное описание отсутствует."
        NotificationDialog.notify(
            self,
            text,
            bg_color=self.bg_color,
            title_text=task.title,
        )

    # ---------- Обработчики ----------

    def _build_specifications(self, task):
        """Колонка спецификаций.

        DEADLINE — дата дедлайна на красном фоне.
        RECURRING (генератор) — next_generation_date на голубом фоне.
        Остальные — пустой прозрачный лейбл для выравнивания.
        """
        # Генератор регулярной задачи — дата следующей генерации.
        if task.is_generator():
            next_date = task.next_generation_date or "—"
            return LabelFactory.create_label(
                self, text=next_date, bg_color=(80, 160, 220, 0.85),
                text_color="#ffffff", alignment=Qt.AlignCenter,
                min_size=(100, 0), padding="4px 8px", border_radius=4,
            )

        # Дедлайн — дата дедлайна на красном фоне.
        if task.priority == TaskPriority.DEADLINE:
            dl = task.get_deadline_datetime()
            text = dl.strftime("%d.%m.%Y %H:%M") if dl else "—"
            return LabelFactory.create_label(
                self, text=text, bg_color=self.DEADLINE_DATE_BG,
                text_color="#ffffff", alignment=Qt.AlignCenter,
                min_size=(100, 0), padding="4px 8px", border_radius=4,
            )
        if task.is_event():
            return LabelFactory.create_label(
                self, text=task.event_date or "—",
                bg_color=(60, 160, 80, 0.85),
                text_color="#ffffff",
                alignment=Qt.AlignCenter,
                min_size=(100, 0),
                padding="4px 8px",
                border_radius=4,
            )
        # Остальные — пустой лейбл для выравнивания колонок.
        return LabelFactory.create_label(
            self, text="", bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4", alignment=Qt.AlignCenter,
            min_size=(100, 0),
        )

    # ---------- Очистка / закрытие ----------

    def cleanup(self):
        """Очистка состояния при закрытии. Наследник может переопределить."""
        pass

    def closeEvent(self, event):
        """Останавливает таймер и завершает работу окна.

        REPLACE: добавлен debug-лог при закрытии.
        """
        if self.logger is not None:
            self.logger.debug(
                f"{type(self).__name__}: closeEvent получен"
            )
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.cleanup()
        event.accept()