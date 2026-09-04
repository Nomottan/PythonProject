from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit,
    QScrollArea, QSizePolicy, QCheckBox, QLineEdit, QMessageBox,
    QGridLayout
)
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory, ListWidgetFactory,
    LayoutFactory, WindowFactory, ProgressFactory
)
from ui.factories.window_factories import ExtendedWindowFactory
from ui.widgets.deadline_progress_widget import DeadlineProgressWidget
from models.planner_models import PlannerTask, RepeatRule, TaskFilter, TaskSorter
from services.planner_services import PlannerFacade
from utils.datetime_utils import DateTimeUtils

class PlannerWindow(QMainWindow):
    """Окно ежедневника (Planner)."""

    def __init__(self, parent=None, facade: PlannerFacade = None):
        super().__init__(parent)
        self.main_window = parent
        self.facade = facade
        self.archive_window = None

        if facade:
            facade.initialize()

        # Зелёная (нефритовая) тема
        main_layout = WindowFactory.setup_child_window(
            self, "Ежедневник",
            bg_color=(0, 95, 80, 0.95),
            close_callback=self.close,
            close_button=False  # убираем стандартный крестик, роль закрытия у кнопки даты
        )

        # Верхняя панель: слева "Архив", справа кнопка даты (закрывает)
        self.archive_btn = ButtonFactory.create_button(
            self, "Архив", (80, 40, 40),
            padding="6px 12px",
            fixed_size=(120, 30)
        )
        self.archive_btn.clicked.connect(self._open_archive)

        self.date_btn = ButtonFactory.create_datetime_button(self, self.close)
        self.date_btn.setText(DateTimeUtils.get_current_datetime_text())

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.archive_btn)
        top_layout.addStretch()
        top_layout.addWidget(self.date_btn)
        main_layout.addLayout(top_layout)

        self.filter_panel = FilterSortPanel(self, mode="planner")
        self.filter_panel.changed.connect(self._render_tasks)
        main_layout.addWidget(self.filter_panel)

        # Область списка задач (заглушка — пустой контейнер)
        scroll, self.tasks_widget, self.tasks_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=5
        )
        # Делаем контентный виджет темнее, чтобы выделить зону списка
        self.tasks_widget.setStyleSheet("""
                    QWidget {
                        background-color: rgba(0, 0, 0, 0.35);
                        border-radius: 8px;
                    }
                """)
        main_layout.addWidget(scroll)

        # Кнопка "Добавить задачу" внизу
        self.add_task_btn = ButtonFactory.create_button(
            self, "Добавить задачу", (80, 140, 110, 0.9),
            padding="8px 16px",
            fixed_size=(180, 35)
        )
        self.add_task_btn.clicked.connect(self._add_task)
        LayoutFactory.add_centered_widget(main_layout, self.add_task_btn)

        self._render_tasks()



        # Таймер обновления времени на кнопке
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._update_datetime)
        self.update_timer.start(60000)

        # Заглушка для отображения списка
        self._render_tasks()

        if facade:
            facade.tasks_changed.connect(self._render_tasks)
            #facade.archive_changed.connect(self._render_archive)
            facade.instances_changed.connect(self._render_tasks)

    # ---------- Заглушки ----------
    def _open_archive(self):
        """Открыть окно архива."""
        if self.archive_window is None or not self.archive_window.isVisible():
            self.archive_window = ArchiveWindow(self)
            WindowFactory.show_child_window(self, self.archive_window)
        else:
            self.archive_window.raise_()
            self.archive_window.activateWindow()

    def _render_tasks(self):
        """Перестраивает список задач из фасада."""
        while self.tasks_layout.count():
            item = self.tasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.facade:
            return

        templates = self.facade.get_templates()
        if not templates:
            placeholder = LabelFactory.create_label(
                self.tasks_widget, "Список задач пуст",
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4"
            )
            self.tasks_layout.addWidget(placeholder)
            return

        # Применяем фильтр и сортировку
        try:
            filtered = self.filter_panel.get_filter().apply(templates)
            sorted_tasks = self.filter_panel.get_sorter().sort(filtered)
        except Exception:
            sorted_tasks = templates

        if not sorted_tasks:
            placeholder = LabelFactory.create_label(
                self.tasks_widget, "Нет задач, удовлетворяющих фильтру",
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4"
            )
            self.tasks_layout.addWidget(placeholder)
            return

        for task in sorted_tasks:
            row = self._create_task_row(task)
            self.tasks_layout.addWidget(row)

    def _create_task_row(self, task):
        """Создаёт виджет строки для одной задачи."""
        row_widget = QWidget()
        row_widget.setObjectName("task_row")
        row_widget.setStyleSheet("QWidget#task_row { background: transparent; border-radius: 0px; }")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # Основной элемент: прогресс-бар, кнопка с лычкой или просто кнопка
        if task.deadline:
            # Для задач с конкретным дедлайном
            main_widget = DeadlineProgressWidget(row_widget, deadline=task.deadline)
            main_widget.clicked.connect(lambda checked, t=task: self._edit_task(t))
            row_layout.addWidget(main_widget, stretch=1)
        elif task.deadline_duration:
            # Для повторяющихся шаблонов с дедлайном: кнопка + лычка
            main_btn = ButtonFactory.create_button(
                row_widget, task.title, (100, 100, 120, 0.8)
            )
            main_btn.clicked.connect(lambda checked, t=task: self._edit_task(t))
            row_layout.addWidget(main_btn, stretch=1)
            # Лычка с длительностью
            days = task.deadline_duration.get("days", 0)
            hours = task.deadline_duration.get("hours", 0)
            duration_text = f"{days} дн. {hours} ч."
            duration_label = LabelFactory.create_label(
                row_widget, duration_text,
                bg_color=(0, 0, 0, 0),
                text_color="#d4d4d4",
                font_size=10
            )
            row_layout.addWidget(duration_label)
        else:
            # Обычная задача без дедлайна
            main_btn = ButtonFactory.create_button(
                row_widget, task.title, (100, 100, 120, 0.8)
            )
            main_btn.clicked.connect(lambda checked, t=task: self._edit_task(t))
            row_layout.addWidget(main_btn, stretch=1)

        # Кнопки действий в зависимости от типа
        if task.task_type in ("one_time", "deadline"):
            complete_btn = ButtonFactory.create_complete_button(
                row_widget, lambda checked, t=task: self._complete_task(t)
            )
            row_layout.addWidget(complete_btn)
        else:
            pause_btn = ButtonFactory.create_pause_button(
                row_widget, lambda checked, t=task: self._toggle_pause(t),
                paused=task.paused
            )
            row_layout.addWidget(pause_btn)

        edit_btn = ButtonFactory.create_edit_button(
            row_widget, lambda checked, t=task: self._edit_task(t)
        )
        row_layout.addWidget(edit_btn)

        delete_btn = ButtonFactory.create_delete_button(
            row_widget, lambda checked, t=task: self._delete_task(t)
        )
        row_layout.addWidget(delete_btn)

        return row_widget

    def _edit_task(self, task):
        dialog = TaskEditDialog(self, facade=self.facade, mode="edit", task=task)
        dialog.show()

    def _save(self):
        # Сбор данных
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return

        description = self.desc_edit.toPlainText().strip()
        priority = self.priority_combo.currentIndex() + 1  # 0->1, 1->2, 2->3, 3->4, 4->5
        deadline_on = self.deadline_check.isChecked()
        repeat_on = self.repeat_check.isChecked()

        # Определяем тип задачи
        if deadline_on and repeat_on:
            task_type = "recurring_deadline"
        elif deadline_on:
            task_type = "deadline"
        elif repeat_on:
            task_type = "recurring"
        else:
            task_type = "one_time"

        # Дедлайн или срок
        deadline = None
        deadline_duration = None
        if deadline_on:
            if repeat_on:
                deadline_duration = {
                    "days": self.days_spin.value(),
                    "hours": self.hours_spin.value()
                }
            else:
                deadline = self.deadline_datetime.dateTime().toPython()

        # Повторение (заглушка: простейшее правило, если включено)
        repeat_rule = None
        if repeat_on:
            # TODO: заменить на реальную настройку из UI
            repeat_rule = RepeatRule(repeat_type="weekly", weekdays=[0])  # пример

        data = {
            "title": title,
            "description": description,
            "task_type": task_type,
            "priority": priority,
            "repeat_rule": repeat_rule,
            "deadline": deadline,
            "deadline_duration": deadline_duration
        }

        if self.mode == "edit":
            self.facade.update_task(self.task.id, data)
        else:  # create или copy
            self.facade.add_task(data)

        self.close()

    def _complete_task(self, task):
        if QMessageBox.question(self, "Выполнение", "Отметить задачу выполненной?") == QMessageBox.Yes:
            self.facade.complete_task(task.id)

    def _toggle_pause(self, task):
        self.facade.toggle_pause(task.id)

    def _delete_task(self, task):
        if QMessageBox.question(self, "Удаление", "Удалить задачу?") == QMessageBox.Yes:
            self.facade.delete_template(task.id)

    def _add_task(self):
        dialog = TaskEditDialog(self, facade=self.facade, mode="create")
        dialog.show()

    def _open_archive(self):
        if self.archive_window is None or not self.archive_window.isVisible():
            self.archive_window = ArchiveWindow(self, facade=self.facade)
            WindowFactory.show_child_window(self, self.archive_window)
        else:
            self.archive_window.raise_()
            self.archive_window.activateWindow()

    def _update_datetime(self):
        self.date_btn.setText(DateTimeUtils.get_current_datetime_text())


class TaskEditDialog(QMainWindow):
    """Окно создания/редактирования задачи с динамическим интерфейсом."""

    def __init__(self, parent=None, mode="create", task=None, facade=None):
        super().__init__(parent)
        self.mode = mode
        self.task = task
        self.facade = facade

        # Переменные для перетаскивания
        self._drag_start_pos = None
        self._repeat_rule = None   # правило повторения, если задано

        # Настройка окна с более синим оттенком
        main_layout = WindowFactory.setup_child_window(
            self, "Задача",
            bg_color=(0, 85, 95, 0.95)  # сине-зелёный
        )

        # --- Поле "Подробное описание" (сверху, изначально пустое и некликабельное) ---
        self.desc_edit = InputWidgetFactory.create_text_edit(
            self, placeholder="",
            bg_color=(0, 0, 0, 0),          # прозрачный
            text_color="#d4d4d4",
            border="1px solid transparent",
            padding="5px",
            enabled=False                   # некликабельно
        )
        main_layout.addWidget(self.desc_edit, alignment=Qt.AlignCenter)

        # --- Заголовок окна ---
        self.header_label = LabelFactory.create_header_label(
            self, "Добавление задачи"
        )
        main_layout.addWidget(self.header_label, alignment=Qt.AlignCenter)

        # --- Поле "Название" (снизу, растянуто) ---
        self.title_edit = InputWidgetFactory.create_default_line_edit(
            self, text="",
            placeholder="Название задачи"
        )
        self.title_edit.setMinimumWidth(300)
        main_layout.addWidget(self.title_edit, alignment=Qt.AlignCenter)

        # --- Чекбоксы и приоритет ---
        check_row = QHBoxLayout()

        # Белые чекбоксы с видимым индикатором
        self.deadline_check = InputWidgetFactory.create_checkbox(
            self, "Дедлайн",
            checked=False,
            bg_color=(0, 0, 0, 0),
            text_color="white",
            indicator_bg_color=(25, 50, 75),
            indicator_checked_bg_color=(200, 200, 200),
            indicator_border="1px solid #888888",
            indicator_border_radius=3
        )
        self.repeat_check = InputWidgetFactory.create_checkbox(
            self, "Регулярная",
            checked=False,
            bg_color=(0, 0, 0, 0),
            text_color="white",
            indicator_bg_color=(25, 50, 75),
            indicator_checked_bg_color=(200, 200, 200),
            indicator_border="1px solid #888888",
            indicator_border_radius=3
        )

        check_row.addWidget(self.deadline_check)
        check_row.addWidget(self.repeat_check)
        check_row.addStretch()

        # Выпадающий список приоритета (виден, когда ни один чекбокс не отмечен)
        self.priority_combo = InputWidgetFactory.create_combo_box(
            self,
            items=["информативный", "малый", "средний", "высокий", "максимальный"],
            current_index=2,
            fixed_size=(120, 30)
        )
        # Лейбл приоритета (виден при активации чекбоксов)
        self.priority_label = LabelFactory.create_label(
            self, "средний приоритет",
            bg_color=(100, 100, 110, 0.8),
            text_color="#ffffff",
            padding="5px 10px",
            border_radius=5,
            fixed_size=(120, 30),
            alignment=Qt.AlignCenter
        )
        self.priority_label.setVisible(False)

        check_row.addWidget(self.priority_combo)
        check_row.addWidget(self.priority_label)
        main_layout.addLayout(check_row)

        # --- Динамические блоки ---
        # Блок регулярности (теперь кнопка и сводка)
        self.repeat_btn = ButtonFactory.create_button(
            self, "Настроить повторение", (100, 100, 150, 0.8)
        )
        self.repeat_summary = LabelFactory.create_label(
            self, "Правило не задано",
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        self.repeat_btn.clicked.connect(self._open_repeat_dialog)
        self.repeat_btn.setVisible(False)
        self.repeat_summary.setVisible(False)
        main_layout.addWidget(self.repeat_btn)
        main_layout.addWidget(self.repeat_summary)

        # Блок дедлайна
        self.deadline_container = QWidget()
        deadline_layout = QVBoxLayout(self.deadline_container)
        deadline_layout.setContentsMargins(0, 0, 0, 0)
        self.deadline_datetime = InputWidgetFactory.create_datetime_edit(
            self.deadline_container
        )
        self.duration_widget = QWidget()
        duration_layout = QHBoxLayout(self.duration_widget)
        duration_layout.setContentsMargins(0, 0, 0, 0)
        self.days_spin = InputWidgetFactory.create_spin_box(
            self.duration_widget, min_value=0, max_value=365, value=0, suffix=" дн."
        )
        self.hours_spin = InputWidgetFactory.create_spin_box(
            self.duration_widget, min_value=0, max_value=23, value=0, suffix=" ч."
        )
        duration_layout.addWidget(self.days_spin)
        duration_layout.addWidget(self.hours_spin)
        self.duration_widget.setVisible(False)

        deadline_layout.addWidget(self.deadline_datetime)
        deadline_layout.addWidget(self.duration_widget)
        self.deadline_container.setVisible(False)
        main_layout.addWidget(self.deadline_container)

        # --- Кнопки ---
        btn_layout = QHBoxLayout()
        save_btn = ButtonFactory.create_button(self, "Сохранить", (70, 120, 90, 0.8))
        cancel_btn = ButtonFactory.create_button(self, "Отмена", (150, 80, 80, 0.8))
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # --- Подключение сигналов ---
        self.title_edit.textChanged.connect(self._on_title_changed)
        self.deadline_check.toggled.connect(self._on_checks_changed)
        self.repeat_check.toggled.connect(self._on_checks_changed)

        # Если редактируем или копируем, заполняем поля
        if task:
            self.title_edit.setText(task.title)
            self.desc_edit.setPlainText(task.description)
            self.deadline_check.setChecked(task.task_type in ("deadline", "recurring_deadline"))
            self.repeat_check.setChecked(task.task_type in ("recurring", "recurring_deadline"))
            self.priority_combo.setCurrentIndex(task.priority - 1)  # приоритет 1..5 -> индекс 0..4
            if task.deadline:
                self.deadline_datetime.setDateTime(task.deadline)
            if task.deadline_duration:
                self.days_spin.setValue(task.deadline_duration.get("days", 0))
                self.hours_spin.setValue(task.deadline_duration.get("hours", 0))
            if task.repeat_rule:
                self._repeat_rule = task.repeat_rule
                self.repeat_summary.setText(self._format_rule_summary(task.repeat_rule))

        # Инициализация видимости (важно после заполнения полей)
        self._on_title_changed(self.title_edit.text())
        self._on_checks_changed()

        # Геометрия: компактное окно по центру родителя
        if parent:
            parent_geom = parent.frameGeometry()
            w, h = 500, 450
            self.setGeometry(parent_geom.x() + (parent_geom.width() - w) // 2,
                             parent_geom.y() + (parent_geom.height() - h) // 2,
                             w, h)

    # ---------- Обработчики динамики ----------
    def _on_title_changed(self, text):
        """Активирует описание при непустом названии."""
        if text.strip():
            self.desc_edit.setEnabled(True)
            self.desc_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(60, 50, 70, 0.9);
                    color: #d4d4d4;
                    border: 1px solid #5a4a5c;
                    border-radius: 5px;
                    padding: 5px;
                }
            """)
        else:
            self.desc_edit.setEnabled(False)
            self.desc_edit.setStyleSheet("""
                QTextEdit {
                    background-color: rgba(0, 0, 0, 0);
                    color: #d4d4d4;
                    border: 1px solid transparent;
                    border-radius: 5px;
                    padding: 5px;
                }
            """)

    def _on_checks_changed(self):
        """Обновляет видимость и текст приоритета, а также динамические блоки."""
        deadline_on = self.deadline_check.isChecked()
        repeat_on = self.repeat_check.isChecked()

        # Приоритет
        if not deadline_on and not repeat_on:
            self.priority_combo.setVisible(True)
            self.priority_label.setVisible(False)
        else:
            self.priority_combo.setVisible(False)
            self.priority_label.setVisible(True)
            if repeat_on:
                self.priority_label.setText("регулярная")
            else:
                self.priority_label.setText("срочная")

        # Блок повторения
        if repeat_on:
            self.repeat_btn.setVisible(True)
            self.repeat_summary.setVisible(True)
            if self._repeat_rule:
                self.repeat_summary.setText(self._format_rule_summary(self._repeat_rule))
        else:
            self.repeat_btn.setVisible(False)
            self.repeat_summary.setVisible(False)
            self._repeat_rule = None
            self.repeat_summary.setText("Правило не задано")

        # Блок дедлайна
        self.deadline_container.setVisible(deadline_on)
        if deadline_on:
            if repeat_on:
                self.deadline_datetime.setVisible(False)
                self.duration_widget.setVisible(True)
            else:
                self.deadline_datetime.setVisible(True)
                self.duration_widget.setVisible(False)

    # ---------- Методы для повторения ----------
    def _open_repeat_dialog(self):
        dialog = RepeatRuleDialog(self, rule=self._repeat_rule)
        dialog.rule_saved.connect(self._on_rule_saved)
        dialog.setWindowModality(Qt.ApplicationModal)   # блокируем родительское окно
        dialog.show()

    def _on_rule_saved(self, rule):
        """Получает правило из диалога и обновляет сводку."""
        self._repeat_rule = rule
        self.repeat_summary.setText(self._format_rule_summary(rule))

    def _format_rule_summary(self, rule):
        """Формирует краткое описание правила повторения."""
        if not rule:
            return "Правило не задано"
        if rule.repeat_type == "daily":
            return f"Ежедневно, каждые {rule.interval_days} дн."
        elif rule.repeat_type == "weekly":
            day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            return "Еженедельно: " + ", ".join(day_names[i] for i in rule.weekdays)
        elif rule.repeat_type == "monthly":
            if rule.monthly_type == "specific_day":
                return "Ежемесячно: " + ", ".join(str(d) for d in rule.days_of_month) + " числа"
            else:
                week_names = ["первая", "вторая", "третья", "четвёртая", "последняя"]
                day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
                return f"Ежемесячно: {week_names[rule.week_number - 1]} {day_names[rule.weekday]}"
        elif rule.repeat_type == "interval":
            return f"Интервал: каждые {rule.interval_days} дн."
        return ""

    # ---------- Перетаскивание окна ----------
    def _is_interactive_widget(self, widget):
        """Проверяет, является ли виджет интерактивным."""
        interactive_types = (
            QLineEdit, QTextEdit, QPushButton, QCheckBox, QComboBox,
            QSpinBox, QDateTimeEdit
        )
        while widget is not None:
            if isinstance(widget, interactive_types):
                return True
            widget = widget.parentWidget()
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            widget_under = self.childAt(event.position().toPoint())
            if not self._is_interactive_widget(widget_under):
                self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            parent = self.parentWidget()
            if parent:
                parent_rect = parent.frameGeometry()
                x = max(parent_rect.x(), min(new_pos.x(), parent_rect.x() + parent_rect.width() - self.width()))
                y = max(parent_rect.y(), min(new_pos.y(), parent_rect.y() + parent_rect.height() - self.height()))
                self.move(x, y)
            else:
                self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---------- Сохранение ----------
    def _save(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Ошибка", "Введите название задачи")
            return

        description = self.desc_edit.toPlainText().strip()
        priority = self.priority_combo.currentIndex() + 1  # 0..4 -> 1..5
        deadline_on = self.deadline_check.isChecked()
        repeat_on = self.repeat_check.isChecked()

        # Определяем тип задачи
        if deadline_on and repeat_on:
            task_type = "recurring_deadline"
        elif deadline_on:
            task_type = "deadline"
        elif repeat_on:
            task_type = "recurring"
        else:
            task_type = "one_time"

        deadline = None
        deadline_duration = None
        if deadline_on:
            if repeat_on:
                deadline_duration = {
                    "days": self.days_spin.value(),
                    "hours": self.hours_spin.value()
                }
            else:
                deadline = self.deadline_datetime.dateTime().toPython()

        repeat_rule = None
        if repeat_on:
            repeat_rule = self._repeat_rule
            if repeat_rule is None:
                QMessageBox.warning(self, "Ошибка", "Настройте правило повторения")
                return

        data = {
            "title": title,
            "description": description,
            "task_type": task_type,
            "priority": priority,
            "repeat_rule": repeat_rule,
            "deadline": deadline,
            "deadline_duration": deadline_duration
        }

        if self.mode == "edit":
            self.facade.update_task(self.task.id, data)
        else:
            self.facade.add_task(data)

        self.close()

    def _cancel(self):
        self.close()

class ArchiveWindow(QMainWindow):
    """Окно архива задач."""

    def __init__(self, parent=None, facade=None):
        super().__init__(parent)
        self.facade = facade

        main_layout = WindowFactory.setup_child_window(
            self, "Архив",
            bg_color=(50, 75, 60, 0.95)
        )

        # Панель фильтров и сортировки
        self.filter_panel = FilterSortPanel(self, mode="archive")
        self.filter_panel.changed.connect(self._render_archive)
        main_layout.addWidget(self.filter_panel)

        # Список архивных записей
        scroll, self.archive_widget, self.archive_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=5
        )
        # Убираем тёмный фон, если он не нужен (по вашему желанию)
        # self.archive_widget.setStyleSheet("...") – можно оставить или удалить
        main_layout.addWidget(scroll)

        if facade:
            facade.archive_changed.connect(self._render_archive)

        self._render_archive()

    def _render_archive(self):
        """Перестраивает список архивных записей с учётом фильтра и сортировки."""
        # Очистка контейнера
        while self.archive_layout.count():
            item = self.archive_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.facade:
            return

        # Получаем все записи из архива
        records = self.facade.get_archive()

        # Применяем фильтр
        try:
            filtered = self.filter_panel.get_filter().apply(records)
        except Exception:
            filtered = records

        # Применяем сортировку
        try:
            sorted_records = self.filter_panel.get_sorter().sort(filtered)
        except Exception:
            sorted_records = filtered

        if not sorted_records:
            placeholder = LabelFactory.create_label(
                self.archive_widget,
                "Нет записей, удовлетворяющих фильтру",
                bg_color=(0, 0, 0, 0),
                text_color="#d4d4d4"
            )
            self.archive_layout.addWidget(placeholder)
            return

        for rec in sorted_records:
            row = self._create_archive_row(rec)
            self.archive_layout.addWidget(row)

    def _create_archive_row(self, record):
        """Создаёт строку для одной архивной записи."""
        row_widget = QWidget()
        row_widget.setObjectName("archive_row")
        row_widget.setStyleSheet("QWidget#archive_row { background: transparent; border-radius: 0px; }")

        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # Основная метка с названием и типом
        type_text = {
            "completed": "Выполнена",
            "deleted_template": "Удалён шаблон",
            "expired_not_completed": "Не выполнена"
        }.get(record.status, "")
        label_text = f"{record.title} ({type_text})"
        main_label = LabelFactory.create_label(
            row_widget, label_text,
            bg_color=(0, 0, 0, 0), text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        row_layout.addWidget(main_label, stretch=1)

        # Кнопки действий
        if record.status == "deleted_template":
            restore_btn = ButtonFactory.create_button(
                row_widget, "Восстановить", (70, 120, 90, 0.8)
            )
            restore_btn.clicked.connect(lambda checked, r=record: self.facade.restore_deleted_template(r.id))
            row_layout.addWidget(restore_btn)

        if record.status == "completed":
            copy_btn = ButtonFactory.create_button(
                row_widget, "Копия", (100, 120, 150, 0.8)
            )
            copy_btn.clicked.connect(lambda checked, r=record: self._create_copy(r))
            row_layout.addWidget(copy_btn)

        delete_btn = ButtonFactory.create_delete_button(
            row_widget,
            lambda checked, r=record: self.facade.delete_from_archive(r.id)
        )
        row_layout.addWidget(delete_btn)

        return row_widget

    def _create_copy(self, record):
        """Открывает окно создания с предзаполненными данными."""
        data = self.facade.get_copy_data(record.id)
        if data:
            dialog = TaskEditDialog(self, facade=self.facade, mode="create")
            dialog.title_edit.setText(data.get("title", ""))
            dialog.desc_edit.setPlainText(data.get("description", ""))
            # Приоритет
            priority_index = data.get("priority", 3) - 1
            dialog.priority_combo.setCurrentIndex(priority_index)
            # Тип задачи можно не восстанавливать, но предзаполним чекбоксы
            task_type = data.get("task_type", "one_time")
            dialog.deadline_check.setChecked(task_type in ("deadline", "recurring_deadline"))
            dialog.repeat_check.setChecked(task_type in ("recurring", "recurring_deadline"))
            # Дедлайн/срок
            if data.get("deadline"):
                dialog.deadline_datetime.setDateTime(data["deadline"])
            if data.get("deadline_duration"):
                dialog.days_spin.setValue(data["deadline_duration"].get("days", 0))
                dialog.hours_spin.setValue(data["deadline_duration"].get("hours", 0))
            dialog.show()

class RepeatRuleDialog(QMainWindow):
    """Окно настройки правила повторения."""

    rule_saved = Signal(object)

    def __init__(self, parent=None, rule: RepeatRule | None = None):
        super().__init__(parent)
        self.rule = rule

        main_layout = WindowFactory.setup_child_window(
            self, "Настройка повторения",
            bg_color=(0, 5, 5, 0.75)
        )

        # Тип повторения
        main_layout.addWidget(LabelFactory.create_header_label(self, "Тип повторения"))
        self.type_combo = InputWidgetFactory.create_combo_box(
            self,
            items=[
                "Ежедневно",
                "Еженедельно",
                "Ежемесячно (по числам)",
                "Ежемесячно (по дню недели)",
                "С интервалом"
            ],
            current_index=0
        )
        main_layout.addWidget(self.type_combo)

        # --- Контейнеры для каждого типа ---
        # Ежедневно
        self.daily_container = QWidget()
        daily_layout = QHBoxLayout(self.daily_container)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        daily_layout.addWidget(QLabel("Каждые"))
        self.daily_spin = InputWidgetFactory.create_spin_box(
            self.daily_container, min_value=1, max_value=365, value=1, suffix=" дн."
        )
        daily_layout.addWidget(self.daily_spin)
        main_layout.addWidget(self.daily_container)

        # Еженедельно
        self.weekly_container = QWidget()
        weekly_layout = QHBoxLayout(self.weekly_container)
        weekly_layout.setContentsMargins(0, 0, 0, 0)
        self.weekday_checks = []
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        for i, name in enumerate(weekday_names):
            cb = InputWidgetFactory.create_checkbox(
                self.weekly_container, name,
                checked=False,
                bg_color=(0,0,0,0),
                text_color="white",
                indicator_bg_color=(25,50,75),
                indicator_checked_bg_color=(200,200,200),
                indicator_border="1px solid #888888",
                indicator_border_radius=3
            )
            self.weekday_checks.append((i, cb))
            weekly_layout.addWidget(cb)
        main_layout.addWidget(self.weekly_container)

        # Ежемесячно (по числам)
        self.monthly_specific_container = QWidget()
        specific_layout = QVBoxLayout(self.monthly_specific_container)
        specific_layout.setContentsMargins(0, 0, 0, 0)
        specific_layout.addWidget(QLabel("Выберите числа месяца:"))
        self.day_checks = []
        grid_layout = QGridLayout()
        for day in range(1, 32):
            cb = InputWidgetFactory.create_checkbox(
                self.monthly_specific_container, str(day),
                checked=False,
                bg_color=(0,0,0,0),
                text_color="white",
                indicator_bg_color=(25,50,75),
                indicator_checked_bg_color=(200,200,200),
                indicator_border="1px solid #888888",
                indicator_border_radius=2,
                fixed_size=(30, 20)
            )
            row = (day - 1) // 7
            col = (day - 1) % 7
            grid_layout.addWidget(cb, row, col)
            self.day_checks.append((day, cb))
        specific_layout.addLayout(grid_layout)
        main_layout.addWidget(self.monthly_specific_container)

        # Ежемесячно (по дню недели)
        self.monthly_weekday_container = QWidget()
        weekday_layout = QHBoxLayout(self.monthly_weekday_container)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.addWidget(QLabel("Номер недели:"))
        self.week_number_combo = InputWidgetFactory.create_combo_box(
            self.monthly_weekday_container,
            items=["Первая", "Вторая", "Третья", "Четвёртая", "Последняя"],
            current_index=0
        )
        weekday_layout.addWidget(self.week_number_combo)
        weekday_layout.addWidget(QLabel("День недели:"))
        self.weekday_combo = InputWidgetFactory.create_combo_box(
            self.monthly_weekday_container,
            items=["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"],
            current_index=0
        )
        weekday_layout.addWidget(self.weekday_combo)
        main_layout.addWidget(self.monthly_weekday_container)

        # Интервал
        self.interval_container = QWidget()
        interval_layout = QHBoxLayout(self.interval_container)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.addWidget(QLabel("Период:"))
        self.interval_spin = InputWidgetFactory.create_spin_box(
            self.interval_container, min_value=1, max_value=365, value=1, suffix=" дн."
        )
        interval_layout.addWidget(self.interval_spin)
        main_layout.addWidget(self.interval_container)

        # Ограничение повторений
        self.limit_check = InputWidgetFactory.create_checkbox(
            self, "Ограничить количество повторений",
            checked=False,
            bg_color=(0,0,0,0),
            text_color="white",
            indicator_bg_color=(25,50,75),
            indicator_checked_bg_color=(200,200,200),
            indicator_border="1px solid #888888",
            indicator_border_radius=3
        )
        main_layout.addWidget(self.limit_check)

        self.max_occurrences_spin = InputWidgetFactory.create_spin_box(
            self, min_value=1, max_value=1000, value=1
        )
        self.max_occurrences_spin.setVisible(False)
        main_layout.addWidget(self.max_occurrences_spin)

        # Кнопки
        btn_layout = QHBoxLayout()
        save_btn = ButtonFactory.create_button(self, "Сохранить", (70, 120, 90, 0.8))
        cancel_btn = ButtonFactory.create_button(self, "Отмена", (150, 80, 80, 0.8))
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # Подключение сигналов
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.limit_check.toggled.connect(self._on_limit_toggled)

        # Заполнение при наличии правила
        if rule:
            self.set_rule(rule)
        else:
            self._on_type_changed(0)
            self._on_limit_toggled(False)

        if parent:
            parent_geom = parent.frameGeometry()
            w, h = 400, 350
            self.setGeometry(parent_geom.x() + (parent_geom.width() - w) // 2 - 50 ,
                             parent_geom.y() + (parent_geom.height() - h) // 2- 225,
                             w, h)

    def _on_type_changed(self, index):
        self.daily_container.setVisible(index == 0)
        self.weekly_container.setVisible(index == 1)
        self.monthly_specific_container.setVisible(index == 2)
        self.monthly_weekday_container.setVisible(index == 3)
        self.interval_container.setVisible(index == 4)

    def _on_limit_toggled(self, checked):
        self.max_occurrences_spin.setVisible(checked)

    def set_rule(self, rule: RepeatRule):
        """Заполняет поля на основе правила."""
        if rule.repeat_type == "daily":
            self.type_combo.setCurrentIndex(0)
            self.daily_spin.setValue(rule.interval_days)
        elif rule.repeat_type == "weekly":
            self.type_combo.setCurrentIndex(1)
            for i, cb in self.weekday_checks:
                cb.setChecked(i in rule.weekdays)
        elif rule.repeat_type == "monthly":
            if rule.monthly_type == "specific_day":
                self.type_combo.setCurrentIndex(2)
                for d, cb in self.day_checks:
                    cb.setChecked(d in rule.days_of_month)
            elif rule.monthly_type == "weekday_pattern":
                self.type_combo.setCurrentIndex(3)
                self.week_number_combo.setCurrentIndex(rule.week_number - 1)
                self.weekday_combo.setCurrentIndex(rule.weekday)
        elif rule.repeat_type == "interval":
            self.type_combo.setCurrentIndex(4)
            self.interval_spin.setValue(rule.interval_days)

        if rule.max_occurrences is not None:
            self.limit_check.setChecked(True)
            self.max_occurrences_spin.setValue(rule.max_occurrences)
        else:
            self.limit_check.setChecked(False)

    def _save(self):
        type_index = self.type_combo.currentIndex()
        if type_index == 0:
            rule = RepeatRule(repeat_type="daily", interval_days=self.daily_spin.value())
        elif type_index == 1:
            days = [i for i, cb in self.weekday_checks if cb.isChecked()]
            if not days:
                QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один день недели")
                return
            rule = RepeatRule(repeat_type="weekly", weekdays=days)
        elif type_index == 2:
            days = [d for d, cb in self.day_checks if cb.isChecked()]
            if not days:
                QMessageBox.warning(self, "Ошибка", "Выберите хотя бы одно число месяца")
                return
            rule = RepeatRule(repeat_type="monthly", monthly_type="specific_day",
                              days_of_month=days)
        elif type_index == 3:
            week_num = self.week_number_combo.currentIndex() + 1
            weekday = self.weekday_combo.currentIndex()
            rule = RepeatRule(repeat_type="monthly", monthly_type="weekday_pattern",
                              week_number=week_num, weekday=weekday)
        elif type_index == 4:
            rule = RepeatRule(repeat_type="interval", interval_days=self.interval_spin.value())
        else:
            rule = RepeatRule(repeat_type="none")

        if self.limit_check.isChecked():
            rule.max_occurrences = self.max_occurrences_spin.value()
        else:
            rule.max_occurrences = None

        self.rule = rule
        self.rule_saved.emit(rule)
        self.close()

class DailyTasksWidget(QWidget):
    """Виджет для отображения задач на сегодня (активных экземпляров)."""

    def __init__(self, parent=None, facade: PlannerFacade = None):
        super().__init__(parent)
        self.facade = facade

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Заголовок
        title = LabelFactory.create_header_label(self, "Задачи на сегодня")
        layout.addWidget(title)

        # Прокручиваемая область для списка
        scroll, self.tasks_widget, self.tasks_layout = ListWidgetFactory.create_scroll_container(
            self, spacing=5
        )
        layout.addWidget(scroll)

        # Если фасад передан, подписываемся на обновления и загружаем данные
        if facade:
            facade.instances_changed.connect(self._render_tasks)
            self._render_tasks()

    def _render_tasks(self):
        """Перестраивает список активных экземпляров на сегодня."""
        # Очистка
        while self.tasks_layout.count():
            item = self.tasks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.facade:
            return

        tasks = self.facade.get_today_instances()
        if not tasks:
            placeholder = LabelFactory.create_label(
                self.tasks_widget, "Нет задач на сегодня",
                bg_color=(0, 0, 0, 0), text_color="#d4d4d4"
            )
            self.tasks_layout.addWidget(placeholder)
            return

        for task in tasks:
            row = self._create_task_row(task)
            self.tasks_layout.addWidget(row)

    def _create_task_row(self, task):
        """Создаёт строку для одного экземпляра."""
        row_widget = QWidget()
        row_widget.setObjectName("today_task_row")
        row_widget.setStyleSheet("QWidget#today_task_row { background: transparent; border-radius: 0px; }")

        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(4)

        # Основной виджет: прогрессбар или метка
        if task.deadline:
            main_widget = DeadlineProgressWidget(row_widget, deadline=task.deadline)
            row_layout.addWidget(main_widget, stretch=1)
        else:
            name_label = LabelFactory.create_label(
                row_widget, task.title,
                bg_color=(0, 0, 0, 0),
                text_color="#d4d4d4",
                alignment=Qt.AlignLeft | Qt.AlignVCenter
            )
            row_layout.addWidget(name_label, stretch=1)

        # Кнопка выполнения
        complete_btn = ButtonFactory.create_complete_button(
            row_widget,
            lambda checked, t=task: self._complete_task(t)
        )
        row_layout.addWidget(complete_btn)

        return row_widget

    def _complete_task(self, task):
        """Подтверждение и выполнение задачи."""
        if QMessageBox.question(self, "Выполнение", "Отметить задачу выполненной?") == QMessageBox.Yes:
            if self.facade:
                self.facade.complete_task(task.id)

class FilterSortPanel(QWidget):
    changed = Signal()

    def __init__(self, parent=None, mode="planner"):
        super().__init__(parent)
        self.mode = mode
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Сортировка ---
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("Сортировать по:"))
        self.sort_by_combo = QComboBox()
        if self.mode == "planner":
            self.sort_by_combo.addItems([
                "Дата создания", "Дедлайн", "Приоритет", "Название",
                "Тип задачи", "Дата следующей генерации"
            ])
        else:  # archive
            self.sort_by_combo.addItems([
                "Дата создания", "Дата архивации", "Название", "Приоритет"
            ])
        sort_layout.addWidget(self.sort_by_combo)

        sort_layout.addWidget(QLabel("Направление:"))
        self.sort_order_combo = QComboBox()
        self.sort_order_combo.addItems(["По возрастанию", "По убыванию"])
        sort_layout.addWidget(self.sort_order_combo)
        layout.addLayout(sort_layout)

        # --- Фильтры ---
        self.filter_widget = QWidget()
        filter_layout = QVBoxLayout(self.filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        if self.mode == "planner":
            self.check_deadline = QCheckBox("Дедлайн")
            self.check_recurring = QCheckBox("Регулярная")
            self.check_one_time = QCheckBox("Обычная")
            filter_layout.addWidget(self.check_deadline)
            filter_layout.addWidget(self.check_recurring)
            filter_layout.addWidget(self.check_one_time)

            # Дополнительные поля (появляются в зависимости от выбранного)
            self.extra_filter = QWidget()
            extra_layout = QGridLayout(self.extra_filter)

            self.deadline_from = InputWidgetFactory.create_date_edit(self.extra_filter)
            self.deadline_to = InputWidgetFactory.create_date_edit(self.extra_filter)
            extra_layout.addWidget(QLabel("Дедлайн с:"), 0, 0)
            extra_layout.addWidget(self.deadline_from, 0, 1)
            extra_layout.addWidget(QLabel("по:"), 0, 2)
            extra_layout.addWidget(self.deadline_to, 0, 3)

            self.gen_from = InputWidgetFactory.create_date_edit(self.extra_filter)
            self.gen_to = InputWidgetFactory.create_date_edit(self.extra_filter)
            extra_layout.addWidget(QLabel("Генерация с:"), 1, 0)
            extra_layout.addWidget(self.gen_from, 1, 1)
            extra_layout.addWidget(QLabel("по:"), 1, 2)
            extra_layout.addWidget(self.gen_to, 1, 3)

            self.priority_combo = QComboBox()
            self.priority_combo.addItems([
                "1 - информативный", "2 - малый", "3 - средний",
                "4 - высокий", "5 - максимальный"
            ])
            extra_layout.addWidget(QLabel("Приоритет:"), 2, 0)
            extra_layout.addWidget(self.priority_combo, 2, 1, 1, 3)

            filter_layout.addWidget(self.extra_filter)

            # Обновление видимости доп. полей
            self.check_deadline.toggled.connect(self._update_extra_visibility)
            self.check_recurring.toggled.connect(self._update_extra_visibility)
            self.check_one_time.toggled.connect(self._update_extra_visibility)
            self._update_extra_visibility()

            # Сигналы изменений
            self.check_deadline.toggled.connect(self.changed.emit)
            self.check_recurring.toggled.connect(self.changed.emit)
            self.check_one_time.toggled.connect(self.changed.emit)
            self.deadline_from.dateChanged.connect(self.changed.emit)
            self.deadline_to.dateChanged.connect(self.changed.emit)
            self.gen_from.dateChanged.connect(self.changed.emit)
            self.gen_to.dateChanged.connect(self.changed.emit)
            self.priority_combo.currentIndexChanged.connect(self.changed.emit)

        else:  # archive
            self.status_combo = QComboBox()
            self.status_combo.addItems([
                "Все", "Выполненные", "Удалённые шаблоны", "Невыполненные экземпляры"
            ])
            filter_layout.addWidget(QLabel("Статус:"))
            filter_layout.addWidget(self.status_combo)

            self.check_deadline = QCheckBox("Дедлайн")
            self.check_recurring = QCheckBox("Регулярная")
            self.check_one_time = QCheckBox("Обычная")
            filter_layout.addWidget(self.check_deadline)
            filter_layout.addWidget(self.check_recurring)
            filter_layout.addWidget(self.check_one_time)

            # Сигналы
            self.status_combo.currentIndexChanged.connect(self.changed.emit)
            self.check_deadline.toggled.connect(self.changed.emit)
            self.check_recurring.toggled.connect(self.changed.emit)
            self.check_one_time.toggled.connect(self.changed.emit)

        layout.addWidget(self.filter_widget)

        # Сортировка – сигналы
        self.sort_by_combo.currentIndexChanged.connect(self.changed.emit)
        self.sort_order_combo.currentIndexChanged.connect(self.changed.emit)

    def _update_extra_visibility(self):
        deadline_only = (self.check_deadline.isChecked() and
                         not self.check_recurring.isChecked() and
                         not self.check_one_time.isChecked())
        recurring_only = (self.check_recurring.isChecked() and
                          not self.check_deadline.isChecked() and
                          not self.check_one_time.isChecked())
        both = (self.check_deadline.isChecked() and
                self.check_recurring.isChecked() and
                not self.check_one_time.isChecked())
        one_time_only = (self.check_one_time.isChecked() and
                         not self.check_deadline.isChecked() and
                         not self.check_recurring.isChecked())

        self.deadline_from.setVisible(deadline_only)
        self.deadline_to.setVisible(deadline_only)
        self.gen_from.setVisible(recurring_only or both)
        self.gen_to.setVisible(recurring_only or both)
        self.priority_combo.setVisible(one_time_only)

    def get_filter(self):
        task_type = None
        priority = None
        status = None
        deadline_from = None
        deadline_to = None
        next_gen_from = None
        next_gen_to = None

        if self.mode == "planner":
            selected_types = []
            if self.check_deadline.isChecked():
                selected_types += ["deadline", "recurring_deadline"]
            if self.check_recurring.isChecked():
                selected_types += ["recurring", "recurring_deadline"]
            if self.check_one_time.isChecked():
                selected_types.append("one_time")
            if selected_types:
                task_type = list(set(selected_types))

            if (self.check_one_time.isChecked() and
                not self.check_deadline.isChecked() and
                not self.check_recurring.isChecked()):
                priority = [self.priority_combo.currentIndex() + 1]

            if self.deadline_from.isVisible():
                deadline_from = self.deadline_from.date().toPython()
                deadline_to = self.deadline_to.date().toPython()
            if self.gen_from.isVisible():
                next_gen_from = self.gen_from.date().toPython()
                next_gen_to = self.gen_to.date().toPython()

        else:  # archive
            status_index = self.status_combo.currentIndex()
            if status_index == 1:
                status = ["completed"]
            elif status_index == 2:
                status = ["deleted_template"]
            elif status_index == 3:
                status = ["expired_not_completed"]

            selected_types = []
            if self.check_deadline.isChecked():
                selected_types += ["deadline", "recurring_deadline"]
            if self.check_recurring.isChecked():
                selected_types += ["recurring", "recurring_deadline"]
            if self.check_one_time.isChecked():
                selected_types.append("one_time")
            if selected_types:
                task_type = list(set(selected_types))

        return TaskFilter(
            task_type=task_type,
            priority=priority,
            status=status,
            deadline_from=deadline_from,
            deadline_to=deadline_to,
            next_generation_from=next_gen_from,
            next_generation_to=next_gen_to,
        )

    def get_sorter(self):
        if self.mode == "planner":
            mapping = [
                "created_at", "deadline", "priority", "title",
                "task_type", "next_generation_date"
            ]
        else:
            mapping = ["created_at", "archived_at", "title", "priority"]

        sort_by = mapping[self.sort_by_combo.currentIndex()]
        ascending = self.sort_order_combo.currentIndex() == 0
        return TaskSorter(sort_by=sort_by, ascending=ascending)
