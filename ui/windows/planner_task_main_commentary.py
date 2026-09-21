"""
Диалог детального просмотра задачи из мини-планировщика.

Показывает заголовок, инфо-строку и описание. Позволяет:
    - отметить задачу выполненной (архивация как COMPLETED),
    - перейти в режим редактирования описания,
    - сохранить новое описание,
    - закрыть диалог без сохранения.
"""

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory, BaseWidgetFactory,
)
from models.planner_task import PlannerTask, TaskStatus


class PlannerTaskMainCommentary(QDialog):
    """Диалог детального просмотра задачи.

    Назначение:
        Быстрый доступ к задаче из мини-планировщика: посмотреть
        описание, отметить выполненной, оставить комментарий.

    Роль в программе:
        Открывается PlannerQuickViewController'ом по клику на слот.
        Модальный на уровне приложения, без системной рамки.
    """

    def __init__(self, parent, task: PlannerTask, planner_service):
        """Конструктор.

        Вход:
            parent — родитель (MainWindow).
            task — PlannerTask для отображения.
            planner_service — PlannerService (для archive_task и update_task).
        """
        super().__init__(parent)
        self._task = task
        self._service = planner_service
        self._edit_mode = False

        # --- Флаги окна ---
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # --- Цвета ---
        bg_color = (70, 80, 90, 0.95)
        border_color = self._calc_border_color(bg_color)

        # --- Центральный виджет ---
        central = QWidget()
        central.setObjectName("commentary_dialog_root")
        bg_c = BaseWidgetFactory.color_to_str(bg_color)
        border_c = BaseWidgetFactory.color_to_str(border_color)
        central.setStyleSheet(f"""
            QWidget#commentary_dialog_root {{
                background-color: {bg_c};
                border: 2px solid {border_c};
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # --- Заголовок ---
        title_lbl = LabelFactory.create_label(
            self,
            text=f"Задача: {task.title}",
            bg_color=(0, 0, 0, 0),
            text_color="#ffffff",
            alignment=Qt.AlignCenter,
            word_wrap=True,
            font_size=14,
            font_weight="bold",
        )
        layout.addWidget(title_lbl)

        # --- Инфо-строка ---
        info_text = (
            f"Создано: {task.created_date}   |   "
            f"Приоритет: {task.priority.display_name}   |   "
            f"Статус: {task.status.display_name}"
        )
        info_lbl = LabelFactory.create_label(
            self,
            text=info_text,
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            alignment=Qt.AlignCenter,
            font_size=11,
        )
        layout.addWidget(info_lbl)

        # --- Описание: два взаимозаменяемых виджета ---
        # Режим просмотра — QLabel.
        self._desc_label = LabelFactory.create_label(
            self,
            text=task.description or "Нет описания",
            bg_color=(60, 70, 80, 0.9),
            text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignTop,
            word_wrap=True,
            padding="8px",
            border_radius=4,
        )
        self._desc_label.setMinimumHeight(120)
        layout.addWidget(self._desc_label)

        # Режим редактирования — QTextEdit, изначально скрыт.
        self._desc_edit = InputWidgetFactory.create_text_edit(
            self,
            text=task.description,
            bg_color=(60, 70, 80, 0.9),
            border="1px solid #4a5566",
            border_radius=4,
            padding="8px",
            font_size=11,
        )
        self._desc_edit.setMinimumHeight(120)
        self._desc_edit.setVisible(False)
        layout.addWidget(self._desc_edit)

        # --- Кнопки ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_complete = ButtonFactory.create_button(
            self, "Выполнено", bg_color=(70, 150, 90, 0.85),
            padding="6px 14px", border_radius=4,
        )
        self._btn_complete.clicked.connect(self._on_complete)
        btn_layout.addWidget(self._btn_complete)

        self._btn_comment = ButtonFactory.create_button(
            self, "Комментарий", bg_color=(70, 100, 150, 0.85),
            padding="6px 14px", border_radius=4,
        )
        self._btn_comment.clicked.connect(self._on_comment)
        btn_layout.addWidget(self._btn_comment)

        self._btn_save = ButtonFactory.create_button(
            self, "Сохранить", bg_color=(70, 150, 90, 0.85),
            padding="6px 14px", border_radius=4,
        )
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save.setEnabled(False)  # изначально нечего сохранять
        btn_layout.addWidget(self._btn_save)

        self._btn_close = ButtonFactory.create_button(
            self, "Закрыть", bg_color=(120, 70, 70, 0.85),
            padding="6px 14px", border_radius=4,
        )
        self._btn_close.clicked.connect(self._on_close)
        btn_layout.addWidget(self._btn_close)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # --- Внешний layout ---
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(central)

        self.setMinimumSize(400, 300)

    # ---------- Вспомогательные ----------

    @staticmethod
    def _calc_border_color(bg_color: tuple) -> tuple:
        """Обводка диалога — та же формула, что в MessageDialog.

        Вход: bg_color — кортеж (r, g, b, a) (или без a).
        Выход: кортеж (r, g, b, 0.9).
        """
        r, g, b = bg_color[:3]
        avg = (r + g + b) // 3

        def clamp(v):
            return max(0, min(255, int(v)))

        if avg <= 128:
            return (clamp(r + 40), clamp(g + 20), clamp(b + 20), 0.9)
        return (clamp(r - 20), clamp(g - 40), clamp(b - 40), 0.9)

    # ---------- Слоты ----------

    def _on_complete(self) -> None:
        """«Выполнено» — архивирует задачу как COMPLETED и закрывает диалог."""
        self._service.archive_task(self._task.task_id, TaskStatus.COMPLETED)
        self.accept()

    def _on_comment(self) -> None:
        """«Комментарий» — переходит в режим редактирования описания."""
        self._edit_mode = True
        self._desc_label.setVisible(False)
        self._desc_edit.setPlainText(self._task.description)
        self._desc_edit.setVisible(True)
        self._btn_comment.setEnabled(False)
        self._btn_save.setEnabled(True)

    def _on_save(self) -> None:
        """«Сохранить» — сохраняет описание и возвращается в режим просмотра."""
        new_desc = self._desc_edit.toPlainText().strip()
        self._task.description = new_desc
        # update_task принимает title, description, priority.
        # title и priority не меняются.
        self._service.update_task(
            task_id=self._task.task_id,
            title=self._task.title,
            description=new_desc,
            priority=self._task.priority,
        )
        # Возврат в режим просмотра.
        self._edit_mode = False
        self._desc_label.setText(new_desc or "Нет описания")
        self._desc_edit.setVisible(False)
        self._desc_label.setVisible(True)
        self._btn_comment.setEnabled(True)
        self._btn_save.setEnabled(False)

    def _on_close(self) -> None:
        """«Закрыть» — закрывает диалог без сохранения изменений."""
        self.reject()