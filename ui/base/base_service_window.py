"""
Базовое окно сервиса (ChzMP, Returns, Compare).

Содержит BaseServiceWindow — QMainWindow с единой инфраструктурой:
    - логгер V2 из LogManagerV2 по атрибутам класса;
    - status_label и status_log (публичные каналы для handler'ов);
    - target_dir и его смена через _on_target_dir_changed;
    - обвязка фонового шага пайплайна через ThreadFactory;
    - обвязка выбора одного файла и списка файлов с крестиками;
    - обвязка кнопки «Собрать продажи».

Роль в программе:
    Все три окна сервисов (ChzMPWindow, ReturnsWindow, CompareWindow)
    наследуются от BaseServiceWindow. Общая инфраструктура — здесь,
    специфика — в наследниках.
"""

from pathlib import Path

from PySide6.QtWidgets import QMainWindow

from ui.factories.factories import (
    LabelFactory, StatusLogFactory, WindowFactory,
    ThreadFactory, FileDialogFactory,
)
from ui.styles import ColorCalculator
from utils.log_tools.decorators import log_button_action
from services.sales_accumulator import SalesAccumulatorService


class BaseServiceWindow(QMainWindow):
    """Базовое окно сервиса.

    Роль:
        Инфраструктура для ChzMPWindow/ReturnsWindow/CompareWindow.
        Наследники задают атрибуты класса и переопределяют хуки.

    Атрибуты класса (переопределяются наследниками):
        LOGGER_SOURCE — source для LoggerV2 окна или None.
        LOGGER_DOMAIN — domain для LoggerV2 окна или None.
        BG_COLOR — цвет фона окна (кортеж). Обычно вычисляется
                   через ColorCalculator.derive.
        PIPELINE_BUTTONS — кортеж имён кнопок, блокируемых на время
                           шага пайплайна.

    Поля экземпляра:
        main_window — родитель (MainWindow).
        log_manager_v2 — LogManagerV2 или None.
        logger — LoggerV2 окна или None.
        target_dir — текущая целевая папка.
        bg_color — цвет фона (из BG_COLOR).
        main_layout — QVBoxLayout каркаса окна.
        status_label — короткая статусная строка (set_status).
        status_log — прокручиваемый лог (set_info).
    """

    LOGGER_SOURCE = None
    LOGGER_DOMAIN = None
    BG_COLOR = (50, 50, 50)
    PIPELINE_BUTTONS = ()

    def __init__(self, parent=None, title="", log_manager_v2=None) -> None:
        """Конструктор.

        Вход:
            parent — MainWindow.
            title — заголовок окна.
            log_manager_v2 — LogManagerV2 или None. Если None —
                             self.logger тоже None, окно работает
                             без логирования.

        Роль: сохраняет ссылки, создаёт логгер окна, строит каркас,
              создаёт status_label и status_log.
        """
        super().__init__(parent)
        self.main_window = parent
        self.log_manager_v2 = log_manager_v2

        # Логгер окна — если задан source.
        self.logger = None
        if log_manager_v2 is not None and self.LOGGER_SOURCE is not None:
            self.logger = log_manager_v2.create_logger_v2(
                source=self.LOGGER_SOURCE,
                domain=self.LOGGER_DOMAIN,
            )
        if self.logger:
            self.logger.debug(f"{type(self).__name__}.__init__: старт")

        self.target_dir = parent.main_config.get("target_dir", None) \
            if parent is not None else None
        self.bg_color = self.BG_COLOR

        # Каркас окна — из фабрики.
        self.main_layout = WindowFactory.setup_child_window(
            self, title, bg_color=self.bg_color,
        )

        # Публичные каналы для handler'ов V2.
        self.status_label = LabelFactory.create_status_label(
            self, "Выберите целевую папку",
        )
        self.status_log = StatusLogFactory.create_status_log(
            self, bg_color=self.bg_color,
            min_height=100, max_height=200,
        )

    # ============================================================
    # Публичные каналы UI (handler'ы V2)
    # ============================================================

    def set_status(self, msg: str) -> None:
        """Обновляет короткое сообщение в статусной строке.

        Вход: msg — текст.
        Выход: нет.
        Роль: канал StatusHandler через active_child.set_status.
        """
        self.status_label.setText(msg)

    def set_info(self, msg: str) -> None:
        """Дописывает сообщение в прокручиваемый лог.

        Вход: msg — текст.
        Выход: нет.
        Роль: канал InfoUIHandler через active_child.set_info.
        """
        self.status_log.log(msg)

    # ============================================================
    # Общие вспомогательные методы
    # ============================================================

    def _precheck_target_dir(self) -> bool:
        """Проверяет, что выбрана целевая папка.

        Вход: нет.
        Выход:
            True — папка выбрана.
            False — папки нет, в status_label записано предупреждение.

        Роль: единая точка проверки target_dir для всех шагов
              пайплайна. Наследники, которым нужны свои условия,
              переопределяют, но обычно вызывают super().
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return False
        return True

    def _current_sellers(self) -> list:
        """Возвращает актуальный список продавцов.

        Вход: нет.
        Выход: list[Seller].

        Роль: базовая реализация — get_sellers_objects(). Returns
              переопределяет на get_sellers_with_brands().
        """
        return self.main_window.sellers_brands_service.get_sellers_objects()

    # ============================================================
    # Целевая папка
    # ============================================================

    def _on_target_dir_changed(self, new_path) -> None:
        """Обработка смены целевой папки.

        Вход: new_path — новый путь.
        Выход: нет.

        Роль: единая точка обновления target_dir. Логирует, пишет
              в main_config, чистит status_log, обновляет
              status_label и status_log, вызывает hook для
              наследников.
        """
        if self.logger:
            self.logger.debug(
                f"_on_target_dir_changed: новая папка {new_path}"
            )
        self.target_dir = new_path
        self.main_window.main_config.set("target_dir", new_path)
        self.status_log.clear()
        self.set_status("Целевая папка обновлена.")
        self.set_info("Целевая папка обновлена.")
        self._on_target_dir_changed_hook()

    def _on_target_dir_changed_hook(self) -> None:
        """Хук для наследников после смены target_dir.

        Вход: нет.
        Выход: нет.
        Роль: по умолчанию ничего не делает. Наследники сбрасывают
              gating-кнопок и прочие состояния, зависящие от папки.
        """
        pass

    # ============================================================
    # Выбор файлов
    # ============================================================

    def _select_single_file(self, *, config_key: str, title: str,
                            filter: str, label_widget,
                            on_success=None):
        """Диалог выбора одного файла + обновление метки.

        Вход:
            config_key — ключ main_config для стартовой папки.
            title — заголовок диалога.
            filter — фильтр типов файлов.
            label_widget — QLabel для отображения имени файла.
            on_success — callable(path) или None.

        Выход:
            str — путь к выбранному файлу; None — отмена.

        Роль: единая точка «выбрать файл». Обновляет метку, пишет
              родительскую папку в main_config, вызывает callback.
        """
        start_dir = (
            self.main_window.main_config.get(config_key, None)
            or self.target_dir
            or str(Path.home())
        )
        path = FileDialogFactory.open_file_dialog(
            self, title, default_dir=start_dir, filter=filter,
        )
        if not path:
            return None

        label_widget.setText(Path(path).name)
        self.main_window.main_config.set(
            config_key, str(Path(path).parent),
        )
        if self.logger:
            self.logger.debug(
                f"_select_single_file: выбран {Path(path).name} "
                f"(config_key={config_key})"
            )
        if on_success is not None:
            on_success(path)
        return path

    def _select_multiple_files(self, *, config_key: str, title: str,
                               filter: str, list_widget,
                               on_success=None) -> list:
        """Диалог выбора файлов + добавление в FileListWidget.

        Вход:
            config_key — ключ main_config для стартовой папки.
            title — заголовок диалога.
            filter — фильтр типов файлов.
            list_widget — виджет с методом add_file(f) -> bool
                          (обычно FileListWidget).
            on_success — callable(added: list[str]) или None.

        Выход:
            list[str] — список фактически добавленных путей
            (дубликаты отсеиваются внутри list_widget.add_file).

        Роль: единая точка «выбрать файлы». Порядок файлов в
              list_widget сохраняется как при добавлении.
        """
        start_dir = (
            self.main_window.main_config.get(config_key, None)
            or self.target_dir
            or str(Path.home())
        )
        files = FileDialogFactory.open_files_dialog(
            self, title, default_dir=start_dir, filter=filter,
        )
        if not files:
            return []

        added = []
        for f in files:
            if list_widget.add_file(f):
                added.append(f)

        if added:
            self.main_window.main_config.set(
                config_key, str(Path(added[0]).parent),
            )
            if self.logger:
                self.logger.debug(
                    f"_select_multiple_files: добавлено "
                    f"{len(added)} из {len(files)} "
                    f"(config_key={config_key})"
                )
            if on_success is not None:
                on_success(added)
        return added

    # ============================================================
    # Обвязка шага пайплайна
    # ============================================================

    def _run_async_step(self, *, service, target_method, kwargs: dict,
                        start_message: str, finish_message: str,
                        step_name: str, enable_after=None,
                        on_success=None) -> None:
        """Запускает шаг пайплайна в фоновом потоке.

        Вход (все именованные):
            service — экземпляр сервиса (для читаемости вызова).
            target_method — bound method сервиса.
            kwargs — доп. именованные аргументы target_method.
            start_message — текст в статусе/логе в начале.
            finish_message — текст при успехе.
            step_name — префикс для logger.debug/critical.
            enable_after — QPushButton для включения после успеха
                           (None — включать нечего).
            on_success — callable() без аргументов — вызывается в
                         UI-потоке после успеха. None — не вызывать.

        Выход: нет.

        Роль: общая обвязка шагов — двойная запись start/finish,
              колбэки, блокировка PIPELINE_BUTTONS, ThreadFactory.
              target_dir и sellers добавляются автоматически.
        """
        self.set_status(start_message)
        self.set_info(start_message)

        def on_finished():
            self.set_status(finish_message)
            self.set_info(finish_message)
            if enable_after is not None:
                enable_after.setEnabled(True)
            if on_success is not None:
                on_success()
            if self.logger:
                self.logger.debug(f"{step_name}: фоновый поток завершён")

        def on_error(e):
            self.set_status(f"Ошибка на шаге {step_name}: {e}")
            self.set_info(f"Ошибка на шаге {step_name}: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в {step_name}: {e}", can_influence=False,
                )

        call_kwargs = {
            "target_dir": self.target_dir,
            "sellers": self._current_sellers(),
        }
        call_kwargs.update(kwargs)

        ThreadFactory.create_thread(
            parent=self,
            buttons=list(self.PIPELINE_BUTTONS),
            target_func=target_method,
            kwargs=call_kwargs,
            on_finished=on_finished,
            error_callback=on_error,
        )

    # ============================================================
    # Аккумуляция продаж
    # ============================================================

    @log_button_action(
        "btn_accumulate_sales",
        "Ошибка в on_accumulate_sales: {e}",
    )
    def on_accumulate_sales(self) -> None:
        """Обработчик кнопки «Собрать продажи».

        Роль: тонкая обёртка — делегирует в _run_accumulate_sales.
              Декоратор фиксирует имя действия в логе.
        """
        self._run_accumulate_sales()

    def _run_accumulate_sales(self) -> None:
        """Запускает аккумуляцию продаж в фоновом потоке.

        Вход: нет.
        Выход: нет.

        Роль: единая обвязка для всех трёх окон. Проверяет
              target_dir, создаёт SalesAccumulatorService с
              log_manager_v2 и запускает accumulate без
              first_folder.
        """
        if not self.target_dir:
            self.set_status("Сначала выберите целевую папку")
            return

        self.set_status("Аккумуляция продаж...")
        self.set_info("Аккумуляция продаж...")
        service = SalesAccumulatorService(self.log_manager_v2)
        if self.logger:
            self.logger.debug(
                "on_accumulate_sales: SalesAccumulatorService создан"
            )

        def on_finished(_result=None):
            self.set_status("Аккумуляция завершена.")
            self.set_info("Аккумуляция завершена.")
            if self.logger:
                self.logger.debug(
                    "on_accumulate_sales: фоновый поток завершён"
                )

        def on_error(e):
            self.set_status(f"Ошибка аккумуляции: {e}")
            self.set_info(f"Ошибка аккумуляции: {e}")
            if self.logger:
                self.logger.critical(
                    f"Ошибка в on_accumulate_sales: {e}",
                    can_influence=False,
                )

        ThreadFactory.run_in_thread(
            target_func=service.accumulate,
            args=(self.target_dir,),
            on_finished=on_finished,
            error_callback=on_error,
        )

    # ============================================================
    # Завершение
    # ============================================================

    def cleanup(self) -> None:
        """Хук очистки состояния при закрытии.

        Вход: нет.
        Выход: нет.
        Роль: по умолчанию ничего не делает. Наследники сбрасывают
              свои списки/файлы.
        """
        pass

    def closeEvent(self, event) -> None:
        """Обработка закрытия окна.

        Вход: event — QCloseEvent.
        Выход: нет.
        Роль: пишет debug, чистит состояние через cleanup, снимает
              active_child у родителя, принимает событие.
        """
        if self.logger:
            self.logger.debug(f"{type(self).__name__}: closeEvent получен")
        self.cleanup()
        if self.main_window is not None and hasattr(
            self.main_window, "active_child",
        ):
            self.main_window.active_child = None
        event.accept()