"""
Окно «Подготовка возвратов в оборот».

Назначение:
    Пайплайн из трёх шагов: подготовка (фильтрация исходного файла),
    выгрузка КИЗов для возврата, подготовка КИЗов для передачи между
    продавцами. Плюс операция аккумуляции продаж — в базовом классе.

Роль в программе:
    Открывается из MainWindow. Наследник BaseServiceWindow:
    set_status/set_info/_precheck_target_dir/closeEvent/
    on_accumulate_sales — унаследованы, окно отвечает только за
    свою раскладку и обработчики шагов.

Структура файла:
    КОНСТАНТЫ → ИНИЦИАЛИЗАЦИЯ → ОБРАБОТЧИКИ КНОПОК →
    ПРИВАТНЫЕ МЕТОДЫ → ХУКИ → ВЗАИМОДЕЙСТВИЕ С ОКНОМ.
"""

from PySide6.QtCore import Qt, Slot

from ui.base.base_service_window import BaseServiceWindow
from ui.factories.factories import (
    ButtonFactory, LabelFactory, LayoutFactory,
)
from ui.styles import ColorCalculator, WindowStyle
from services.returns_service import (
    ReturnsPreparationService, KizExportService, KizTransferService,
)
from ui.windows.message_dialog import MessageDialog, NotificationDialog
from ui.windows.returns_dialogs import PriorityResolutionDialog
from utils.log_tools.decorators import log_button_action


class ReturnsWindow(BaseServiceWindow):
    """Окно пайплайна возвратов.

    Роль:
        Объединяет три шага обработки возвратов. Каждый шаг —
        отдельный сервис, запускается в фоновом потоке через
        BaseServiceWindow._run_async_step. Логи шагов идут в
        status_log (унаследован); короткие подсказки — в
        status_label (унаследован).

    Цвет:
        BG_COLOR вычисляется в __init__ от цвета MainWindow через
        WindowStyle.resolve_parent_bg. Классовый BG_COLOR оставлен
        как fallback, если окно создаётся без родителя.
    """

    # ============================================================
    # КОНСТАНТЫ
    # ============================================================

    LOGGER_SOURCE = "ReturnsWindow.returns_window"
    LOGGER_DOMAIN = "returns"

    # Fallback; реальный BG_COLOR вычисляется в __init__ от parent.
    BG_COLOR = (50, 50, 50)

    # Кнопки, блокируемые на время шага пайплайна.
    # btn_accumulate сюда не входит — это отдельная операция.
    PIPELINE_BUTTONS = (
        "btn_choose_file",
        "btn_prepare",
        "btn_export_kiz",
        "btn_prepare_transfer",
    )

    # ============================================================
    # ИНИЦИАЛИЗАЦИЯ
    # ============================================================

    def __init__(self, parent=None, log_manager_v2=None):
        """Конструктор.

        Вход:
            parent — MainWindow.
            log_manager_v2 — LogManagerV2 или None.

        Роль: вычисляет цвет от родителя, строит состояние,
              элементы и макет. Порядок блоков: состояние →
              элементы → макет.
        """
        # Цвет — от родителя. Формула: r+2(r//5), g+g//5, b+2(b//5).
        parent_bg = WindowStyle.resolve_parent_bg(parent, (50, 50, 50))
        self.BG_COLOR = ColorCalculator.derive(
            parent_bg,
            r_fn=lambda r: r *2 ,
            g_fn=lambda g: g + g // 3,
            b_fn=lambda b: b + 2 * (b // 5),
        )

        super().__init__(
            parent,
            title="Подготовка возвратов в оборот",
            log_manager_v2=log_manager_v2,
        )

        # ---------- СОСТОЯНИЕ ----------
        self.source_file = None

        # ---------- ЭЛЕМЕНТЫ: описание ----------
        self.header_label = LabelFactory.create_label(
            self,
            text=(
                "Подготовка возвратов\n"
                "Подготовь файл, он должен быть определенного формата\n"
                "Прогони коды через BestMark и сделай импорт в Excell\n"
                "С этим файлом всё работать будет\n"
                "Прежде чем продавать в ЭДО верни КИЗы в оборот"
            ),
            bg_color=(35, 50, 60, 0),
            padding="6px",
            border_radius=5,
            alignment=Qt.AlignCenter,
            font_size=14,
            word_wrap=True,
        )

        # ---------- ЭЛЕМЕНТЫ: файл возвратов ----------
        (self.file_row,
         self.btn_choose_file,
         self.file_label) = self._create_file_picker_row(
            "Выбрать файл",
            "last_returns_dir",
            "Выберите Excel-файл с возвратами",
            "Excel (*.xlsx)",
            button_color=(120, 90, 120, 0.8),
        )

        self.btn_choose_file.setFixedWidth(120)
        self.file_label.setFixedWidth(190)
        self.btn_choose_file.clicked.connect(self.select_source_file)

        # ---------- ЭЛЕМЕНТЫ: путь ----------
        # path_selector создаётся в BaseServiceWindow.
        self.path_selector.setFixedWidth(315)

        # ---------- ЭЛЕМЕНТЫ: кнопки шагов ----------
        _action_configs = [
            ("btn_prepare", "Подготовка",
             (100, 50, 100), "6px 12px", (150, 35)),
            ("btn_export_kiz", "Для возврата",
             (130, 50, 100), "8px 16px", (150, 35)),
            ("btn_prepare_transfer", "Для передачи",
             (100, 50, 70), "8px 16px", (150, 35)),
        ]
        _action_handlers = {
            "btn_prepare": "on_prepare",
            "btn_export_kiz": "on_export_kiz",
            "btn_prepare_transfer": "on_prepare_transfer",
        }
        ButtonFactory.create_buttons_from_config(
            self, _action_configs, _action_handlers,
        )

        # Гейтинг: шаги 2 и 3 недоступны до подготовки.
        self.btn_export_kiz.setEnabled(False)
        self.btn_prepare_transfer.setEnabled(False)

        # ---------- МАКЕТ ----------
        box = LayoutFactory.create_service_box(
            self,
            path_selector=self.path_selector,
            status_label=self.status_label,
            left_buttons=[self.btn_prepare],
            right_items=[self.btn_export_kiz, self.btn_prepare_transfer],
            file_row=self.file_row,
            right_stretch_top=True,
        )

        self._add_service_page(
            self.header_label, box, self._create_accumulate_row(),
        )

    # ============================================================
    # ОБРАБОТЧИКИ КНОПОК
    # ============================================================

    @log_button_action(
        "btn_choose_file",
        "Ошибка при выборе файла возвратов: {e}",
    )
    def select_source_file(self) -> None:
        """Открывает диалог выбора исходного файла возвратов.

        Роль: тонкая обёртка над _select_single_file. Путь
              сохраняется в self.source_file через callback.
        """
        self._select_single_file(
            config_key="last_returns_dir",
            title="Выберите Excel-файл с возвратами",
            filter="Excel (*.xlsx)",
            label_widget=self.file_label,
            on_success=self._on_source_file_selected,
        )

    @log_button_action("btn_prepare", "Ошибка в on_prepare: {e}")
    def on_prepare(self) -> None:
        """Шаг 1: подготовка — фильтрация исходного файла возвратов."""
        if not self._precheck_target_dir():
            return
        if not self.source_file:
            self.set_status("Сначала выберите файл")
            return

        service = ReturnsPreparationService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_prepare: ReturnsPreparationService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.prepare,
            kwargs={"source_file": self.source_file},
            start_message="Идёт подготовка...",
            finish_message="Подготовка завершена.",
            step_name="on_prepare",
            enable_after=self.btn_export_kiz,
            on_success=self._on_prepare_finished,
        )

    @log_button_action("btn_export_kiz", "Ошибка в on_export_kiz: {e}")
    def on_export_kiz(self) -> None:
        """Шаг 2: выгрузка КИЗов для возврата."""
        if not self._precheck_target_dir():
            return

        service = KizExportService(
            self.main_window.kiz_validator,
            self.log_manager_v2,
            overwrite_requester=self._request_export_mode,
        )
        if self.logger:
            self.logger.debug("on_export_kiz: KizExportService создан")

        self._run_async_step(
            service=service,
            target_method=service.export,
            kwargs={},
            start_message="Выгрузка КИЗов...",
            finish_message="Выгрузка КИЗов завершена.",
            step_name="on_export_kiz",
            enable_after=self.btn_prepare_transfer,
        )

    @log_button_action(
        "btn_prepare_transfer",
        "Ошибка в on_prepare_transfer: {e}",
    )
    def on_prepare_transfer(self) -> None:
        """Шаг 3: подготовка КИЗов для передачи между продавцами."""
        if not self._precheck_target_dir():
            return

        service = KizTransferService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_prepare_transfer: KizTransferService создан"
            )

        self._run_async_step(
            service=service,
            target_method=service.prepare_transfer,
            kwargs={},
            start_message="Подготовка передач КИЗов...",
            finish_message="Подготовка передач КИЗов завершена.",
            step_name="on_prepare_transfer",
            enable_after=None,
        )

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: CALLBACK'И И ДИАЛОГИ
    # ============================================================

    def _on_source_file_selected(self, path: str) -> None:
        """Callback выбора файла возвратов.

        Вход: path — выбранный путь.
        Выход: нет.
        Роль: сохраняет self.source_file и подсказывает шаг.
        """
        self.source_file = path
        self.set_status("Файл выбран. Нажмите «Подготовка».")

    def _on_prepare_finished(self, result) -> None:
        """Callback on_success шага prepare.

        Вход:
            result — dict {new, old, dup, saved} или None.

        Роль: если saved == 0 — показать NotificationDialog.
              Во всех остальных случаях (в том числе result is None) —
              ничего не делаем, сводка уже ушла в status_log.
        """
        if not result:
            return
        saved = result.get("saved", 0)
        if saved == 0:
            NotificationDialog.notify(
                parent=self,
                text=(
                    "Новых КИЗов не обнаружено — все строки "
                    "исходного файла уже были в прошлых отчётах. "
                    "Файл возвратов оставлен без изменений."
                ),
                title_text="Нет новых КИЗов",
                bg_color=self.bg_color,
            )

    def _request_priority_resolution(self, conflicts) -> dict:
        """Callback от KizTransferService: разрешить конфликты брендов.

        Вход:
            conflicts — {brand_key: {"raw_brand": str,
                                     "candidates": [Seller]}}.

        Выход:
            {brand_key: Seller}.

        Роль: делегирует открытие диалога в UI-поток через
              _run_in_ui_blocking. Вызывается из фонового потока
              сервиса — прямой показ QDialog там недопустим.
        """
        if self.logger:
            self.logger.debug(
                f"_request_priority_resolution: "
                f"конфликтов {len(conflicts)}"
            )
        return self._run_in_ui_blocking(
            lambda: self._open_priority_dialog(conflicts)
        )

    @Slot(object)
    def _open_priority_dialog(self, conflicts) -> dict:
        """Открывает PriorityResolutionDialog в UI-потоке.

        Вход:
            conflicts — {brand_key: {"raw_brand": str,
                                     "candidates": [Seller]}}.

        Выход:
            {brand_key: Seller} — выбранные продавцы для каждого
            конфликтного бренда.
        """
        dialog = PriorityResolutionDialog(
            parent=self,
            conflicts=conflicts,
            log_manager_v2=self.log_manager_v2,
        )
        dialog.exec()
        return dialog.get_resolution()

    def _request_export_mode(self) -> bool | None:
        """Callback от KizExportService: спросить режим записи .txt.

        Выход:
            True — перезаписать.
            False — дополнить.
            None — отмена.

        Роль: вызывается из фонового потока сервиса. Открытие
              диалога делегируется в UI-поток через
              _run_in_ui_blocking.
        """
        return self._run_in_ui_blocking(self._show_export_mode_dialog)

    @Slot()
    def _show_export_mode_dialog(self) -> bool | None:
        """Открывает диалог выбора режима записи в UI-потоке.

        Выход:
            True / False / None — см. _request_export_mode.
            None — пользователь отменил или аварийное закрытие.

        Роль: три кнопки. «Перезаписать» → True, «Дополнить» →
              False, «Отмена» → None. Ключ "cancel" возвращается
              кнопкой «Отмена» (последняя, привязана к Esc).
              None также — при аварийном закрытии (Alt+F4).
        """
        text = (
            "Уже имеются файлы для возвратов. Если предыдущие КИЗы "
            "ты в оборот вернул, то нужно перезаписать. Иначе дополним "
            "файлы новыми для того чтоб сразу всё ввести в оборот. "
            "\n\n====   Итак, вопрос: Нужна ли перезапись?   ===="
        )
        buttons = [
            ("Перезаписать", "overwrite", None),
            ("Дополнить", "append", None),
            ("Отмена", "cancel", None),
        ]
        result = MessageDialog.question(
            self,
            text=text,
            buttons=buttons,
            title_text="Режим записи",
            bg_color=self.bg_color,
        )
        if result == "overwrite":
            return True
        if result == "append":
            return False
        return None

    # ============================================================
    # ПРИВАТНЫЕ МЕТОДЫ: ХУКИ БАЗОВОГО КЛАССА
    # ============================================================

    def _current_sellers(self) -> list:
        """Возвращает список продавцов с брендами.

        Вход: нет.
        Выход: list[Seller] с заполненными .brands.
        Роль: переопределение базового — для возвратов нужны
              продавцы с полной информацией о брендах.
        """
        return (
            self.main_window.sellers_brands_service
            .get_sellers_with_brands()
        )

    def _on_target_dir_changed_hook(self) -> None:
        """Сброс кнопок шагов 2–3 при смене папки.

        Вход: нет.
        Выход: нет.
        Роль: хук вызывается базовым _on_target_dir_changed после
              очистки логов и обновления target_dir.
        """
        self.btn_export_kiz.setEnabled(False)
        self.btn_prepare_transfer.setEnabled(False)

    # ============================================================
    # ВЗАИМОДЕЙСТВИЕ С ОКНОМ
    # ============================================================

    def cleanup(self) -> None:
        """Сброс состояния окна при закрытии.

        Вход: нет.
        Выход: нет.
        Роль: вызывается из базового closeEvent. Сбрасывает
              source_file и текст лейбла файла.
        """
        self.source_file = None
        self.file_label.setText("Файл не выбран")
