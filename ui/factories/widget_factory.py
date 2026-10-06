"""
Фабрики составных виджетов: списков, скролл-областей, лога.

Содержит два класса:
    ListWidgetFactory  — QListWidget, QScrollArea, контейнеры.
    StatusLogFactory   — лог статуса (StatusLog).

ListWidgetFactory не наследует BaseWidgetFactory: QSS собирается
через WidgetStyle. Расчёт цветов скроллбара — в ui.styles.ScrollbarStyle.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QListWidget, QTableWidget, QFrame, QScrollArea,
    QSizePolicy, QVBoxLayout,
)

from ui.styles import WidgetStyle


class ListWidgetFactory:
    """Фабрика для создания списков и прокручиваемых областей.

    Роль: единая точка создания QListWidget и QScrollArea со
          стилизованными скроллбарами. QSS собирается через
          WidgetStyle.

    Публичный API:
        create_list_widget — QListWidget с QSS.
        create_scroll_area — QScrollArea со скроллбарами.
        create_scroll_container — QScrollArea + QWidget + QVBoxLayout.
    """

    @staticmethod
    def create_list_widget(parent, fixed_width=None, fixed_height=None,
                           min_size=None, max_size=None,
                           horizontal_scroll=True, vertical_scroll=True,
                           selection_mode=QListWidget.SingleSelection,
                           bg_color=(30, 20, 35, 0.3),
                           text_color=None, border_radius=5,
                           padding="0px", border="none", font_size=10,
                           object_name=None, cursor_shape=None,
                           extra_style=""):
        """Создаёт стилизованный QListWidget.

        Вход:
            parent — родительский виджет.
            fixed_width, fixed_height — фиксированные размеры или None.
            min_size, max_size — (w, h) или None.
            horizontal_scroll, vertical_scroll — политики прокрутки.
            selection_mode — QListWidget.SelectionMode.
            bg_color, text_color, border_radius, padding, border,
            font_size — стиль.
            object_name, cursor_shape — общие настройки.
            extra_style — дополнительный CSS.

        Выход: QListWidget с QSS.

        Роль: единая точка создания списков. Если задана
              фиксированная ширина — SizePolicy.Fixed, иначе
              Expanding.

        REPLACE: QSS собирается через WidgetStyle.apply_list_widget.
        """
        list_widget = QListWidget(parent)

        if object_name:
            list_widget.setObjectName(object_name)
        if cursor_shape is not None:
            list_widget.setCursor(cursor_shape)
        if fixed_width:
            list_widget.setFixedWidth(fixed_width)
        if fixed_height:
            list_widget.setFixedHeight(fixed_height)
        if min_size:
            list_widget.setMinimumSize(*min_size)
        if max_size:
            list_widget.setMaximumSize(*max_size)
        if not horizontal_scroll:
            list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        if not vertical_scroll:
            list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setSelectionMode(selection_mode)

        if fixed_width:
            list_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        else:
            list_widget.setSizePolicy(QSizePolicy.Expanding,
                                      QSizePolicy.Expanding)

        WidgetStyle.apply_list_widget(
            list_widget, bg_color, text_color, border, border_radius,
            padding, font_size, extra_style,
        )
        return list_widget

    @staticmethod
    def create_file_list_widget(parent, fixed_width=None, fixed_height=None,
                                bg_color=(30, 20, 35, 0.3),
                                text_color=None, border_radius=5,
                                padding="0px", font_size=10,
                                object_name=None):
        """Создаёт FileListWidget — список файлов с крестиком.

        Вход:
            parent — родительский виджет.
            fixed_width, fixed_height — размеры или None.
            bg_color, text_color, border_radius, padding, font_size —
                стиль (передаётся в FileListWidget).
            object_name — objectName.

        Выход: FileListWidget.

        Роль: единая точка создания списка файлов с крестиками.
              Локальный импорт FileListWidget из ui.widgets — чтобы
              не тянуть его в шапку фабрики (циклы: widgets
              реэкспортируется через ui.factories.factories, а
              FileListWidget зависит от ui.styles, не от factories).
        """
        from ui.widgets.file_list_widget import FileListWidget
        widget = FileListWidget(
            parent=parent,
            bg_color=bg_color,
            text_color=text_color,
            border_radius=border_radius,
            padding=padding,
            font_size=font_size,
            object_name=object_name,
        )
        if fixed_width:
            widget.setFixedWidth(fixed_width)
        if fixed_height:
            widget.setFixedHeight(fixed_height)
        return widget

    @staticmethod
    def create_scroll_area(parent, widget=None, bg_color=(25, 25, 45),
                           border="none", border_radius=0,
                           widget_resizable=True, object_name=None,
                           cursor_shape=None, extra_style="",
                           scrollbar_width=12, scrollbar_radius=6,
                           rounded=True):
        """Создаёт прокручиваемую область со скроллбарами.

        Вход:
            parent — родительский виджет.
            widget — виджет внутри области. None → не устанавливаем.
            bg_color — фон окна для расчёта скроллбара.
            border, border_radius — стиль области.
            widget_resizable — растягивать ли внутренний виджет.
            object_name, cursor_shape — общие настройки.
            extra_style — дополнительный CSS.
            scrollbar_width, scrollbar_radius — параметры скроллбара.
            rounded — форма рамки QFrame: True (дефолт) →
                      StyledPanel (скруглённые углы Qt),
                      False → NoFrame (прямые углы).

        Выход: QScrollArea.

        Роль: единая точка создания QScrollArea. Скроллбар
              подбирается через WidgetStyle (ScrollbarStyle).
              Форма рамки управляется параметром rounded — QSS
              «border: none» дефолтный frameShape не всегда
              перекрывает, поэтому задаём его явно.
        """
        scroll = QScrollArea(parent)
        scroll.setFrameShape(
            QFrame.StyledPanel if rounded else QFrame.NoFrame
        )
        if object_name:
            scroll.setObjectName(object_name)
        if cursor_shape is not None:
            scroll.setCursor(cursor_shape)
        scroll.setWidgetResizable(widget_resizable)

        WidgetStyle.apply_scroll_area(
            scroll, bg_color, border, border_radius,
            scrollbar_width, scrollbar_radius, extra_style,
        )

        if widget is not None:
            scroll.setWidget(widget)

        return scroll

    @staticmethod
    def create_scroll_container(parent, spacing=2, margins=(0, 0, 0, 0),
                                bg_color=(25, 25, 45),
                                rounded=True):
        """Создаёт прокручиваемую область с внутренним контейнером.

        Вход:
            parent — родительский виджет.
            spacing — расстояние между элементами в layout.
            margins — отступы (left, top, right, bottom).
            bg_color — фон окна для скроллбара.
            rounded — форма рамки QScrollArea: True (дефолт) →
                      скруглённые углы, False → прямые углы.

        Выход: (scroll_area, content_widget, content_layout).

        Роль: удобный хелпер — создаёт QScrollArea, внутри —
              QWidget с QVBoxLayout. Возвращает все три объекта.
        """
        content_widget = QWidget(parent)
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(*margins)
        content_layout.setSpacing(spacing)

        scroll_area = ListWidgetFactory.create_scroll_area(
            parent, widget=content_widget, widget_resizable=True,
            bg_color=bg_color, rounded=rounded,
        )

        return scroll_area, content_widget, content_layout

class TableWidgetFactory:
    """Фабрика для создания QTableWidget со стилем.

    Роль: единая точка создания таблиц. QSS собирается через
          WidgetStyle.apply_table_widget — базовый блок, опциональный
          заголовок, ::item, скроллбар. Поведение (selection,
          edit triggers, section resize) задаётся вызывающим кодом
          после создания — это специфика конкретного места.

    Публичный API:
        create_table_widget — QTableWidget с QSS.
    """

    @staticmethod
    def create_table_widget(parent, rows=0, columns=0, headers=None,
                            bg_color=(30, 20, 35, 0.3),
                            text_color=None, border="none",
                            border_radius=5, padding="2px",
                            font_size=None,
                            header_bg_color=None,
                            header_text_color=None,
                            header_padding="4px",
                            item_padding="4px",
                            show_grid=True,
                            gridline_color=None,
                            fixed_size=None, min_size=None, max_size=None,
                            object_name=None, cursor_shape=None,
                            extra_style=""):
        """Создаёт стилизованный QTableWidget.

        Вход:
            parent — родительский виджет.
            rows, columns — начальные размеры.
            headers — список заголовков (None → не задаём).
            bg_color, text_color, border, border_radius, padding,
            font_size — стиль таблицы.
            header_bg_color, header_text_color, header_padding —
                стиль QHeaderView::section. Если оба None — блок
                заголовка не добавляется.
            item_padding — padding в ::item.
            show_grid — показывать линии сетки (setShowGrid).
            gridline_color — цвет линий; None → свойство не
                добавляется.
            fixed_size, min_size, max_size — размеры (или None).
            object_name, cursor_shape — общие настройки.
            extra_style — дополнительный CSS.

        Выход: QTableWidget с QSS.

        Роль:
            Не задаёт setSelectionBehavior / setEditTriggers /
            setSectionResizeMode — это специфика каждого места,
            делается после создания. Также не делает
            resizeRowsToContents — вызывается после заполнения
            ячеек.
        """
        table = QTableWidget(parent)

        if rows:
            table.setRowCount(rows)
        if columns:
            table.setColumnCount(columns)
        if headers:
            table.setHorizontalHeaderLabels(headers)
        if object_name:
            table.setObjectName(object_name)
        if cursor_shape is not None:
            table.setCursor(cursor_shape)
        if fixed_size:
            table.setFixedSize(*fixed_size)
        if min_size:
            table.setMinimumSize(*min_size)
        if max_size:
            table.setMaximumSize(*max_size)

        WidgetStyle.apply_table_widget(
            table, bg_color, text_color, border, border_radius,
            padding, font_size, header_bg_color, header_text_color,
            header_padding, item_padding, show_grid, gridline_color,
            extra_style,
        )
        return table

class StatusLogFactory:
    """Фабрика лога статуса (StatusLog).

    Назначение:
        Единая точка создания StatusLog — read-only QTextEdit
        со стилем под фон окна.

    Роль в программе:
        Используется в ChzMPWindow, CompareWindow, ReturnsWindow
        вместо самодельных QTextEdit с QSS. QSS собирается внутри
        самого StatusLog — здесь только прокси.
    """

    @staticmethod
    def create_status_log(parent, bg_color=None, border_color=None,
                          font_family="Consolas, monospace", font_size=10,
                          min_height=100, max_height=200):
        """Создаёт StatusLog.

        Вход:
            parent — родительское окно.
            bg_color — фон лога. None → берётся у parent.
            border_color — цвет рамки. None → авто-расчёт.
            font_family — шрифт.
            font_size — размер шрифта.
            min_height, max_height — ограничения высоты.

        Выход: StatusLog.

        Роль: локальный импорт — StatusLog живёт в ui/widgets и
              не должен тянуться в шапку фабрики (иначе цикл:
              status_log импортирует BaseWidgetFactory, а widgets
              реэкспортирует через ui.factories).
        """
        from ui.widgets.status_log import StatusLog
        return StatusLog(
            parent=parent,
            bg_color=bg_color,
            border_color=border_color,
            font_family=font_family,
            font_size=font_size,
            min_height=min_height,
            max_height=max_height,
        )
