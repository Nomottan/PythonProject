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
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QLayout,
    QDialog
)
from PySide6.QtCore import Qt, QTimer

from ui.factories.factories import (
    WindowFactory, ButtonFactory, LabelFactory, ListWidgetFactory,
    BaseWidgetFactory, FilterFactory,
)
from models.planner_task import TaskPriority, ThemeKey
from ui.styles import ColorCalculator


class _BasePlannerListWindow(QMainWindow):
    """Базовое окно со списком задач.

    Общая часть для PlannerWindow и PlannerArchiveWindow.

    Наследники определяют:
        LOGGER_SOURCE / LOGGER_DOMAIN — идентификация для LoggerV2.
        TASK_TYPE_COLUMNS — список колонок.
        _get_tasks() — источник данных.
        При необходимости расширяют COLUMN_BUILDERS.
    """

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None

    # Интервал автообновления — 5 минут.
    RELOAD_INTERVAL_MS = 5 * 60 * 1000

    # Сдвиг каналов для акцентного фона (название задачи, дата).
    ACCENT_SHIFT = 25
    ACCENT_ALPHA = 0.7

    # Нейтральный цвет для неизвестных значений.
    NEUTRAL_COLOR = (120, 120, 120, 0.85)
    DEADLINE_DATE_BG = (130, 40, 40, 0.85)

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

    # Базовые строители колонок. Наследники могут дополнить.
    COLUMN_BUILDERS = {
        "title": "_build_title",
        "checklist": "_build_checklist",
        "theme": "_build_theme",
        "priority": "_build_priority",
        "status": "_build_status",
        "date": "_build_date",
        "specifications": "_build_specifications",
    }
    EDITABLE = True

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, title="", bg_color=(64, 48, 66, 0.8),
                 log_manager_v2=None, main_config=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок окна.
            bg_color — цвет фона. Передаётся в WindowFactory и в скролл.
            log_manager_v2 — LogManagerV2 или None.
            main_config — MainConfig или None.
        """
        super().__init__(parent)

        # ---------- СОСТОЯНИЕ ----------
        self.bg_color = bg_color
        self.main_config = main_config
        self.service_window = self
        self.filter_panel = None
        self._empty_label = None
        self._theme_picker = None

        # Логгер V2
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None and self.LOGGER_SOURCE is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )

        # Акцентный цвет для названий задач и даты
        self._accent_bg = self._calc_accent_color(bg_color)
        self._accent_text = BaseWidgetFactory.calc_text_color(self._accent_bg)

        # ---------- МАКЕТ ----------
        main_layout = WindowFactory.setup_child_window(
            self, title, bg_color=self.bg_color,
        )
        self._main_layout = main_layout

        # Прокручиваемая область задач
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
        self.tasks_layout.addStretch() # Растяжка внизу

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Панель фильтров
        field_defs = self._get_filter_field_defs()
        if field_defs:
            self.filter_panel = FilterFactory.create_filter_panel(
                self,
                field_defs=field_defs,
                get_source=lambda: self._get_tasks(),
                bg_color=self.bg_color,
            )
            self._main_layout.insertWidget(1, self.filter_panel)
            self.filter_panel.filtered_changed.connect(self._reload_tasks)

        # ---------- ТАЙМЕР ----------
        self._timer = QTimer(self)
        self._timer.setInterval(self.RELOAD_INTERVAL_MS)
        self._timer.timeout.connect(self._reload_tasks)
        self._timer.start()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ИСТОЧНИКИ И ОТРИСОВКА
    # ============================================================

    def _get_tasks(self):
        """Возвращает список задач для отрисовки. Наследник реализует."""
        raise NotImplementedError

    def _get_filter_field_defs(self) -> list:
        """Возвращает список FieldDef для панели фильтров."""
        return []

    def _reload_tasks(self, filtered=None):
        """Перерисовывает список задач."""
        # Очистка строк (кроме растяжки).
        while self.tasks_layout.count() > 1:
            item = self.tasks_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._empty_label = None

        # Источник: аргумент → панель → наследник.
        if filtered is not None:
            source = filtered
        elif self.filter_panel is not None:
            source = self.filter_panel.get_filtered()
        else:
            source = self._get_tasks()

        if not source:
            self._empty_label = LabelFactory.create_label(
                self,
                text="Нет задач, удовлетворяющих фильтру",
                bg_color=(0, 0, 0, 0),
                alignment=Qt.AlignCenter,
                word_wrap=True,
            )
            self.tasks_layout.insertWidget(
                self.tasks_layout.count() - 1, self._empty_label,
            )
            return

        for task in source:
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
                if col_id == "title":
                    layout.addWidget(widget, 1)
                else:
                    layout.addWidget(widget)
        layout.addStretch(1)
        return row

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: БИЛДЕРЫ КОЛОНОК
    # ============================================================

    @classmethod
    def _calc_accent_color(cls, bg_color) -> tuple:
        """Вычисляет акцентный цвет от фона окна."""
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

    def _build_title(self, task):
        """Название задачи — кликабельная кнопка."""
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
        btn.setFixedWidth(150)
        btn.setToolTip(task.title)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        btn.clicked.connect(
            lambda checked=False, t=task: self._on_title_clicked(t)
        )
        return btn

    def _on_title_clicked(self, task):
        """Клик по названию — уведомление с описанием."""
        from ui.windows.message_dialog import NotificationDialog
        text = task.description or "Подробное описание отсутствует."
        NotificationDialog.notify(
            self,
            text,
            bg_color=self.bg_color,
            title_text=task.title,
        )

    def _build_checklist(self, task):
        """Плашка чек-листа — «Чек-лист» или «Без чек-листа»."""
        if not task.checklist_required:
            lbl = LabelFactory.create_label(
                self,
                "Без чек-листа",
                bg_color=self.NEUTRAL_COLOR,
                font_weight="bold",
            )
            lbl.setFixedWidth(100)
            return lbl

        btn = ButtonFactory.create_button(
            self,
            "Чек-лист",
            bg_color=ColorCalculator.derive(
                self._accent_bg,
                r_fn=lambda r: r + 10,
                g_fn=lambda g: g + 15,
                b_fn=lambda b: b + 20,
                alpha=0.85,
            ),
            padding="4px 8px",
            border_radius=4,
        )
        btn.setFixedWidth(100)
        btn.clicked.connect(
            lambda checked=False, t=task: self._on_open_checklist(t)
        )
        return btn

    def _on_open_checklist(self, task) -> None:
        """Открывает модальный диалог чек-листа."""
        from ui.windows.planner_checklist_dialogs import ChecklistDialog

        mode = "edit" if self.EDITABLE else "view"
        dialog = ChecklistDialog(
            self,
            task=task,
            bg_color=self.bg_color,
            log_manager_v2=self.log_manager_v2,
            mode=mode,
        )
        dialog.setWindowModality(Qt.WindowModal)
        if dialog.exec() == QDialog.Accepted and self.EDITABLE:
            result = dialog.get_result()
            if result is not None:
                self.service.update_checklist(task.task_id, result)
        self._reload_tasks()

    def _resolve_theme_name(self, task) -> str:
        """Возвращает эффективное имя темы задачи.

        Fallback на ThemeKey.BLACK при невалидном task.theme. Если
        main_config is None или planner_themes не dict — возвращает
        дефолтное имя.
        """
        try:
            key = ThemeKey(task.theme)
        except (ValueError, TypeError):
            key = ThemeKey.BLACK

        raw = self.main_config.get("planner_themes", {}) if self.main_config is not None else {}
        if not isinstance(raw, dict):
            raw = {}

        return ThemeKey.resolve_effective_name(key, raw)

    def _build_theme(self, task):
        """Строит плашку темы задачи."""
        try:
            theme_key = ThemeKey(task.theme)
        except (ValueError, TypeError):
            theme_key = ThemeKey.BLACK

        name = self._resolve_theme_name(task)

        if self.EDITABLE:
            btn = ButtonFactory.create_button(
                self, text=name, bg_color=theme_key.color,
                fixed_size=(120, 30), padding="4px 8px", border_radius=4,
            )
            btn.clicked.connect(
                lambda checked=False, t=task: self._on_theme_clicked(t)
            )
            return btn

        lbl = LabelFactory.create_label(
            self, text=name, bg_color=theme_key.color, font_weight="bold",
        )
        lbl.setFixedWidth(120)
        return lbl

    def _build_priority(self, task):
        """Приоритет задачи — цветной лейбл."""
        priority = task.priority.display_name
        color = self.PRIORITY_COLORS.get(priority, self.NEUTRAL_COLOR)
        return LabelFactory.create_label(
            self, text=priority, bg_color=color,
            font_weight="bold", min_size=(100, 0),
        )

    def _on_theme_clicked(self, task) -> None:
        """Открывает пикер темы при клике на плашку."""
        if self._theme_picker is not None:
            try:
                self._theme_picker.close()
            except RuntimeError:
                pass

        from ui.windows.planner_themes_dialog import PlannerThemePickerDialog
        try:
            current_theme = ThemeKey(task.theme)
        except (ValueError, TypeError):
            current_theme = ThemeKey.BLACK

        self._theme_picker = PlannerThemePickerDialog(
            self, current_theme, self.main_config, self.log_manager_v2,
        )
        self._theme_picker.destroyed.connect(
            lambda: setattr(self, "_theme_picker", None)
        )
        self._theme_picker.theme_key_selected.connect(
            lambda val: self._save_theme(task.task_id, val)
        )
        self._theme_picker.show()

    def _save_theme(self, task_id, theme_val) -> None:
        """Сохраняет новую тему и перерисовывает список."""
        if self.logger:
            self.logger.debug(
                f"Планировщик: смена темы task_id={task_id}, theme={theme_val!r}"
            )
        self.service.set_theme(task_id, theme_val)
        self._reload_tasks()

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
        lbl = LabelFactory.create_label(
            self,
            text=task.created_date,
            bg_color=ColorCalculator.derive(
                self._accent_bg,
                r_fn=lambda r: r - 40,
                g_fn=lambda g: g - 30,
                b_fn=lambda b: b - 20,
                alpha=self.ACCENT_ALPHA,
            ),
            text_color=self._accent_text,
            alignment=Qt.AlignCenter,
            padding="4px 8px",
            border_radius=4,
        )
        lbl.setFixedWidth(100)
        return lbl

    def _build_specifications(self, task):
        """Колонка спецификаций."""
        if task.is_generator():
            next_date = task.next_generation_date or "—"
            bg = (80, 160, 220, 0.85)
            return LabelFactory.create_label(
                self, text=next_date, bg_color=bg,
                text_color=ColorCalculator.text_for(bg), alignment=Qt.AlignCenter,
                min_size=(100, 0), padding="4px 8px", border_radius=4,
            )

        if task.priority == TaskPriority.DEADLINE:
            dl = task.get_deadline_datetime()
            text = dl.strftime("%d.%m.%Y %H:%M") if dl else "—"
            bg = self.DEADLINE_DATE_BG
            return LabelFactory.create_label(
                self, text=text, bg_color=bg,
                text_color=ColorCalculator.text_for(bg), alignment=Qt.AlignCenter,
                min_size=(100, 0), padding="4px 8px", border_radius=4,
            )

        if task.is_event():
            bg = (60, 160, 80, 0.85)
            return LabelFactory.create_label(
                self, text=task.event_date or "—",
                bg_color=bg,
                text_color=ColorCalculator.text_for(bg),
                alignment=Qt.AlignCenter,
                min_size=(100, 0),
                padding="4px 8px",
                border_radius=4,
            )

        return LabelFactory.create_label(
            self, text="", bg_color=(0, 0, 0, 0),
            alignment=Qt.AlignCenter, min_size=(100, 0),
        )

    # ============================================================
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def cleanup(self):
        """Очистка состояния при закрытии. Наследник может переопределить."""
        pass

    def closeEvent(self, event):
        """Останавливает таймер и завершает работу окна."""
        if self.logger is not None:
            self.logger.debug(
                f"{type(self).__name__}: closeEvent получен"
            )
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.cleanup()
        event.accept()