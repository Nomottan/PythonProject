"""
Окно сравнения поставок.

Назначение:
    Пайплайн из шести шагов: подготовка (копия листа поставки +
    сборный файл + загрузка), три этапа сопоставления, отчёт.
    Каждый шаг — синхронный вызов метода CompareService; стадии
    сами открывают диалоги через callback'и, сервис при этом не
    знает про Qt.

Роль в программе:
    Открывается из MainWindow. Логгер окна создаётся в __init__,
    пишет сообщения от UI (с source="CompareWindow.compare_window").
    Логика прогона — в CompareService. Гейтинг кнопок — по self._state.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt

from ui.factories.factories import (
    ButtonFactory, LabelFactory, ListWidgetFactory, LayoutFactory,
    WindowFactory, FileDialogFactory, StatusLogFactory,
)
from ui.widgets.path_selector import PathSelector
from ui.windows.mappings_window import BrandMappingsWindow
from ui.windows.compare_dialogs import (
    Stage1ReviewDialog, ConfirmMatchDialog, ManualMatchDialog,
)
from utils.log_tools.decorators import log_button_action
from services.compare_service import CompareService


class CompareWindow(QMainWindow):
    """Окно сравнения листа поставки с фактическими поставками.

    Роль:
        Ведёт пользователя по шагам: подготовка → этап 1 → этап 2 →
        этап 3 → отчёт. Все шаги синхронные, в UI-потоке, потому
        что стадии открывают диалоги. Логи шагов идут в status_display,
        короткие подсказки — в status_label.

    Поля:
        service — CompareService с callbacks.
        logger — LoggerV2 окна или None.
        _state — gating-флаги: prepared, stage1_done, stage2_done,
                 stage3_done. Управляют доступностью кнопок между
                 шагами.
    """

    # Кнопки, блокируемые на время выполнения шага пайплайна.
    # btn_choose_file, btn_add_supply, btn_mappings — не входят:
    # они не относятся к самому пайплайну.
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
            mappings_storage — CompareMappingsStorage из MainWindow,
                               чтобы CompareService не создавал своё
                               хранилище через PathManager.
            log_manager_v2 — LogManagerV2 или None.

        Роль: создаёт логгер окна, gating-состояние, сервис с
              callback'ами, раскладку и подключает сигналы.
        """
        super().__init__(parent)
        self.main_window = parent

        # LoggerV2 окна — для собственных сообщений (без work_folder:
        # файловый канал пишут сервисы, у окна своей рабочей папки нет).
        self.log_manager_v2 = log_manager_v2
        self.logger = None
        if log_manager_v2 is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source="CompareWindow.compare_window",
                domain="compare",
            )
        if self.logger:
            self.logger.debug("CompareWindow.__init__: старт")

        # Переменные состояния.
        self.target_dir = parent.main_config.get("target_dir", None)
        self.supply_file = None
        self.supply_files = []
        self.bg_color = (50, 80, 70, 0.95)

        # Gating-состояние шагов.
        self._state = {
            "prepared":    False,
            "stage1_done": False,
            "stage2_done": False,
            "stage3_done": False,
        }

        # brands_set — набор ключей брендов из конфига.
        brands = parent.sellers_brands_service.get_brands_objects()
        brands_set = set()
        for b in brands:
            brands_set.add(b.name.lower())
            for key in b.keys:
                brands_set.add(key.lower())

        # Сервис с callback'ами. Диалоги окно открывает само —
        # сервис только сообщает, когда нужен ввод.
        self.service = CompareService(
            log_manager_v2=log_manager_v2,
            brands_set=brands_set,
            mappings_storage=mappings_storage,
            stage1_reviewer=self._review_stage1,
            stage2_confirmer=self._confirm_stage2,
            stage3_selector=self._select_stage3,
        )

        # Настройка окна.
        main_layout = WindowFactory.setup_child_window(
            self, "Сравнение поставок",
            bg_color=self.bg_color,
        )

        # ============================================================
        # ЭЛЕМЕНТЫ
        # ============================================================
        self.instruction_label = LabelFactory.create_label(
            self,
            text="Подготовка к сравнению поставок\n"
                 "Шаг 1: Выберите папку для сохранения результатов\n"
                 "Шаг 2: Выберите файл листа поставки (один Excel-файл)\n"
                 "Шаг 3: Добавьте файлы с фактическими поставками (можно несколько)\n"
                 "Шаг 4: Нажмите 'Подготовить для работы' – данные будут загружены\n"
                 "Шаг 5: Последовательно выполняйте этапы 1→2→3\n"
                 "Шаг 6: Сформируйте отчёт",
            bg_color=(0, 0, 0, 0),
            text_color="#c2c2c2",
            padding="0px",
            border_radius=0,
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )
        main_layout.addWidget(self.instruction_label)

        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите папку для результатов",
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)
        main_layout.addWidget(self.path_selector)

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
        main_layout.addWidget(file_row)

        # Две колонки: слева кнопки, справа список файлов поставок.
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

        self.list_supply = ListWidgetFactory.create_list_widget(
            self,
            fixed_width=220,
            fixed_height=200,
            horizontal_scroll=False,
            bg_color=(30, 20, 35, 0.3),
            text_color="#d4d4d4",
            font_size=10,
        )
        right_layout.addWidget(self.list_supply)
        right_layout.addStretch()

        columns_layout.addWidget(left_widget)
        columns_layout.addWidget(right_widget)
        main_layout.addLayout(columns_layout)

        # Кнопка «Сохранённые сопоставления».
        self.btn_mappings = ButtonFactory.create_button(
            self, "Сохранённые сопоставления", (70, 120, 160, 0.8),
            padding="8px 16px", fixed_size=(200, 30),
        )
        self.btn_mappings.clicked.connect(self._open_mappings_window)
        mappings_row = LayoutFactory.create_row(
            self, self.btn_mappings, alignment=Qt.AlignCenter,
        )
        main_layout.addWidget(mappings_row)

        # Короткая подсказка (set_status).
        self.status_label = LabelFactory.create_status_label(
            self, "Выберите папку и файлы",
        )
        main_layout.addWidget(self.status_label)

        # Прокручиваемый лог (set_info).
        self.status_display = StatusLogFactory.create_status_log(
            self, bg_color=self.bg_color,
            min_height=100, max_height=200,
        )
        main_layout.addWidget(self.status_display)

        # Стартовое состояние кнопок.
        self._update_buttons_state()

        self.set_info("Окно сравнения поставок готово к работе.")
        if self.logger:
            self.logger.debug("CompareWindow.__init__: окно инициализировано")

    # ============================================================
    # ПУБЛИЧНЫЕ КАНАЛЫ UI
    # ============================================================

    def set_status(self, msg: str) -> None:
        """Обновляет короткое сообщение в статусной строке.

        Вход: msg — текст.
        Выход: нет.
        Роль: единая точка обновления status_label. Вызывается
              из StatusHandler через active_child.set_status.
        """
        self.status_label.setText(msg)

    def set_info(self, msg: str) -> None:
        """Дописывает сообщение в прокручиваемый лог.

        Вход: msg — текст.
        Выход: нет.
        Роль: единая точка записи в status_display. Вызывается
              из InfoUIHandler через active_child.set_info.
        """
        self.status_display.append(msg)

    # ============================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ============================================================

    def _on_target_dir_changed(self, new_path) -> None:
        """Обработка смены целевой папки.

        Вход: new_path — новый путь.
        Роль: обновляет target_dir, пишет в main_config, сбрасывает
              gating (папка новая — подготовка не выполнена).
        """
        if self.logger:
            self.logger.debug(
                f"_on_target_dir_changed: новая папка {new_path}"
            )
        self.target_dir = new_path
        self.parent().main_config.set("target_dir", new_path)
        self._state = {
            "prepared":    False,
            "stage1_done": False,
            "stage2_done": False,
            "stage3_done": False,
        }
        self._update_buttons_state()
        self.set_status("Целевая папка обновлена.")

    def _precheck_target_dir(self) -> bool:
        """Проверяет, что выбрана целевая папка.

        Вход: нет.
        Выход:
            True — папка выбрана.
            False — папки нет, в status_label записано предупреждение.

        Роль: единая точка проверки target_dir для всех шагов.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return False
        return True

    def _update_buttons_state(self) -> None:
        """Включает/выключает кнопки по self._state.

        Вход: нет.
        Выход: нет.
        Роль: применяет gating-правила:
            btn_prepare    — всегда доступна.
            btn_stage1     — после «prepared».
            btn_stage2     — после «stage1_done».
            btn_stage3     — после «stage2_done».
            btn_report     — после «stage3_done».
        """
        st = self._state
        self.btn_prepare.setEnabled(True)
        self.btn_stage1.setEnabled(st["prepared"])
        self.btn_stage2.setEnabled(st["stage1_done"])
        self.btn_stage3.setEnabled(st["stage2_done"])
        self.btn_report.setEnabled(st["stage3_done"])

    def _set_pipeline_enabled(self, enabled: bool) -> None:
        """Блокирует/разблокирует все PIPELINE_BUTTONS.

        Вход: enabled — True — разблокировать по _state,
                         False — заблокировать всё.
        Выход: нет.
        Роль: на время шага пайплайна все кнопки недоступны; после —
              разблокируются согласно gating-состоянию.
        """
        if not enabled:
            for name in self.PIPELINE_BUTTONS:
                btn = getattr(self, name, None)
                if btn is not None:
                    btn.setEnabled(False)
        else:
            self._update_buttons_state()

    def _run_pipeline_step(self, *, step_name: str, fn, start_message: str,
                           finish_message: str, mark_key: str = None) -> None:
        """Выполняет один шаг пайплайна.

        Вход (все параметры именованные):
            step_name — префикс для логов.
            fn — callable без аргументов, тело шага.
            start_message — текст в status_label/status_log в начале.
            finish_message — текст при успехе.
            mark_key — какой флаг в self._state выставить после
                       успеха. None — ничего не выставлять.

        Выход: нет.

        Роль:
            Единая обвязка шагов окна: блокировка кнопок, запись
            короткого сообщения в status_label и подробного — в
            status_display, лог об ошибке через logger.critical.
            Шаг синхронный — стадии могут открывать диалоги.
        """
        self._set_pipeline_enabled(False)
        self.set_status(start_message)
        self.set_info(start_message)
        try:
            fn()
            self.set_status(finish_message)
            self.set_info(finish_message)
            if self.logger:
                self.logger.debug(f"{step_name}: шаг завершён")
            if mark_key is not None:
                self._state[mark_key] = True
        except Exception as e:
            self.set_status(f"Ошибка на шаге {step_name}: {e}")
            self.set_info(f"Ошибка на шаге {step_name}: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в {step_name}: {e}", can_influence=False,
                )
        finally:
            self._set_pipeline_enabled(True)

    # ============================================================
    # CALLBACK'И ДЛЯ CompareService
    # ============================================================

    def _review_stage1(self, pairs) -> list:
        """Открывает Stage1ReviewDialog и возвращает флаги keep.

        Вход: pairs — список (SupplyItem, Candidate).
        Выход: list[bool] — какие пары оставить.
        Роль: вызывается из Stage1.run в UI-потоке.
        """
        dialog = Stage1ReviewDialog(self, pairs)
        dialog.exec()
        return dialog.get_keep_flags()

    def _confirm_stage2(self, item, candidate, score: float,
                        remaining: int) -> bool:
        """Открывает ConfirmMatchDialog и возвращает подтверждение.

        Вход:
            item — SupplyItem.
            candidate — Candidate.
            score — схожесть.
            remaining — сколько товаров осталось.

        Выход: True — подтверждено, False — отклонено.
        """
        dialog = ConfirmMatchDialog(
            self,
            {"name": item.name, "count": item.count},
            {"name": candidate.name, "count": candidate.count},
            score,
            remaining,
        )
        dialog.exec()
        return dialog.get_result() == "confirmed"

    def _select_stage3(self, item, candidates, remaining: int) -> tuple:
        """Открывает ManualMatchDialog и возвращает выбор пользователя.

        Вход:
            item — SupplyItem.
            candidates — список доступных Candidate.
            remaining — сколько товаров в очереди.

        Выход:
            (selected_candidate_dict | None, skip_all: bool).

        Роль: превращает Candidate в dict {'name', 'count'} для
              диалога. Stage3.run сам найдёт Candidate по паре
              name + count — так диалог не таскает модель через Qt.
        """
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
        return dialog.get_result()

    # ============================================================
    # ОБРАБОТЧИКИ ВЫБОРА ФАЙЛОВ
    # ============================================================

    @log_button_action(
        "btn_choose_file",
        "Ошибка при выборе листа поставки: {e}",
    )
    def select_supply_file(self) -> None:
        """Открывает диалог выбора файла листа поставки.

        Роль: сохраняет путь в self.supply_file, имя — в file_label,
              папку — в main_config для следующего запуска.
        """
        start_dir = (
            self.parent().main_config.get("last_compare_supply_dir", None)
            or self.target_dir
            or str(Path.home())
        )
        file_path = FileDialogFactory.open_file_dialog(
            self, "Выберите Excel-файл листа поставки",
            default_dir=start_dir,
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER,
        )
        if file_path:
            self.supply_file = file_path
            self.file_label.setText(Path(file_path).name)
            self.parent().main_config.set(
                "last_compare_supply_dir", str(Path(file_path).parent),
            )
            self.set_info(f"Выбран файл поставки: {Path(file_path).name}")
            if self.logger:
                self.logger.debug(
                    f"select_supply_file: выбран {Path(file_path).name}"
                )

    @log_button_action(
        "btn_add_supply",
        "Ошибка при выборе файлов поставок: {e}",
    )
    def select_supply_files(self) -> None:
        """Открывает диалог выбора файлов поставок.

        Роль: добавляет новые файлы к self.supply_files, дубликаты
              (по строке пути) не добавляются.
        """
        start_dir = (
            self.parent().main_config.get("last_compare_supplies_dir", None)
            or self.target_dir
            or str(Path.home())
        )
        files = FileDialogFactory.open_files_dialog(
            self, "Выберите файлы с поставками",
            default_dir=start_dir,
            filter=FileDialogFactory.SUPPORTED_FILES_FILTER,
        )
        if files:
            for f in files:
                if f not in self.supply_files:
                    self.supply_files.append(f)
                    self.list_supply.addItem(Path(f).name)
            first_file = Path(files[0])
            self.parent().main_config.set(
                "last_compare_supplies_dir", str(first_file.parent),
            )
            self.set_info(
                f"Добавлено {len(files)} файлов поставок. "
                f"Всего: {len(self.supply_files)}"
            )
            if self.logger:
                self.logger.debug(
                    f"select_supply_files: добавлено {len(files)}, "
                    f"итого {len(self.supply_files)}"
                )

    @log_button_action(
        "btn_mappings",
        "Ошибка при открытии окна сопоставлений: {e}",
    )
    def _open_mappings_window(self) -> None:
        """Открывает окно сохранённых сопоставлений.

        Роль: диалог синхронный, открывается модально. После
              закрытия — ничего не пересчитывается: изменения
              маппингов подхватятся при следующем run_stage1.
        """
        window = BrandMappingsWindow(
            parent=self,
            service=self.service,
            sellers_brands_service=self.main_window.sellers_brands_service,
        )
        window.exec()

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК ПАЙПЛАЙНА
    # ============================================================

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
        """Шаг 1: подготовка — копия листа + сборный файл + загрузка."""
        if not self._precheck_target_dir():
            return
        if not self.supply_file:
            self.set_status("Сначала выберите файл листа поставки")
            return
        if not self.supply_files:
            self.set_status("Добавьте хотя бы один файл с поставками")
            return

        self._run_pipeline_step(
            step_name="on_prepare",
            fn=self._prepare_fn,
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена. Можно переходить к этапу 1.",
            mark_key="prepared",
        )

    def _prepare_fn(self) -> None:
        """Тело шага подготовки.

        Роль: вызывает три операции сервиса последовательно.
              Все сообщения идут в status_display через set_info —
              тот же канал, что и раньше, только через публичный
              метод, а не через self.log().
        """
        copied_path = self.service.copy_supply_sheet(
            self.supply_file, self.target_dir,
        )
        self.set_info(f"  Копия создана: {copied_path}")

        consolidated_path = self.service.build_consolidated_supply(
            self.supply_files, self.target_dir,
        )
        self.set_info(f"  Сборный файл создан: {consolidated_path}")

        self.service.load_data()
        self.set_info(
            f"  Загружено товаров: {len(self.service.supply_items)}, "
            f"кандидатов: {len(self.service.candidates)}"
        )

    @log_button_action("btn_stage1", "Ошибка в on_stage1: {e}")
    def on_stage1(self) -> None:
        """Шаг 2: этап 1 — жёсткая сверка."""
        if not self._precheck_target_dir():
            return
        self._run_pipeline_step(
            step_name="on_stage1",
            fn=self.service.run_stage1,
            start_message="Этап 1 — жёсткая сверка...",
            finish_message="Этап 1 завершён.",
            mark_key="stage1_done",
        )
        # Если после этапа 1 не осталось товаров или кандидатов —
        # можно сразу формировать отчёт, минуя этапы 2 и 3.
        self._maybe_unlock_report()

    @log_button_action("btn_stage2", "Ошибка в on_stage2: {e}")
    def on_stage2(self) -> None:
        """Шаг 3: этап 2 — мягкая сверка."""
        if not self._precheck_target_dir():
            return
        self._run_pipeline_step(
            step_name="on_stage2",
            fn=self.service.run_stage2,
            start_message="Этап 2 — мягкая сверка...",
            finish_message="Этап 2 завершён.",
            mark_key="stage2_done",
        )
        self._maybe_unlock_report()

    @log_button_action("btn_stage3", "Ошибка в on_stage3: {e}")
    def on_stage3(self) -> None:
        """Шаг 4: этап 3 — ручной выбор."""
        if not self._precheck_target_dir():
            return
        self._run_pipeline_step(
            step_name="on_stage3",
            fn=self.service.run_stage3,
            start_message="Этап 3 — ручной выбор...",
            finish_message="Этап 3 завершён. Можно формировать отчёт.",
            mark_key="stage3_done",
        )

    def _maybe_unlock_report(self) -> None:
        """Разрешает отчёт, если сопоставлять больше нечего.

        Роль: после этапов 1 и 2 может оказаться, что supply_items
              или candidates пусты. Тогда этапы 2/3 бессмысленны,
              и логичнее сразу открыть кнопку «Сформировать отчёт».
              Флаг stage3_done выставляется принудительно.
        """
        if not self._state["prepared"]:
            return
        if not self.service.supply_items or not self.service.candidates:
            self._state["stage3_done"] = True
            self._update_buttons_state()

    @log_button_action("btn_report", "Ошибка в on_generate_report: {e}")
    def on_generate_report(self) -> None:
        """Шаг 5: формирование отчёта и сохранение сопоставлений."""
        if not self._precheck_target_dir():
            return

        def _fn() -> None:
            self.service.generate_report(self.target_dir)
            self.service.save_mappings()

        self._run_pipeline_step(
            step_name="on_generate_report",
            fn=_fn,
            start_message="Формирование отчёта...",
            finish_message="Отчёт и сопоставления сохранены.",
            mark_key=None,
        )

    # ============================================================
    # ЗАКРЫТИЕ ОКНА
    # ============================================================

    def cleanup(self) -> None:
        """Сброс состояния окна (файлы, списки)."""
        self.supply_file = None
        self.supply_files = []
        self.list_supply.clear()

    def closeEvent(self, event) -> None:
        """Обработка закрытия окна.

        Роль: чистит состояние, снимает active_child у родителя,
              принимает событие.
        """
        if self.logger:
            self.logger.debug("CompareWindow: closeEvent получен")
        self.cleanup()
        if self.parent() and hasattr(self.parent(), 'active_child'):
            self.parent().active_child = None
        event.accept()