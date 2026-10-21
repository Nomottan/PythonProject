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

Структура файла:
    КОНСТАНТЫ → ИНИЦИАЛИЗАЦИЯ → ОБРАБОТЧИКИ КНОПОК →
    ПРИВАТНЫЕ МЕТОДЫ → ХУКИ → ВЗАИМОДЕЙСТВИЕ С ОКНОМ.
"""

from PySide6.QtCore import Qt, QMetaObject, QThread, Slot
from PySide6.QtWidgets import QApplication
from pathlib import Path
from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, ListWidgetFactory,
    LayoutFactory, FileDialogFactory,
)
from ui.styles import ColorCalculator, WindowStyle
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

    Цвет:
        BG_COLOR вычисляется в __init__ от цвета MainWindow через
        WindowStyle.resolve_parent_bg. Классовый BG_COLOR оставлен
        как fallback, если окно создаётся без родителя.
    """

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = "CompareWindow.compare_window"
    LOGGER_DOMAIN = "compare"

    # Fallback; реальный BG_COLOR вычисляется в __init__ от parent.
    BG_COLOR = (50, 50, 50)

    PIPELINE_BUTTONS = (
        "btn_prepare",
        "btn_stage1",
        "btn_stage2",
        "btn_stage3",
        "btn_report",
    )

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, mappings_storage=None,
                 log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            mappings_storage — CompareMappingsStorage из MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: вычисляет цвет от родителя, создаёт gating-состояние,
              сервис с callbacks, элементы и макет.
        """
        # Цвет — от родителя. Формула: r, 2g-2(g//5), b+2(b//5).
        parent_bg = WindowStyle.resolve_parent_bg(parent, (50, 50, 50))
        self.BG_COLOR = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r,
            g_fn=lambda g: 2 * g - 2 * (g // 5),
            b_fn=lambda b: b + 2 * (b // 5),
        )

        super().__init__(
            parent,
            title="Сравнение поставок",
            log_manager_v2=log_manager_v2,
        )

        # ---------- СОСТОЯНИЕ ----------
        self.supply_file = None
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

        # ---------- СЕРВИС ----------
        brands = parent.sellers_brands_service.get_brands_objects()
        brands_set = set()
        for b in brands:
            brands_set.add(b.name.lower())
            for key in b.keys:
                brands_set.add(key.lower())

        self.service = CompareService(
            log_manager_v2=log_manager_v2,
            brands_set=brands_set,
            mappings_storage=mappings_storage,
            stage1_reviewer=self._review_stage1,
            stage2_confirmer=self._confirm_stage2,
            stage3_selector=self._select_stage3,
        )

        # ---------- ЭЛЕМЕНТЫ: описание ----------
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
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )

        # ---------- ЭЛЕМЕНТЫ: путь ----------
        # path_selector создаётся в BaseServiceWindow.
        # Ширина: 220 + 10 + 220 = 450 — под ряд колонок.
        self.path_selector.setFixedWidth(450)

        # ---------- ЭЛЕМЕНТЫ: файл поставки ----------
        (self.file_row,
         self.btn_choose_file,
         self.file_label) = self._create_file_picker_row(
            "Выбрать Лист сверки",
            "last_compare_supply_dir",
            "Выберите Excel-файл листа поставки",
            FileDialogFactory.SUPPORTED_FILES_FILTER,
        )
        # Ширины под path_selector (450): 220 + 5 + 225 = 450.
        self.btn_choose_file.setFixedWidth(220)
        self.file_label.setFixedWidth(225)
        self.btn_choose_file.clicked.connect(self.select_supply_file)

        # ---------- ЭЛЕМЕНТЫ: список поставок ----------
        self.list_supply = ListWidgetFactory.create_file_list_widget(
            self,
            fixed_width=220,
            fixed_height=200,
            bg_color=(30, 20, 35, 0.3),
            text_color=None,
            font_size=10,
        )

        # ---------- ЭЛЕМЕНТЫ: кнопки ----------
        _action_configs = [
            ("btn_prepare", "Подготовить для работы",
             (30, 50, 100, 0.8), "8px 16px", (220, 35)),
            ("btn_stage1", "Этап 1 (жёсткая сверка)",
             (30, 80, 100, 0.8), "8px 16px", (220, 35)),
            ("btn_stage2", "Этап 2 (мягкая сверка)",
             (30, 110, 100, 0.8), "8px 16px", (220, 35)),
            ("btn_stage3", "Этап 3 (ручной выбор)",
             (30, 120, 100, 0.8), "8px 16px", (220, 35)),
            ("btn_report", "Сформировать отчёт",
             (90, 110, 160, 0.8), "8px 16px", (220, 35)),
            ("btn_add_supply", "Добавить файлы поставок",
             (70, 120, 160, 0.8), "6px 12px", (220, 30)),
            ("btn_mappings", "Сохранённые сопоставления",
             (70, 120, 160, 0.8), "8px 16px", (200, 30)),
        ]
        _action_handlers = {
            "btn_prepare": "on_prepare",
            "btn_stage1": "on_stage1",
            "btn_stage2": "on_stage2",
            "btn_stage3": "on_stage3",
            "btn_report": "on_generate_report",
            "btn_add_supply": "select_supply_files",
            "btn_mappings": "_open_mappings_window",
        }
        ButtonFactory.create_buttons_from_config(
            self, _action_configs, _action_handlers,
        )

        # ---------- МАКЕТ ----------
        # Левая колонка: step_label, кнопки этапов.
        # Правая колонка: btn_add_supply, list_supply.
        box = LayoutFactory.create_service_box(
            self,
            path_selector=self.path_selector,
            status_label=self.status_label,
            left_buttons=[
                self.btn_prepare, self.btn_stage1,
                self.btn_stage2, self.btn_stage3,
                self.btn_report,
            ],
            right_items=[self.btn_add_supply, self.list_supply],
            file_row=self.file_row,
            right_stretch_top=True,
        )

        page = self._add_service_page(
            self.instruction_label, box, accumulate_row=None,
        )

        # Кнопка «Сохранённые сопоставления» — перед status_log.
        mappings_row = LayoutFactory.create_row(
            self, self.btn_mappings, alignment=Qt.AlignCenter,
        )
        page.insertWidget(page.count() - 1, mappings_row)

        # Стартовое состояние кнопок.
        self._update_buttons_state()
        self.set_info("Окно сравнения поставок готово к работе.")

        if self.logger:
            self.logger.debug("CompareWindow.__init__: окно инициализировано")

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
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

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: CALLBACK'И UI
    # ============================================================

    def _on_supply_file_selected(self, path: str) -> None:
        """Сохраняет путь в self.supply_file и пишет в лог."""
        self.supply_file = path
        self.set_info(f"Выбран файл поставки: {Path(path).name}")

    def _review_stage1(self, pairs) -> list:
        """Открывает Stage1ReviewDialog в UI-потоке."""
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
        """Открывает ConfirmMatchDialog в UI-потоке."""
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
        """Открывает ManualMatchDialog в UI-потоке."""
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
    # ПРИВАТНЫЕ МЕТОДЫ: GATING
    # ============================================================

    def _update_buttons_state(self) -> None:
        """Включает/выключает кнопки по self._state."""
        st = self._state
        self.btn_prepare.setEnabled(True)
        self.btn_stage1.setEnabled(st["prepared"])
        self.btn_stage2.setEnabled(st["stage1_done"])
        self.btn_stage3.setEnabled(st["stage2_done"])
        self.btn_report.setEnabled(st["stage3_done"])

    def _maybe_unlock_report(self) -> None:
        """Разрешает отчёт, если сопоставлять больше нечего."""
        if not self._state["prepared"]:
            return
        if not self.service.supply_items or not self.service.candidates:
            self._state["stage3_done"] = True
            self._update_buttons_state()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ОБВЯЗКИ ШАГОВ
    # ============================================================

    def _prepare_pipeline(self, target_dir, sellers,
                          supply_file, supply_files) -> None:
        """Тело шага подготовки. Выполняется в фоновом потоке."""
        self.service.copy_supply_sheet(supply_file, target_dir)
        self.service.build_consolidated_supply(supply_files, target_dir)
        self.service.load_data()

    def _after_prepare(self) -> None:
        """Вызывается в UI-потоке после успеха подготовки."""
        self._state["prepared"] = True
        self._update_buttons_state()
        self.set_status("Подготовка завершена. Нажмите Этап 1")

    def _stage1_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 1. Выполняется в фоновом потоке."""
        self.service.run_stage1()

    def _after_stage1(self) -> None:
        """UI-поток после успеха этапа 1."""
        self._state["stage1_done"] = True
        self._update_buttons_state()
        self._maybe_unlock_report()
        self.set_status("Этап 1 завершён. Нажмите Этап 2")

    def _stage2_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 2. Выполняется в фоновом потоке."""
        self.service.run_stage2()

    def _after_stage2(self) -> None:
        """UI-поток после успеха этапа 2."""
        self._state["stage2_done"] = True
        self._update_buttons_state()
        self._maybe_unlock_report()
        self.set_status("Этап 2 завершён. Нажмите Этап 3")

    def _stage3_pipeline(self, target_dir, sellers) -> None:
        """Тело шага 3. Выполняется в фоновом потоке."""
        self.service.run_stage3()

    def _after_stage3(self) -> None:
        """UI-поток после успеха этапа 3."""
        self._state["stage3_done"] = True
        self._update_buttons_state()
        self.set_status("Все этапы завершены. Сформируйте отчёт")

    def _generate_report_pipeline(self, target_dir, sellers) -> None:
        """Тело шага отчёта. Выполняется в фоновом потоке."""
        self.service.generate_report(target_dir)
        self.service.save_mappings()

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ХУКИ БАЗОВОГО КЛАССА
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
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def cleanup(self) -> None:
        """Сброс состояния окна при закрытии.

        Вход: нет.
        Выход: нет.
        Роль: вызывается из базового closeEvent. Сбрасывает
              supply_file и очищает list_supply.
        """
        self.supply_file = None
        self.list_supply.clear_files()