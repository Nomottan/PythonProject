from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal

from ui.factories.factories import ButtonFactory, BaseWidgetFactory


class PlannerQuickView(QWidget):
    """Виджет с 6 кнопками задач.

    Назначение:
        Показать до 6 активных задач. Слоты распределяет
        PlannerQuickViewController; виджет только отображает.

    Роль в программе:
        Встраивается в MainWindow над центральными кнопками.

    Сигналы:
        task_clicked(int) — пользователь кликнул по слоту. Аргумент — task_id
                            задачи, показанной в данный момент в этом слоте.
                            Для пустого слота сигнал не испускается.
    """

    task_clicked = Signal(object)

    # Количество слотов.
    SLOT_COUNT = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("planner_quick_view_root")
        self.setStyleSheet("""
                    QWidget#planner_quick_view_root {
                        background-color: rgba(30, 30, 35, 0.9);
                        border-radius: 6px;
                    }
                """)

        self.setMaximumWidth(400)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(6, 6, 6, 6)
        self._layout.setSpacing(4)

        # _slot_task_ids[i] — текущий task_id в слоте i (None, если пусто).
        # Нужен, чтобы отдать правильный id при клике по карусели,
        # когда содержимое слота меняется.
        self._slot_task_ids: list = [None] * self.SLOT_COUNT

        # Кнопки-слоты.
        self._buttons = []
        for i in range(self.SLOT_COUNT):
            btn = ButtonFactory.create_button(
                self,
                text="",
                bg_color=(50, 50, 50, 0.85),
                text_color="#d4d4d4",
                alignment="left",
                padding="6px 12px",
                border_radius=4,
                font_size=11,
                cursor_shape=Qt.PointingHandCursor,
            )
            # Замыкаем индекс через параметр по умолчанию.
            btn.clicked.connect(lambda checked=False, idx=i: self._on_button_clicked(idx))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.setVisible(False)
            self._layout.addWidget(btn)
            self._buttons.append(btn)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ---------- Публичный API ----------

    def set_slots(self, slots: list) -> None:
        """Заполняет все 6 слотов.

        Вход: slots — список длиной SLOT_COUNT. Элемент:
            None — пустой слот (кнопка скрыта).
            (task, color) — заполненный слот; task — PlannerTask,
                            color — кортеж (r, g, b, a).

        Роль: единая точка перерисовки слотов. Вызывается контроллером.
        """
        for i in range(self.SLOT_COUNT):
            slot = slots[i] if i < len(slots) else None
            btn = self._buttons[i]
            if slot is None:
                btn.setVisible(False)
                self._slot_task_ids[i] = None
                continue
            task, color = slot
            self._apply_slot(btn, i, task, color)

    def update_slot(self, index: int, task, color) -> None:
        """Обновляет содержимое одного слота (используется каруселью).

        Вход: index — индекс слота; task — PlannerTask; color — кортеж.
        Роль: карусель крутит задачи ОДНОГО приоритета — значит, цвет
              полосы не меняется. Переустанавливать QSS не нужно: каждое
              setStyleSheet ломает текущее псевдосостояние (:hover,
              :pressed) и перерисовывает border-left с потерей яркости.
              Меняем только текст и task_id.
        """
        if 0 <= index < self.SLOT_COUNT:
            btn = self._buttons[index]
            btn.setText(task.title)
            btn.setToolTip("")
            self._slot_task_ids[index] = task.task_id

    def show_empty(self) -> None:
        """Показать «Нет активных задач» в верхнем слоте.

        Роль: состояние, когда у сервиса нет активных задач. Остальные
              слоты скрыты, кнопка неактивна.
        """
        for i in range(self.SLOT_COUNT):
            self._buttons[i].setVisible(False)
            self._slot_task_ids[i] = None
        top = self._buttons[0]
        top.setText("Нет активных задач")
        top.setStyleSheet("")
        top.setEnabled(False)
        top.setVisible(True)

    # ---------- Внутренние ----------

    SLOT_BG = (78, 78, 83, 0.95)  # основной
    SLOT_BG_HOVER = (98, 98, 103, 0.95)  # при наведении
    SLOT_BG_PRESSED = (60, 60, 65, 0.95)  # при нажатии
    SLOT_TEXT = "#e0e0e0"

    def _apply_slot(self, btn, index: int, task, color) -> None:
        """Применяет задачу и цвет-индикатор к кнопке-слоту.

        Вход: btn — кнопка слота; index — его индекс; task — PlannerTask;
              color — кортеж (r, g, b, a) — цвет полосы слева.

        Роль: общая точка для set_slots и update_slot. Кастомный QSS:
              единый светлый фон + цветная полоса слева по приоритету.
              ButtonFactory здесь не используется — у слота свой дизайн.
        """
        stripe_color = BaseWidgetFactory.color_to_str(color)
        bg = BaseWidgetFactory.color_to_str(self.SLOT_BG)
        bg_hover = BaseWidgetFactory.color_to_str(self.SLOT_BG_HOVER)
        bg_pressed = BaseWidgetFactory.color_to_str(self.SLOT_BG_PRESSED)

        btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {self.SLOT_TEXT};
                    text-align: left;
                    padding: 6px 12px 6px 14px;
                    border: none;
                    border-left: 4px solid {stripe_color};
                    border-radius: 4px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {bg_hover};
                }}
                QPushButton:pressed {{
                    background-color: {bg_pressed};
                }}
            """)
        btn.setText(task.title)
        #btn.setToolTip(task.title)
        btn.setEnabled(True)
        btn.setVisible(True)
        self._slot_task_ids[index] = task.task_id

    def _on_button_clicked(self, index: int) -> None:
        """Обработчик клика по слоту.

        Вход: index — индекс слота.
        Роль: если слот пуст — ничего не делаем. Иначе испускаем
              task_clicked с текущим task_id.
        """
        task_id = self._slot_task_ids[index]
        if task_id is None:
            return
        self.task_clicked.emit(task_id)