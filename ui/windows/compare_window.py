"""
Окно сравнения поставок.

Назначение:
    Пайплайн из шести шагов: подготовка (копия листа + сборный
    файл + загрузка), три этапа сопоставления, отчёт. Все шаги
    идут в фоновом потоке через BaseServiceWindow._run_async_step.
    Диалоги стадий открываются в UI-потоке через callbacks
    CompareService с QMetaObject.invokeMethod + BlockingQueuedConnection.

Роль в программе:
    Открывается из MainWindow. Наследник BaseServiceWindow:
    set_status/set_info/_precheck_target_dir/closeEvent/
    on_accumulate_sales — унаследованы. Окно отвечает за раскладку,
    gating через self._state и специфику callbacks.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QMetaObject, QThread, Slot
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QVBoxLayout, QWidget,
)

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, ListWidgetFactory,
    LayoutFactory, FileDialogFactory,
)
from ui.styles import ColorCalculator
from ui.widgets.path_selector import PathSelector
from ui.windows.mappings_window import BrandMappingsWindow
from ui.windows.compare_dialogs import (
    Stage1ReviewDialog, ConfirmMatchDialog, ManualMatchDialog,
)
from utils.log_tools.decorators import log_button_action
from services.compare_service import CompareService


class CompareWindow(BaseServiceWindow):
    """Окно сравнения листа поставки с фактическими поставками.

    Роль:
        Ведёт пользователя по шагам: подготовка → этап 1 → этап 2 →
        этап 3 → отчёт. Все шаги идут в фоне, стадии вызывают
        callbacks окна; те через QMetaObject.invokeMethod с
        BlockingQueuedConnection открывают диалог в UI-потоке.

    Атрибуты класса:
        LOGGER_SOURCE / LOGGER_DOMAIN — идентификация для LoggerV2.
        BG_COLOR — производный от (50, 50, 50) → (50, 80, 70, 0.95).
        PIPELINE_BUTTONS — пять кнопок пайплайна.

    Поля экземпляра:
        service — CompareService с callbacks.
        _state — gating шагов: prepared, stage1_done, stage2_done,
                 stage3_done.
        _stageN_request / _stageN_response — обмен с UI-потоком
                 для диалогов (Q_ARG с Python-объектами ненадёжен).
    """

    LOGGER_SOURCE = "CompareWindow.compare_window"
    LOGGER_DOMAIN = "compare"

    # BG_COLOR: r, 2g-2(g//5), b+2(b//5) от (50,50,50) → (50, 80, 70).
    # alpha — из дефолта ColorCalculator.derive (0.95).
    BG_COLOR = ColorCalculator.derive(
        (50, 50, 50),
        r_fn=lambda r: r,
        g_fn=lambda g: 2 * g - 2 * (g // 5),
        b_fn=lambda b: b + 2 * (b // 5),
    )

    PIPELINE_BUTTONS = (
        "btn_prepare",
        "btn_stage1",
        "btn_stage2",
        "btn_stage3",
        "btn_report",
    )

    def __init__(self, parent=None, mappings_storage=None,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            mappings_storage — CompareMappingsStorage из MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: создаёт gating-состояние, сервис с callbacks,
              раскладку.
        """
        super().__init__(
            parent,
            title="Сравнение поставок",
            log_manager_v2=log_manager_v2,
        )

        # Специфичное состояние окна.
        self.supply_file = None            # один файл листа поставки
        self._state = {
            "prepared":    False,
            "stage1_done": False,
            "stage2_done": False,
            "stage3_done": False,
        }

        # Обмен с UI-потоком для диалогов стадий.
        self._stage1_request = None
        self._stage1_response = None
        self._stage2_request = None
        self._stage2_response = False
        self._stage3_request = None
        self._stage3_response = (None, False)

        # brands_set — ключи брендов из конфига.
        brands = parent.sellers_brands_service.get_brands_objects()
        brands_set = set()
        for b in brands:
            brands_set.add(b.name.lower())
            for key in b.keys:
                brands_set.add(key.lower())

        # Сервис с callbacks.
        self.service = CompareService(
            log_manager_v2=log_manager_v2,
            brands_set=brands_set,
            mappings_storage=mappings_storage,
            stage1_reviewer=self._review_stage1,
            stage2_confirmer=self._confirm_stage2,
            stage3_selector=self._select_stage3,
        )

        # ============================================================
        # ЭЛЕМЕНТЫ
        # ============================================================
        self.instruction_label = LabelFactory.create_label(
            self,
            text=(
                "Подготовка к сравнению поставок\n"
                "Шаг 1: Выберите папку для сохранения результатов\n"
                "Шаг 2: Выберите файл листа поставки (один Excel-файл)\n"
                "Шаг 3: Добавьте файлы с фактическими поставками (можно несколько)\n"
                "Шаг 4: Нажмите 'Подготовить для работы' – данные будут загружены\n"
                "Шаг 5: Последовательно выполняйте этапы 1→2→3\n"
                "Шаг 6: Сформируйте отчёт"
            ),
            bg_color=(0, 0, 0, 0),
            text_color="#c2c2c2",
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        self.main_layout.addWidget(self.instruction_label)

        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите папку для результатов",
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)
        self.main_layout.addWidget(self.path_selector)

        # Строка выбора файла листа поставки.
        self.btn_choose_file = ButtonFactory.create_button(
            self, "Выбрать Лист сверки", (100, 120, 100, 0.8),
        )
        self.btn_choose_file.clicked.connect(self.select_supply_file)

        self.file_label = LabelFactory.create_label(
            self, "Файл не выбран",
            bg_color=(64, 48, 66, 128),
            text_color="#d4d4d4",
            padding="4px 8px",
            border_radius=5,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_family="Consolas, monospace",
            font_size=10,
        )
        file_row = LayoutFactory.create_row(
            self, self.btn_choose_file, self.file_label, spacing=5,
        )
        self.main_layout.addWidget(file_row)

        # Две колонки: слева кнопки пайплайна, справа список файлов.
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self.step_label = LabelFactory.create_label(
            self, "Текущий шаг: Ожидание",
            bg_color=(0, 0, 0, 0),
            text_color="#d4d4d4",
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
            font_size=12,
            font_weight="bold",
        )
        left_layout.addWidget(self.step_label)

        self.btn_prepare = ButtonFactory.create_button(
            self, "Подготовить для работы", (30, 50, 100, 0.8),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_prepare.clicked.connect(self.on_prepare)
        left_layout.addWidget(self.btn_prepare)

        self.btn_stage1 = ButtonFactory.create_button(
            self, "Этап 1 (жёсткая сверка)", (30, 80, 100, 0.8),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_stage1.clicked.connect(self.on_stage1)
        left_layout.addWidget(self.btn_stage1)

        self.btn_stage2 = ButtonFactory.create_button(
            self, "Этап 2 (мягкая сверка)", (30, 110, 100, 0.8),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_stage2.clicked.connect(self.on_stage2)
        left_layout.addWidget(self.btn_stage2)

        self.btn_stage3 = ButtonFactory.create_button(
            self, "Этап 3 (ручной выбор)", (30, 120, 100, 0.8),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_stage3.clicked.connect(self.on_stage3)
        left_layout.addWidget(self.btn_stage3)

        self.btn_report = ButtonFactory.create_button(
            self, "Сформировать отчёт", (90, 110, 160, 0.8),
            padding="8px 16px", fixed_size=(220, 35),
        )
        self.btn_report.clicked.connect(self.on_generate_report)
        left_layout.addWidget(self.btn_report)
        left_layout.addStretch()

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)

        self.btn_add_supply = ButtonFactory.create_button(
            self, "Добавить файлы поставок", (70, 120, 160, 0.8),
            padding="6px 12px", fixed_size=(220, 30),
        )
        self.btn_add_supply.clicked.connect(self.select_supply_files)
        right_layout.addWidget(self.btn_add_supply)

        # FileListWidget — списки с крестиками.
        self.list_supply = ListWidgetFactory.create_file_list_widget(
            self,
            fixed_width=220,
            fixed_height=200,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10,
        )
        right_layout.addWidget(self.list_supply)
        right_layout.addStretch()

        columns_layout.addWidget(left_widget)
        columns_layout.addWidget(right_widget)
        self.main_layout.addLayout(columns_layout)

        # Кнопка «Сохранённые сопоставления».
        self.btn_mappings = ButtonFactory.create_button(
            self, "Сохранённые сопоставления", (70, 120, 160, 0.8),
            padding="8px 16px", fixed_size=(200, 30),
        )
        self.btn_mappings.clicked.connect(self._open_mappings_window)
        mappings_row = LayoutFactory.create_row(
            self, self.btn_mappings, alignment=Qt.AlignCenter,
        )
        self.main_layout.addWidget(mappings_row)

        # status_label и status_log — из базового класса.
        self.main_layout.addWidget(self.status_label)
        self.main_layout.addWidget(self.status_log)

        # Стартовое состояние кнопок.
        self._update_buttons_state()
        self.set_info("Окно сравнения поставок готово к работе.")

        if self.logger:
            self.logger.debug("CompareWindow.__init__: окно инициализировано")

    # ============================================================
    # GATING
    # ============================================================

    def _update_buttons_state(self) -> None:
        """Включает/выключает кнопки по self._state.

        Вход: нет.
        Выход: нет.
        Роль: btn_prepare — всегда; остальные — по gating-флагам.
        """
        st = self._state
        self.btn_prepare.setEnabled(True)
        self.btn_stage1.setEnabled(st["prepared"])
        self.btn_stage2.setEnabled(st["stage1_done"])
        self.btn_stage3.setEnabled(st["stage2_done"])
        self.btn_report.setEnabled(st["stage3_done"])

    def _maybe_unlock_report(self) -> None:
        """Разрешает отчёт, если сопоставлять больше нечего.

        Вход: нет.
        Выход: нет.
        Роль: после этапов 1/2 может оказаться, что supply_items
              или candidates пусты. Тогда флаг stage3_done
              выставляется принудительно.
        """
        if not self._state["prepared"]:
            return
        if not self.service.supply_items or not self.service.candidates:
            self._state["stage3_done"] = True
            self._update_buttons_state()

    # ============================================================
    # ЦЕЛЕВАЯ ПАПКА — переопределение целиком
    # ============================================================

    def _on_target_dir_changed(self, new_path) -> None:
        """Обработка смены целевой папки.

        Вход: new_path — новый путь.
        Выход: нет.

        Роль: переопределена (не через хук) — логика специфична:
              без status_log.clear() и set_info, но со сбросом
              gating-состояния.
        """
        if self.logger:
            self.logger.debug(
                f"_on_target_dir_changed: новая папка {new_path}"
            )
        self.target_dir = new_path
        self.main_window.main_config.set("target_dir", new_path)
        self._state = {
            "prepared":    False,
            "stage1_done": False,
            "stage2_done": False,
            "stage3_done": False,
        }
        self._update_buttons_state()
        self.set_status("Целевая папка обновлена.")

    # ============================================================
    # CALLBACKS ДЛЯ CompareService (потокобезопасные)
    # ============================================================

    def _review_stage1(self, pairs) -> list:
        """Открывает Stage1ReviewDialog в UI-потоке.

        Вход: pairs — список (SupplyItem, Candidate).
        Выход: list[bool] — какие пары оставить.
        Роль: если фоновый поток — invokeMethod с BlockingQueued;
              если UI-поток — вызываем слот напрямую.
        """
        self._stage1_request = pairs
        self._stage1_response = None

        app = QApplication.instance()
        if app is None:
            return [True] * len(pairs)

        if QThread.currentThread() == app.thread():
            self._show_stage1_dialog_slot()
        else:
            QMetaObject.invokeMethod(
                self, "_show_stage1_dialog_slot",
                Qt.BlockingQueuedConnection,
            )
        if self._stage1_response is None:
            return [True] * len(pairs)
        return self._stage1_response

    @Slot()
    def _show_stage1_dialog_slot(self) -> None:
        """Открывает Stage1ReviewDialog. Выполняется в UI-потоке."""
        dialog = Stage1ReviewDialog(self, self._stage1_request)
        dialog.exec()
        self._stage1_response = dialog.get_keep_flags()

    def _confirm_stage2(self, item, candidate, score: float,
                        remaining: int) -> bool:
        """Открывает ConfirmMatchDialog в UI-потоке.

        Вход:
            item — SupplyItem.
            candidate — Candidate.
            score — схожесть.
            remaining — сколько товаров осталось.

        Выход: True — подтверждено, False — отклонено.
        """
        self._stage2_request = (item, candidate, score, remaining)
        self._stage2_response = False

        app = QApplication.instance()
        if app is None:
            return True

        if QThread.currentThread() == app.thread():
            self._show_stage2_dialog_slot()
        else:
            QMetaObject.invokeMethod(
                self, "_show_stage2_dialog_slot",
                Qt.BlockingQueuedConnection,
            )
        return self._stage2_response

    @Slot()
    def _show_stage2_dialog_slot(self) -> None:
        """Открывает ConfirmMatchDialog. Выполняется в UI-потоке."""
        item, candidate, score, remaining = self._stage2_request
        dialog = ConfirmMatchDialog(
            self,
            {"name": item.name, "count": item.count},
            {"name": candidate.name, "count": candidate.count},
            score,
            remaining,
        )
        dialog.exec()
        self._stage2_response = (dialog.get_result() == "confirmed")

    def _select_stage3(self, item, candidates, remaining: int) -> tuple:
        """Открывает ManualMatchDialog в UI-потоке.

        Вход:
            item — SupplyItem.
            candidates — список доступных Candidate.
            remaining — сколько товаров в очереди.

        Выход: (Candidate | None, skip_all: bool).
        """
        self._stage3_request = (item, candidates, remaining)
        self._stage3_response = (None, False)

        app = QApplication.instance()
        if app is None:
            return (None, False)

        if QThread.currentThread() == app.thread():
            self._show_stage3_dialog_slot()
        else:
            QMetaObject.invokeMethod(
                self, "_show_stage3_dialog_slot",
                Qt.BlockingQueuedConnection,
            )
        return self._stage3_response

    @Slot()
    def _show_stage3_dialog_slot(self) -> None:
        """Открывает ManualMatchDialog. Выполняется в UI-потоке."""
        item, candidates, remaining = self._stage3_request
        candidates_for_dialog = [
            {"name": c.name, "count": c.count} for c in candidates
        ]
        dialog = ManualMatchDialog(
            self,
            {"name": item.name, "count": item.count},
            candidates_for_dialog,
            remaining,
        )
        dialog.exec()
        selected, skip_all = dialog.get_result()

        if selected is None:
            self._stage3_response = (None, skip_all)
            return

        # Найти объект Candidate по name + count среди исходных.
        matched = None
        for c in candidates:
            if (c.name == selected["name"]
                    and c.count == selected.get("count")):
                matched = c
                break
        self._stage3_response = (matched, skip_all)

    # ============================================================
    # ВЫБОР ФАЙЛОВ
    # ============================================================

    @log_button_action(
        "btn_choose_file",
        "Ошибка при выборе листа поставки: {e}",
    )
    def select_supply_file(self) -> None:
        """Открывает диалог выбора файла листа поставки.

        Роль: тонкая обёртка над _select_single_file. Путь
              сохраняется в self.supply_file через callback.
        """
        self._select_single_file(
            config_key="last_compare_supply_dir",
            title="Выберите Excel-файл листа поставки",
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER,
            label_widget=self.file_label,
            on_success=self._on_supply_file_selected,
        )

    def _on_supply_file_selected(self, path: str) -> None:
        """Сохраняет путь в self.supply_file и пишет в лог."""
        self.supply_file = path
        self.set_info(f"Выбран файл поставки: {Path(path).name}")

    @log_button_action(
        "btn_add_supply",
        "Ошибка при выборе файлов поставок: {e}",
    )
    def select_supply_files(self) -> None:
        """Открывает диалог выбора файлов поставок.

        Роль: тонкая обёртка над _select_multiple_files. Файлы
              добавляются в list_supply через FileListWidget.add_file.
        """
        self._select_multiple_files(
            config_key="last_compare_supplies_dir",
            title="Выберите файлы с поставками",
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER,
            list_widget=self.list_supply,
            on_success=lambda added: self.set_info(
                f"Добавлено {len(added)} файлов поставок. "
                f"Всего: {self.list_supply.count()}"
            ),
        )

    @log_button_action(
        "btn_mappings",
        "Ошибка при открытии окна сопоставлений: {e}",
    )
    def _open_mappings_window(self) -> None:
        """Открывает окно сохранённых сопоставлений (синхронно)."""
        window = BrandMappingsWindow(
            parent=self,
            service=self.service,
            sellers_brands_service=self.main_window.sellers_brands_service,
        )
        window.exec()

    # ============================================================
    # ОБРАБОТЧИКИ ПАЙПЛАЙНА
    # ============================================================

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
        """Шаг 1: подготовка (копия листа + сборный + загрузка)."""
        if not self._precheck_target_dir():
            return
        if not self.supply_file:
            self.set_status("Сначала выберите файл листа поставки")
            return
        supply_files = self.list_supply.get_files()
        if not supply_files:
            self.set_status("Добавьте хотя бы один файл с поставками")
            return

        # Захватываем Qt-данные в UI-потоке до запуска фонового шага.
        self._run_async_step(
            service=self.service,
            target_method=self._prepare_pipeline,
            kwargs={
                "supply_file": self.supply_file,
                "supply_files": supply_files,
            },
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            on_success=self._after_prepare,
        )

    def _prepare_pipeline(self, target_dir, sellers,
                          supply_file, supply_files) -> None:
        """Тело шага подготовки. Выполняется в фоновом потоке.

        Вход:
            target_dir — из _run_async_step.
            sellers — из _run_async_step (не используется, но
                      подпись обязательна по контракту).
            supply_file — путь к листу поставки.
            supply_files — список путей к файлам поставок.

        Роль: три вызова сервиса подряд. Qt-виджеты не трогаются —
              всё, что нужно, пришло в аргументах.
        """
        self.service.copy_supply_sheet(supply_file, target_dir)
        self.service.build_consolidated_supply(supply_files, target_dir)
        self.service.load_data()

    def _after_prepare(self) -> None:
        """Вызывается в UI-потоке после успеха подготовки."""
        self._state["prepared"] = True
        self._update_buttons_state()
        self.step_label.setText(
            "Текущий шаг: Подготовка завершена. Нажмите Этап 1"
        )

    @log_button_action("btn_stage1", "Ошибка в on_stage1: {e}")
    def on_stage1(self) -> None:
        """Шаг 2: этап 1 — жёсткая сверка."""
        if not self._precheck_target_dir():
            return
        self._run_async_step(
            service=self.service,
            target_method=self._stage1_pipeline,
            kwargs={},
            start_message="Этап 1 — жёсткая сверка...",
            finish_message="Этап 1 завершён.",
            step_name="on_stage1",
            on_success=self._after_stage1,
        )

    def _stage1_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 1. Выполняется в фоновом потоке."""
        self.service.run_stage1()

    def _after_stage1(self) -> None:
        """UI-поток после успеха этапа 1."""
        self._state["stage1_done"] = True
        self._update_buttons_state()
        self._maybe_unlock_report()
        self.step_label.setText(
            "Текущий шаг: Этап 1 завершён. Нажмите Этап 2"
        )

    @log_button_action("btn_stage2", "Ошибка в on_stage2: {e}")
    def on_stage2(self) -> None:
        """Шаг 3: этап 2 — мягкая сверка."""
        if not self._precheck_target_dir():
            return
        self._run_async_step(
            service=self.service,
            target_method=self._stage2_pipeline,
            kwargs={},
            start_message="Этап 2 — мягкая сверка...",
            finish_message="Этап 2 завершён.",
            step_name="on_stage2",
            on_success=self._after_stage2,
        )

    def _stage2_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 2. Выполняется в фоновом потоке."""
        self.service.run_stage2()

    def _after_stage2(self) -> None:
        """UI-поток после успеха этапа 2."""
        self._state["stage2_done"] = True
        self._update_buttons_state()
        self._maybe_unlock_report()
        self.step_label.setText(
            "Текущий шаг: Этап 2 завершён. Нажмите Этап 3"
        )

    @log_button_action("btn_stage3", "Ошибка в on_stage3: {e}")
    def on_stage3(self) -> None:
        """Шаг 4: этап 3 — ручной выбор."""
        if not self._precheck_target_dir():
            return
        self._run_async_step(
            service=self.service,
            target_method=self._stage3_pipeline,
            kwargs={},
            start_message="Этап 3 — ручной выбор...",
            finish_message="Этап 3 завершён.",
            step_name="on_stage3",
            on_success=self._after_stage3,
        )

    def _stage3_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 3. Выполняется в фоновом потоке."""
        self.service.run_stage3()

    def _after_stage3(self) -> None:
        """UI-поток после успеха этапа 3."""
        self._state["stage3_done"] = True
        self._update_buttons_state()
        self.step_label.setText(
            "Текущий шаг: Все этапы завершены. Сформируйте отчёт"
        )

    @log_button_action("btn_report", "Ошибка в on_generate_report: {e}")
    def on_generate_report(self) -> None:
        """Шаг 5: формирование отчёта и сохранение сопоставлений."""
        if not self._precheck_target_dir():
            return
        self._run_async_step(
            service=self.service,
            target_method=self._generate_report_pipeline,
            kwargs={},
            start_message="Формирование отчёта...",
            finish_message="Отчёт и сопоставления сохранены.",
            step_name="on_generate_report",
            on_success=None,
        )

    def _generate_report_pipeline(self, target_dir, sellers) -> None:
        """Тело шага отчёта. Выполняется в фоновом потоке."""
        self.service.generate_report(target_dir)
        self.service.save_mappings()

    # ============================================================
    # ЗАКРЫТИЕ ОКНА
    # ============================================================

    def cleanup(self) -> None:
        """Сброс состояния окна при закрытии."""
        self.supply_file = None
        self.list_supply.clear_files()
