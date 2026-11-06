"""
Централизованный оркестратор окон.

Управляет уровнями вложенности (Level), модальностью, геометрией
и перетаскиванием всех дочерних окон приложения.
"""

from PySide6.QtCore import Qt, QEvent, QObject


class WindowManager(QObject):
    """Менеджер дочерних окон.

    Роль:
        Отслеживает все зарегистрированные окна, выставляет им
        правильные флаги (без системной рамки), модальность и
        геометрию с отступами (10, 10, 0, 0).
        Ограничивает перемещение независимых окон (fill_parent=False)
        в пределах главного окна (клэмпинг) и автоматически
        ресайзит окна с fill_parent=True при изменении родителя.
    """

    def __init__(self, main_window, log_manager_v2):
        """Конструктор.

        Вход:
            main_window — MainWindow (window_level=0).
            log_manager_v2 — LogManagerV2 или None.
        """
        super().__init__()
        self._main_window = main_window
        self._windows = {}
        self._logger = None
        if log_manager_v2 is not None:
            self._logger = log_manager_v2.create_logger_v2(
                source="WindowManager.ui.managers.window_manager",
                domain="ui",
            )

    def register_window(self, window, parent, fill_parent, modal):
        """Регистрирует окно, настраивает флаги, геометрию и подписки.

        Вход:
            window — QDialog или QMainWindow.
            parent — родительское окно.
            fill_parent — True, если окно должно занимать всё
                          пространство родителя (с отступами).
            modal — True, если окно должно блокировать родителя.
        """
        if parent is None:
            if self._logger:
                self._logger.warning(
                    f"WindowManager: попытка регистрации "
                    f"{type(window).__name__} без parent!"
                )
            raise ValueError(
                f"register_window: parent обязателен для {type(window).__name__}"
            )

        window.window_level = getattr(parent, "window_level", 0) + 1

        # Флаги окна (без системной рамки, но как полноценный диалог)
        window.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        window.setAttribute(Qt.WA_TranslucentBackground)

        # Модальность
        if modal:
            window.setWindowModality(Qt.WindowModal)
        else:
            window.setWindowModality(Qt.NonModal)

        # Геометрия
        if fill_parent:
            # Сервисные/псевдосервисные окна занимают область
            # Qt-родителя с отступами (10, 10, -10, -10).
            window.setGeometry(*self._calculate_geometry(parent))
        else:
            # Диалоги сохраняют свой размер (default_width ×
            # default_height, выставленный фабрикой). Только
            # позиционируем: центр Qt-родителя, клэмп в MainWindow.
            self._position_dialog(window, parent)

        # window_manager на самом окне — чтобы вложенные диалоги
        # (Level 2+) нашли менеджер через hasattr(parent, ...).
        # Все окна ссылаются на один и тот же экземпляр.
        window.window_manager = self

        # Регистрация
        self._windows[id(window)] = {
            "window": window,
            "parent": parent,
            "fill_parent": fill_parent,
        }

        # Подписки
        window.installEventFilter(self)
        if fill_parent:
            parent.installEventFilter(self)
        window_id = id(window)
        window.destroyed.connect(
            lambda: self._on_destroyed_by_id(window_id)
        )

        if fill_parent and hasattr(self._main_window, "active_child"):
            self._main_window.active_child = window

        if self._logger:
            self._logger.debug(
                f"WindowManager: зарегистрировано {type(window).__name__} "
                f"(Level {window.window_level}), "
                f"fill_parent={fill_parent}, modal={modal}"
            )

    def _calculate_geometry(self, parent):
        """Вычисляет геометрию окна.

        Сдвиг +30 по Y применяется только если родитель — это
        MainWindow (компенсация его верхней панели/заголовка).
        Для вложенных окон (Level 1+) сдвиг не нужен, они
        выравниваются ровно по границам родителя.
        """
        offset_y = 30 if parent is self._main_window else 0
        return (
            parent.x(),
            parent.y() + offset_y,
            parent.width(),
            parent.height(),
        )
    def _position_dialog(self, window, parent):
        """Позиционирует диалог без растяжения.

        Вход:
            window — QDialog с уже выставленным размером
                     (resize(default_width, default_height) из фабрики).
            parent — Qt-родитель (окно или другой диалог).

        Роль: центрирует диалог в Qt-родителе (fallback — MainWindow)
              и клэмпит в MainWindow с отступом (10, 10). Размер
              диалога НЕ меняется — это его собственный размер из
              фабрики (для MessageDialog — adjustSize по контенту,
              для BaseEditDialog — default_width × default_height).
        """
        w, h = window.width(), window.height()

        # Центр Qt-родителя.
        src = parent if parent is not None else self._main_window
        try:
            src_geo = src.frameGeometry()
        except RuntimeError:
            src_geo = self._main_window.frameGeometry()

        x = src_geo.x() + (src_geo.width() - w) // 2
        y = src_geo.y() + (src_geo.height() - h) // 2

        # Клэмп в MainWindow — те же отступы (10, 10), что и у
        # fill_parent-окон, чтобы диалог не прилипал к краям.
        try:
            main_geo = self._main_window.frameGeometry()
            x = max(main_geo.left() + 10, min(x, main_geo.right() - w))
            y = max(main_geo.top() + 10, min(y, main_geo.bottom() - h))
        except RuntimeError:
            pass

        window.move(x, y)

    def unregister_window(self, window):
        """Снимает окно с регистрации и каскадно закрывает дочерние."""
        # Каскадное закрытие дочерних окон
        for entry in list(self._windows.values()):
            if entry["parent"] is window:
                try:
                    entry["window"].close()
                except RuntimeError:
                    pass

        try:
            window.removeEventFilter(self)
        except RuntimeError:
            pass

        parent = self._windows.get(id(window), {}).get("parent")
        if parent is not None:
            try:
                parent.removeEventFilter(self)
            except RuntimeError:
                pass

        self._windows.pop(id(window), None)

        if self._logger:
            self._logger.debug(
                f"WindowManager: {type(window).__name__} снят с регистрации"
            )

    def _on_destroyed(self, window):
        """Слот сигнала destroyed — для защиты от двойного удаления."""
        if id(window) in self._windows:
            self.unregister_window(window)

    def _on_destroyed_by_id(self, window_id):
        """Слот сигнала destroyed — по id, без захвата Python-обёртки.

        Вход:
            window_id — id(window) на момент регистрации.

        Роль: защита от двойного удаления. Не обращается к самому
              окну — только к реестру по id. Если запись уже снята
              (unregister_window отработал по QEvent.Close) —
              ничего не делает.
        """
        entry = self._windows.get(window_id)
        if entry is None:
            return
        try:
            self.unregister_window(entry["window"])
        except RuntimeError:
            self._windows.pop(window_id, None)

    def get_window(self, cls):
        """Возвращает первый видимый экземпляр окна заданного класса."""
        for entry in self._windows.values():
            window = entry["window"]
            try:
                if isinstance(window, cls) and window.isVisible():
                    return window
            except RuntimeError:
                continue
        return None

    def close_all(self, except_=None):
        """Закрывает все зарегистрированные окна, кроме except_."""
        for entry in list(self._windows.values()):
            window = entry["window"]
            if window is not except_:
                try:
                    window.close()
                except RuntimeError:
                    pass

    def eventFilter(self, obj, event):
        """Фильтр событий: клэмпинг (Move) и ресайз (Resize/Move)."""
        entry = None
        for e in self._windows.values():
            if e["window"] is obj:
                entry = e
                break

        # 1. Закрытие окна
        if event.type() == QEvent.Close and entry:
            self.unregister_window(obj)
            return False

        # 2. Перетаскивание независимого окна (клэмпинг в MainWindow)
        if event.type() == QEvent.Move and entry and not entry["fill_parent"]:
            if getattr(obj, "_wm_clamping", False):
                return False

            main_geo = self._main_window.frameGeometry()
            new_x = max(main_geo.left() + 10, min(obj.x(), main_geo.right() - obj.width()))
            new_y = max(main_geo.top() + 10, min(obj.y(), main_geo.bottom() - obj.height()))

            if (new_x, new_y) != (obj.x(), obj.y()):
                old_x, old_y = obj.x(), obj.y()
                obj._wm_clamping = True
                obj.move(new_x, new_y)
                obj._wm_clamping = False
                if self._logger:
                    self._logger.debug(
                        f"WindowManager: клэмпинг {type(obj).__name__} "
                        f"с ({old_x}, {old_y}) на ({new_x}, {new_y})"
                    )
            return False

        # 3. Ресайз окна при изменении родителя (fill_parent=True)
        if event.type() in (QEvent.Resize, QEvent.Move):
            self._sync_fill_parent_children(obj)
            return False

        return False

    def broadcast_theme(self, parent_bg):
        """Зарезервировано. В текущей порции не используется."""
        pass

    def _sync_fill_parent_children(self, parent):
        """Пересчитывает геометрию детей с fill_parent=True.

        Вход:
            parent — QWidget, чьё событие Resize/Move пришло.

        Роль: на Resize/Move родителя пересчитывает и применяет
              geometry ко всем зарегистрированным детям с
              fill_parent=True. Вызывается из eventFilter для
              любого объекта (родителя или самого окна) — так
              работает каскад: MainWindow → Level 1 → Level 2.
        """
        for entry in list(self._windows.values()):
            if entry["parent"] is not parent:
                continue
            if not entry["fill_parent"]:
                continue
            try:
                entry["window"].setGeometry(
                    *self._calculate_geometry(parent)
                )
            except RuntimeError:
                pass
