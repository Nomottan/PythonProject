"""
Окно «Продажи КИЗов».

Аккумуляция и распределение файлов продаж:
    «Собрать продажи» — аккумуляция из всех источников
    (ЧЗ_МП, Возвраты, ранее распределённые) в единую папку.
    «Распределить продажи» — выбор BestMark-файла и разнесение
    строк по продавцам-владельцам.

Роль в программе:
    Открывается из MainWindow. Наследник BaseServiceWindow:
    set_status/set_info/_precheck_target_dir/closeEvent/
    on_accumulate_sales — унаследованы. Окно отвечает за раскладку
    и обработчик открытия диалога распределения.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout
from ui.styles import ColorCalculator, WindowStyle
from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
)
from ui.styles import ColorCalculator
from ui.widgets.path_selector import PathSelector
from ui.windows.kiz_by_sellers_dialogs import KizBySellersDialog
from utils.log_tools.decorators import log_button_action

class KizBySellersWindow(BaseServiceWindow):
    """Окно аккумуляции и распределения продаж.

    Роль:Q
        Объединяет два действия: аккумуляцию продаж (кнопка
        унаследована от BaseServiceWindow) и распределение
        BestMark-файла (диалог KizBySellersDialog).
    """

    LOGGER_SOURCE = "KizBySellersWindow.kiz_by_sellers_window"
    LOGGER_DOMAIN = "sales"

    BG_COLOR = (50, 50, 50)
    PIPELINE_BUTTONS = ("btn_accumulate", "btn_open_distribute")

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: строит раскладку, подключает сигналы.
        """
        parent_bg = WindowStyle.resolve_parent_bg(parent, (50, 50, 50))
        self.BG_COLOR = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: 2 * r + r // 5,
            g_fn=lambda g: g - g // 5,
            b_fn=lambda b: b,
        )
        super().__init__(
            parent,
            title="Продажи КИЗов",
            log_manager_v2=log_manager_v2,
        )

        # ---------- ОПИСАНИЕ (D4) ----------
        desc_label = LabelFactory.create_label(
            self,
            text=(
                "Аккумуляция и распределение файлов продаж:\n"
                "«Собрать продажи» — собрать файлы продаж из всех "
                "источников (ЧЗ_МП, Возвраты, ранее распределённые) "
                "в единую папку Продажи_{date}.\n"
                "«Распределить продажи» — выбрать файл BestMark и "
                "разнести его строки по продавцам-владельцам, "
                "сформировав файлы продаж."
            ),
            bg_color=(0, 0, 0, 0),
            padding="0px",
            alignment=Qt.AlignCenter,
            word_wrap=True,
        )

        # ---------- ВЫБОР ПАПКИ ----------
        self.path_selector = PathSelector(
            self,
            initial_path=self.target_dir,
            dialog_title="Выберите целевую папку",
        )
        self.path_selector.path_changed.connect(self._on_target_dir_changed)

        # ---------- КНОПКИ ----------
        self.btn_accumulate = ButtonFactory.create_button(
            self, "Собрать продажи", (60, 90, 120, 0.8),
            padding="8px 16px", fixed_size=(180, 35),
        )
        # on_accumulate_sales унаследован от BaseServiceWindow.
        self.btn_accumulate.clicked.connect(self.on_accumulate_sales)

        self.btn_open_distribute = ButtonFactory.create_button(
            self, "Распределить продажи", (50, 120, 120, 0.8),
            padding="8px 16px", fixed_size=(180, 35),
        )
        self.btn_open_distribute.clicked.connect(
            self.on_open_distribute_dialog,
        )

        # ---------- МАКЕТ ----------
        center = QVBoxLayout()
        center.setSpacing(10)
        center.setAlignment(Qt.AlignCenter)
        center.addWidget(desc_label)
        center.addWidget(self.path_selector)
        center.addWidget(self.status_label)
        center.addWidget(LayoutFactory.create_row(
            self, self.btn_accumulate, self.btn_open_distribute,
            spacing=8,
        ))
        center.addWidget(self.status_log)
        center.addStretch(1)
        self.main_layout.addLayout(center)

        if self.logger:
            self.logger.debug(
                "KizBySellersWindow.__init__: окно инициализировано"
            )

    # ============================================================
    # ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _on_target_dir_changed_hook(self) -> None:
        """Хук смены целевой папки.

        Вход: нет.
        Выход: нет.
        Роль: обе кнопки всегда доступны — сброс не требуется.
        """
        pass

    def cleanup(self) -> None:
        """Хук очистки при закрытии.

        Вход: нет.
        Выход: нет.
        Роль: специфичных данных нет — сбрасывать нечего.
        """
        if self.logger:
            self.logger.debug("KizBySellersWindow.cleanup")

    # ============================================================
    # ОБРАБОТЧИКИ
    # ============================================================

    @log_button_action(
        "btn_open_distribute", "Ошибка при открытии диалога: {e}",
    )
    def on_open_distribute_dialog(self) -> None:
        """Открывает диалог распределения BestMark-файла.

        Роль: проверяет target_dir, получает актуальный список
              продавцов, открывает модальный диалог. Продавцы
              передаются в диалог — он должен использовать
              те же данные, что использует окно.
        """
        if not self._precheck_target_dir():
            return

        sellers = self._current_sellers()
        if self.logger:
            self.logger.debug(
                f"on_open_distribute_dialog: продавцов {len(sellers)}"
            )

        dialog = KizBySellersDialog(
            parent=self,
            log_manager_v2=self.log_manager_v2,
            sellers=sellers,
        )
        dialog.exec()

        if self.logger:
            self.logger.debug(
                "on_open_distribute_dialog: диалог закрыт"
            )