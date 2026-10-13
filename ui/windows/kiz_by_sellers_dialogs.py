"""
Диалог распределения BestMark-файла по продавцам.

Содержит KizBySellersDialog — модальный диалог выбора исходного
файла и продавца-получателя. Запускает KizBySellersService в
фоновом потоке, показывает уведомление по завершении.

Роль в программе:
    Открывается из KizBySellersWindow по кнопке «Распределить
    продажи». Продавцы передаются при создании — из
    KizBySellersWindow._current_sellers.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout

from ui.base.base_edit_dialog import BaseEditDialog
from ui.factories.factories import (
    ButtonFactory, LabelFactory, InputWidgetFactory,
    FileDialogFactory, ThreadFactory,
)
from ui.styles import ColorCalculator, WindowStyle
from ui.windows.message_dialog import NotificationDialog
from services.kiz_by_sellers_service import KizBySellersService

class KizBySellersDialog(BaseEditDialog):
    """Модальный диалог распределения BestMark-файла.

    Роль:
        Выбор исходного файла + продавца-получателя. Кнопка
        «Распределить продажи» активируется только когда выбраны
        оба. Запуск сервиса — в фоновом потоке; результат
        показывается уведомлением.

    Атрибуты класса:
        LOGGER_SOURCE, LOGGER_DOMAIN — для создания логгера в
        BaseEditDialog.__init__. Без них self.logger остаётся None
        и debug-сообщения падают.
    """

    LOGGER_SOURCE = "KizBySellersDialog.kiz_by_sellers_dialogs"
    LOGGER_DOMAIN = "sales"

    def __init__(self, parent=None, log_manager_v2=None, sellers=None):
        """Конструктор.

        Вход:
            parent — родительское окно (KizBySellersWindow).
            log_manager_v2 — LogManagerV2 или None.
            sellers — список Seller. None → [].

        Роль: вычисляет bg_color от родителя, сохраняет состояние
              (файл, продавец), вызывает super().
        """
        self._log_manager_v2 = log_manager_v2
        self._sellers = sellers or []
        self._source_file: str | None = None
        self._selected_seller = None

        parent_bg = WindowStyle.resolve_parent_bg(parent, (40, 50, 60))
        self.bg_color = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: (2 * r + r // 5)//2,
            g_fn=lambda g: g - g // 5,
            b_fn=lambda b: b//2,
            alpha=0.95,
        )

        super().__init__(
            parent=parent,
            title="Распределить продажи",
            bg_color=self.bg_color,
            close_button=True,
            ok_cancel=False,
            draggable=True,
            close_on_click_outside=False,
            modal=True,
            center=True,
            width=500,
            height=180,
            log_manager_v2=log_manager_v2,
        )

        if self.logger:
            self.logger.debug("KizBySellersDialog.__init__: старт")

    # ---------- Сборка содержимого ----------

    def _build_content(self, layout) -> None:
        """Собирает содержимое диалога.

        Вход: layout — QVBoxLayout, созданный setup_dialog_frame.
        Роль: заголовок, строка выбора файла, комбобокс продавцов,
              кнопка запуска (изначально disabled).
        """
        element_bg = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - r // 5,
            g_fn=lambda g: g - g // 5,
            b_fn=lambda b: b - b // 5,
            alpha=1.0,
        )

        layout.addWidget(
            LabelFactory.create_header_label(
                self, "Распределить продажи",
            )
        )

        row = QHBoxLayout()
        self._file_btn = ButtonFactory.create_button(
            self, "...", element_bg, fixed_size=(35, 28),
        )
        self._file_btn.clicked.connect(self._on_pick_file)
        row.addWidget(self._file_btn)

        self._file_label = LabelFactory.create_label(
            self, "Файл не выбран",
            bg_color=element_bg,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        row.addWidget(self._file_label, stretch=1)
        layout.addLayout(row)

        self._combo = InputWidgetFactory.create_combo_box(
            self, items=[s.name for s in self._sellers],
            bg_color=element_bg,
        )
        self._combo.currentIndexChanged.connect(self._on_seller_changed)
        layout.addWidget(self._combo)

        self._btn_distribute = ButtonFactory.create_button(
            self, "Распределить продажи", element_bg,
        )
        self._btn_distribute.clicked.connect(self._on_distribute)
        self._btn_distribute.setEnabled(False)
        layout.addWidget(self._btn_distribute)

    # ---------- Обработчики ----------

    def _on_pick_file(self) -> None:
        """Открывает диалог выбора BestMark-файла.

        Роль: стартовая папка — target_dir родительского окна
              (если задан). Обновляет лейбл и состояние кнопки.
        """
        parent_win = self.parent()
        start_dir = (
            parent_win.target_dir
            if parent_win and getattr(parent_win, "target_dir", None)
            else None
        )
        path = FileDialogFactory.open_file_dialog(
            self, "Выберите файл BestMark",
            default_dir=start_dir, filter="Excel (*.xlsx)",
        )
        if not path:
            return
        self._source_file = path
        self._file_label.setText(Path(path).name)
        if self.logger:
            self.logger.debug(f"Выбран файл: {Path(path).name}")
        self._update_button_state()

    def _on_seller_changed(self, index) -> None:
        """Реакция на выбор продавца в комбобоксе.

        Вход: index — индекс выбранного элемента.
        Роль: сохраняет Seller или None, обновляет кнопку.
        """
        if 0 <= index < len(self._sellers):
            self._selected_seller = self._sellers[index]
            if self.logger:
                self.logger.debug(
                    f"Выбран продавец: {self._selected_seller.name}"
                )
        else:
            self._selected_seller = None
        self._update_button_state()

    def _update_button_state(self) -> None:
        """Включает кнопку, когда выбраны и файл, и продавец.

        Роль: единая точка пересчёта состояния кнопки. Вызывается
              из обработчиков файла и продавца.
        """
        enabled = (
            bool(self._source_file)
            and self._selected_seller is not None
        )
        self._btn_distribute.setEnabled(enabled)
        if self.logger:
            self.logger.debug(
                f"Кнопка 'Распределить' → {enabled}"
            )

    def _on_distribute(self) -> None:
        """Запускает сервис распределения в фоновом потоке.

        Роль: блокирует кнопку, создаёт KizBySellersService,
              делегирует запуск в ThreadFactory.run_in_thread.
              target_dir берётся у родительского окна.
        """
        if not self._source_file or self._selected_seller is None:
            return
        parent_win = self.parent()
        target_dir = parent_win.target_dir
        if self.logger:
            self.logger.debug(
                f"_on_distribute: старт, "
                f"seller={self._selected_seller.name}, "
                f"target_dir={target_dir}"
            )
        service = KizBySellersService(
            self._log_manager_v2, self._sellers,
        )
        self._btn_distribute.setEnabled(False)
        ThreadFactory.run_in_thread(
            target_func=service.distribute,
            args=(target_dir, self._source_file, self._selected_seller),
            on_finished=self._on_finished,
            error_callback=self._on_error,
        )

    def _on_finished(self, result) -> None:
        """Обработчик успешного завершения фонового потока.

        Вход: result — dict из KizBySellersService.distribute.
        Роль: ok → notify + accept. Иначе → notify об ошибке,
              кнопка снова активна.
        """
        if result.get("status") == "ok":
            NotificationDialog.notify(
                parent=self.parent(),
                text=(
                    f"Распределение завершено. КИЗов записано: "
                    f"{result.get('kiz_written', 0)}"
                ),
                bg_color=self.bg_color,
                title_text="Готово",
            )
            if self.logger:
                self.logger.debug(
                    f"Распределение завершено: {result}"
                )
            self.accept()
        else:
            if self.logger:
                self.logger.debug(
                    f"Распределение вернуло статус: "
                    f"{result.get('status')}, "
                    f"ошибка: {result.get('error')}"
                )
            NotificationDialog.notify(
                parent=self.parent(),
                text=(
                    f"Распределение не выполнено: "
                    f"{result.get('error')}"
                ),
                bg_color=self.bg_color,
                title_text="Ошибка",
            )
            self._btn_distribute.setEnabled(True)

    def _on_error(self, msg) -> None:
        """Обработчик исключения в фоновом потоке.

        Вход: msg — строка исключения.
        Роль: debug + notify + разблокировка кнопки.
        """
        if self.logger:
            self.logger.debug(f"Ошибка распределения: {msg}")
        NotificationDialog.notify(
            parent=self.parent(),
            text=f"Ошибка распределения: {msg}",
            bg_color=self.bg_color,
            title_text="Ошибка",
        )
        self._btn_distribute.setEnabled(True)