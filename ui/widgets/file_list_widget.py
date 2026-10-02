"""
Виджет списка файлов с крестиком удаления.

Содержит FileListWidget — QListWidget, в каждой строке которого
слева кнопка «✕» (удалить файл из списка), справа — имя файла.
Эмитит сигнал file_removed(path) при удалении.

Роль в программе:
    Единая точка для списков выбранных файлов в окнах сервисов
    (ChzMPWindow, ReturnsWindow, CompareWindow). Пришёл на смену
    ListWidgetFactory.create_list_widget для случая «файлы, которые
    можно убирать по одному».
"""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QWidget, QHBoxLayout, QPushButton,
    QLabel, QSizePolicy,
)

from ui.styles import WidgetStyle


class FileListWidget(QListWidget):
    """Список выбранных файлов с крестиком удаления в каждой строке.

    Роль:
        Заменяет простой QListWidget там, где пользователь должен
        иметь возможность убрать отдельный файл из списка. Скрывает
        внутреннее устройство строки (кнопка + метка + UserRole
        с путём) за публичным API:
            add_file(path) -> bool
            remove_file(path)
            get_files() -> list[str]
            clear_files()

    Сигналы:
        file_removed(str) — путь удалённого файла. Эмитится как при
                            удалении через UI-крестик, так и при
                            явном вызове remove_file().

    Стиль:
        QSS списка — через WidgetStyle.apply_list_widget.
        Цвет текста имени файла и крестика — rgb-кортежи.
    """

    # Сигнал: путь удалённого файла.
    file_removed = Signal(str)

    # Цвета крестика. В rgb-формате (кортежи), не строки.
    CLOSE_COLOR = (212, 212, 212)        # #d4d4d4
    CLOSE_HOVER_COLOR = (255, 102, 102)  # #ff6666

    def __init__(self, parent=None,
                 bg_color=(30, 20, 35, 0.3),
                 text_color=None,
                 border_radius=5, padding="0px", font_size=10,
                 object_name=None, extra_style=""):
        """Конструктор.

        Вход:
            parent — родительский виджет.
            bg_color — фон списка (кортеж).
            text_color — цвет текста (строка или кортеж — как
                         принимает WidgetStyle.apply_list_widget).
            border_radius — радиус скругления.
            padding — внутренние отступы.
            font_size — размер шрифта.
            object_name — objectName для CSS-селектора.
            extra_style — дополнительный CSS.

        Роль: настраивает сам QListWidget через WidgetStyle,
              сохраняет параметры стиля для создания строк.
        """
        super().__init__(parent)
        self._text_color = text_color
        self._font_size = font_size

        WidgetStyle.apply_list_widget(
            self, bg_color, text_color, "none", border_radius,
            padding, font_size, extra_style,
        )
        if object_name:
            self.setObjectName(object_name)

    # ---------- Публичный API ----------

    def add_file(self, path: str) -> bool:
        """Добавляет файл в список.

        Вход: path — путь к файлу.
        Выход:
            True — файл добавлен.
            False — такой путь уже есть в списке.

        Роль: единственная точка добавления. Создаёт QListWidgetItem,
              вешает на него QWidget с крестиком и меткой имени,
              сохраняет путь в UserRole.
        """
        if path in self.get_files():
            return False

        item = QListWidgetItem()
        self.addItem(item)

        row = self._build_row_widget(path)
        self.setItemWidget(item, row)
        item.setData(Qt.UserRole, path)
        return True

    def remove_file(self, path: str) -> None:
        """Удаляет файл из списка и эмитит file_removed(path).

        Вход: path — путь к файлу.
        Выход: нет.
        Роль: ищет item по UserRole, удаляет. Если такого нет —
              молча выходит.
        """
        for i in range(self.count()):
            item = self.item(i)
            if item.data(Qt.UserRole) == path:
                self.takeItem(i)
                self.file_removed.emit(path)
                return

    def get_files(self) -> list:
        """Возвращает список путей в порядке добавления.

        Выход: list[str].
        """
        return [
            self.item(i).data(Qt.UserRole)
            for i in range(self.count())
        ]

    def clear_files(self) -> None:
        """Очищает список файлов.

        Вход: нет.
        Выход: нет.
        Роль: обёртка над clear(). Сигналы file_removed НЕ эмитятся —
              это «сброс», а не «удаление пользователем».
        """
        self.clear()

    # ---------- Внутреннее ----------

    def _build_row_widget(self, path: str) -> QWidget:
        """Создаёт строку: крестик + имя файла.

        Вход: path — путь к файлу.
        Выход: QWidget для setItemWidget.
        Роль: вынесено отдельно, чтобы add_file был читаемым.
        """
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        close_btn = self._build_close_button(path)
        layout.addWidget(close_btn)

        name_label = QLabel(Path(path).name)
        WidgetStyle.apply_label(
            name_label,
            bg_color=(0, 0, 0, 0),
            text_color=self._text_color,
            padding="0px",
            border_radius=0,
            font_size=self._font_size,
            alignment=Qt.AlignLeft | Qt.AlignVCenter,
        )
        layout.addWidget(name_label, stretch=1)

        return row

    def _build_close_button(self, path: str) -> QPushButton:
        """Создаёт крестик с обработчиком удаления.

        Вход: path — путь файла, который удалит крестик.
        Выход: QPushButton.
        Роль: размер подстраивается под содержимое (SizePolicy.Fixed,
              без setFixedSize). Цвета — rgb-кортежи, hover — через
              QSS.
        """
        btn = QPushButton("✕")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setFlat(True)

        base = self.CLOSE_COLOR
        hover = self.CLOSE_HOVER_COLOR
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: rgb({base[0]}, {base[1]}, {base[2]});
                padding: 1px 3px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: rgb({hover[0]}, {hover[1]}, {hover[2]});
            }}
        """)
        btn.clicked.connect(lambda checked=False, p=path: self.remove_file(p))
        return btn