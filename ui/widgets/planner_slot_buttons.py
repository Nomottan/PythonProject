"""
Виджеты-кнопки планировщика.

Содержит приватный предок _BaseTaskButton и четырёх его
наследников — кнопки-слоты для мини-планировщика:
    DeadlineTaskButton — дедлайн-задача с прогрессбаром.
    InstanceTaskButton — экземпляр регулярной задачи.
    EventTaskButton    — событие с фиксированной датой.
    SimpleTaskButton   — обычная задача с полосой цвета приоритета.

Поля ввода дедлайна вынесены в отдельный модуль:
    ui.widgets.planner_dl_fields_widget.DeadlineFieldsWidget

Роль в программе:
    Используются в PlannerQuickView через CompositeWidgetFactory.
    Логика не зависит от сервисов — только отображение задач и
    обработка кликов.

QSS-цвета собираются через ui.styles.ColorCalculator.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar,
)

from ui.styles.colors import ColorCalculator


class _BaseTaskButton(QWidget):
    """Приватный предок для кнопок-слотов планировщика.

    Назначение:
        Содержит всё, что общее у DeadlineTaskButton,
        InstanceTaskButton и SimpleTaskButton: layout с title_label,
        цвета фона, mouse-логику, базовый QSS.

    Роль в программе:
        Не используется напрямую. Наследники задают свой
        DEFAULT_STRIPE, при необходимости расширяют layout через
        _extend_layout и переопределяют set_task.

    Атрибуты классов:
        clicked — сигнал, испускается при клике по виджету.
        BG, BG_HOVER, BG_PRESSED — цвета фона в трёх состояниях.
        TEXT_COLOR — цвет текста (HEX).
        DEFAULT_STRIPE — цвет полосы слева по умолчанию.
    """

    clicked = Signal()

    BG = (78, 78, 83, 0.95)
    BG_HOVER = (98, 98, 103, 0.95)
    BG_PRESSED = (60, 60, 65, 0.95)
    TEXT_COLOR = "#e0e0e0"
    DEFAULT_STRIPE = (80, 160, 220, 1.0)

    def __init__(self, parent=None, stripe_color=None):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            stripe_color — цвет полосы слева. None → берётся
                           self.DEFAULT_STRIPE.

        Роль: настраивает флаги, собирает базовый layout,
              вызывает _extend_layout для наследников, инициализирует
              состояние мыши.
        """
        super().__init__(parent)
        # WA_StyledBackground нужен, чтобы QSS background-color
        # работал на чистом QWidget.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        self._stripe_color = (
            stripe_color if stripe_color is not None
            else self.DEFAULT_STRIPE
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 4, 8, 4)
        self._layout.setSpacing(2)

        self._title_label = QLabel()
        self._title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._title_label.setStyleSheet(
            f"color: {self.TEXT_COLOR}; font-size: 11px; background: transparent;"
        )
        self._title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._layout.addWidget(self._title_label)

        self._extend_layout(self._layout)

        self._hovered = False
        self._pressed = False
        self._apply_bg(self.BG)

    # ---------- Точки расширения для наследников ----------

    def _extend_layout(self, layout) -> None:
        """Хук: наследники добавляют свои элементы в layout.

        Вход: layout — QVBoxLayout, уже содержит title_label.
        Роль: по умолчанию ничего не делает.
        """
        pass

    # ---------- Публичный API ----------

    def set_task(self, task) -> None:
        """Устанавливает название задачи.

        Вход: task — PlannerTask.
        Роль: базовое поведение — просто текст.
        """
        self._title_label.setText(task.title)

    # ---------- Внутренние ----------

    def _apply_bg(self, bg) -> None:
        """Устанавливает фон виджета через QSS.

        Вход: bg — цвет фона (кортеж).
        Роль: единая точка обновления QSS. Использует
              type(self).__name__ как селектор — так стиль не
              протекает на дочерние виджеты.

        REPLACE: BaseWidgetFactory.color_to_str заменён на
        ColorCalculator.to_str — убрали лишний слой.
        """
        cls_name = type(self).__name__
        bg_str = ColorCalculator.to_str(bg)
        stripe_str = ColorCalculator.to_str(self._stripe_color)
        self.setStyleSheet(f"""
            {cls_name} {{
                background-color: {bg_str};
                border: none;
                border-left: 4px solid {stripe_str};
                border-radius: 4px;
            }}
        """)

    # ---------- Обработка мыши ----------

    def mousePressEvent(self, event):
        """Обработка нажатия левой кнопкой мыши."""
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._apply_bg(self.BG_PRESSED)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Обработка отпускания левой кнопки мыши."""
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self._apply_bg(self.BG_HOVER if self._hovered else self.BG)
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        """Курсор вошёл в виджет."""
        self._hovered = True
        if not self._pressed:
            self._apply_bg(self.BG_HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Курсор покинул виджет."""
        self._hovered = False
        if not self._pressed:
            self._apply_bg(self.BG)
        super().leaveEvent(event)


class DeadlineTaskButton(_BaseTaskButton):
    """Кнопка задачи с дедлайном: полоса слева + название + прогрессбар.

    Назначение:
        Отдельный вид кнопки-слота для дедлайн-задач.

    Роль в программе:
        Используется PlannerQuickView для задач с
        priority == DEADLINE.

    Отличия от базы:
        DEFAULT_STRIPE — оранжевый.
        В layout добавляется QProgressBar.
        set_task переопределён — вызывает update_progress.
    """

    DEFAULT_STRIPE = (220, 130, 60, 1.0)

    PROGRESS_CHUNK_NORMAL = (100, 180, 120, 0.9)
    PROGRESS_CHUNK_RED = (200, 70, 70, 0.9)

    def _extend_layout(self, layout) -> None:
        """Добавляет прогрессбар под title_label."""
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._progress_bar)

    def set_task(self, task) -> None:
        """Устанавливает название и пересчитывает прогресс."""
        super().set_task(task)
        self.update_progress(task)

    def update_progress(self, task) -> None:
        """Обновляет прогресс-бар.

        Вход: task — PlannerTask.

        Роль: progress = min(100, elapsed / total * 100).
              total <= 0 → progress = 100.
              progress >= 90 → красный chunk, иначе зелёный.

        REPLACE: BaseWidgetFactory.color_to_str заменён на
        ColorCalculator.to_str.
        """
        from datetime import datetime
        created = task.get_created_datetime()
        deadline = task.get_deadline_datetime()
        if created is None or deadline is None:
            self._progress_bar.setValue(0)
            return

        total = (deadline - created).total_seconds()
        if total <= 0:
            progress = 100
        else:
            elapsed = (datetime.now() - created).total_seconds()
            progress = max(0, min(100, int(elapsed / total * 100)))

        self._progress_bar.setValue(progress)

        chunk = (ColorCalculator.to_str(self.PROGRESS_CHUNK_RED)
                 if progress >= 90
                 else ColorCalculator.to_str(self.PROGRESS_CHUNK_NORMAL))
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(0, 0, 0, 0.3);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk};
                border-radius: 2px;
            }}
        """)


class InstanceTaskButton(_BaseTaskButton):
    """Кнопка экземпляра регулярной задачи.

    Назначение:
        Отдельный вид кнопки-слота для экземпляров, порождённых
        генератором. Отличается от обычной QPushButton цветом
        полосы слева (голубая по умолчанию).

    Роль в программе:
        Используется PlannerQuickView для
        task.is_recurring_instance().
    """
    pass


class EventTaskButton(_BaseTaskButton):
    """Кнопка-слот события с фиксированной датой.

    Назначение:
        Отдельный вид кнопки-слота для событий — задач с
        task_type == EVENT. Жёлтая полоса, чтобы событие
        визуально выделялось.

    Роль в программе:
        Используется PlannerQuickView для task.is_event().
    """
    DEFAULT_STRIPE = (240, 240, 40, 1.0)


class SimpleTaskButton(_BaseTaskButton):
    """Кнопка-слот для обычной задачи.

    Назначение:
        Заменяет обычную QPushButton в PlannerQuickView для
        приоритетов LOW/MEDIUM/HIGH. Единый предок
        _BaseTaskButton — общая mouse-логика и QSS.

    Роль в программе:
        Используется PlannerQuickView для обычных приоритетов.
        Цвет полосы задаётся аргументом stripe_color.
    """
    pass