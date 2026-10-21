"""
Фабрика контейнеров с компоновками.

Содержит LayoutFactory — единая точка создания QWidget с
настроенным layout: QHBoxLayout, QVBoxLayout, QGridLayout,
QFormLayout, QStackedLayout. Все методы возвращают QWidget,
готовый к вставке в родительский layout.

LayoutFactory не наследует BaseWidgetFactory: стилей и цветов
здесь нет, только структура.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGridLayout,
    QFormLayout, QStackedLayout,
)


class LayoutFactory:
    """Фабрика для создания контейнеров с компоновками.

    Роль: единая точка создания QWidget + layout. Позволяет
          собирать сложные композиции декларативно.

    Публичный API:
        create_row — QHBoxLayout.
        create_column — QVBoxLayout.
        create_grid — QGridLayout.
        create_form — QFormLayout.
        create_stacked — QStackedLayout.
        add_centered_widget — центрирование виджета в layout.
    """

    @staticmethod
    def create_row(parent, *widgets, spacing=10, margins=(0, 0, 0, 0),
                   alignment=Qt.AlignCenter, fixed_width=None,
                   fixed_height=None, stretch_factors=None,
                   background_color="transparent", object_name=None):
        """Создаёт горизонтальный контейнер.

        Вход:
            parent — родительский виджет.
            *widgets — виджеты слева направо.
            spacing — расстояние между виджетами в px.
            margins — отступы (left, top, right, bottom).
            alignment — Qt.AlignmentFlag для layout.
            fixed_width, fixed_height — фиксированные размеры.
            stretch_factors — список коэффициентов растяжения для
                              addWidget(w, stretch).
            background_color — CSS-цвет фона контейнера.
            object_name — objectName для селектора.

        Выход: QWidget с QHBoxLayout.

        Роль: обёртка для быстрого создания строки виджетов.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            if stretch_factors and i < len(stretch_factors):
                layout.addWidget(w, stretch_factors[i])
            else:
                layout.addWidget(w)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def create_service_box(parent, path_selector, status_label, left_buttons,
                           right_items=None, file_row=None,
                           bottom_widget=None, right_stretch_top=False):
        """Создаёт стандартный бокс сервисного окна.

        Вход:
            parent — родительский виджет.
            path_selector — виджет выбора пути.
            status_label — лейбл статуса (растягивается в левой колонке).
            left_buttons — список виджетов для левой колонки (под статусом).
            right_items — список виджетов для правой колонки.
            file_row — виджет строки выбора файла (опционально).
            bottom_widget — виджет нижней строки (опционально, если
                            колонки не нужны — просто status + row).
            right_stretch_top — прижать right_items к низу правой
                            колонки (stretch сверху). По умолчанию
                            False — элементы сверху.

        Выход: QWidget с готовой компоновкой.
        """
        box = QWidget(parent)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Шапка: выбор пути и (опционально) выбор файла.
        layout.addWidget(path_selector, alignment=Qt.AlignCenter)
        if file_row:
            layout.addWidget(file_row, alignment=Qt.AlignCenter)

        # 2. Основная часть: либо колонки, либо простая строка.
        if bottom_widget:
            layout.addWidget(status_label, alignment=Qt.AlignCenter)
            layout.addWidget(bottom_widget, alignment=Qt.AlignCenter)
        else:
            left_col = QVBoxLayout()
            left_col.addWidget(status_label, 1)
            for btn in left_buttons:
                left_col.addWidget(btn)

            right_col = QVBoxLayout()
            right_col.setSpacing(5)
            if right_stretch_top:
                right_col.addStretch(1)
            if right_items:
                for item in right_items:
                    right_col.addWidget(item)

            columns = QHBoxLayout()
            columns.addLayout(left_col)
            columns.addLayout(right_col)

            wrapper = QHBoxLayout()
            wrapper.addStretch()
            wrapper.addLayout(columns)
            wrapper.addStretch()
            layout.addLayout(wrapper)

        return box

    @staticmethod
    def create_service_page(header_widget, box, status_log,
                            accumulate_row=None):
        """Собирает стандартную вертикальную страницу сервиса.

        Вход:
            header_widget — верхний лейбл (desc_label / header_label /
                            instruction_label).
            box — центральный бокс (из create_service_box).
            status_log — прокручиваемый лог (StatusLog).
            accumulate_row — QLayout с кнопкой «Собрать продажи»
                            или None, если операция не нужна.

        Выход: QVBoxLayout — готов к addLayout() в main_layout.

        Роль: единый макет сервисной страницы. Структура:
              header → box → stretch(1) → status_log
              → (accumulate_row). Margins наследуются от QVBoxLayout
              по умолчанию — поведение совпадает с прежним.
        """
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.addWidget(header_widget)
        layout.addWidget(box)
        layout.addStretch(1)
        layout.addWidget(status_log)
        if accumulate_row is not None:
            layout.addLayout(accumulate_row)
        return layout

    @staticmethod
    def create_column(parent, *widgets, spacing=10, margins=(0, 0, 0, 0),
                      alignment=Qt.AlignCenter, fixed_width=None,
                      fixed_height=None, stretch_factors=None,
                      background_color="transparent", object_name=None):
        """Создаёт вертикальный контейнер.

        Вход: как в create_row, направление — сверху вниз.

        Выход: QWidget с QVBoxLayout.

        Роль: используется для вертикальных колонок кнопок и полей.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            if stretch_factors and i < len(stretch_factors):
                layout.addWidget(w, stretch_factors[i])
            else:
                layout.addWidget(w)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def create_grid(parent, widgets, columns, spacing=10,
                    margins=(0, 0, 0, 0), alignment=Qt.AlignCenter,
                    fixed_width=None, fixed_height=None,
                    background_color="transparent", object_name=None):
        """Создаёт контейнер с сеткой.

        Вход:
            parent — родительский виджет.
            widgets — список виджетов.
            columns — количество столбцов.
            spacing — расстояние между ячейками.
            margins — отступы.
            alignment — Qt.AlignmentFlag.
            fixed_width, fixed_height — фиксированные размеры.
            background_color — цвет фона.
            object_name — objectName.

        Выход: QWidget с QGridLayout.

        Роль: размещает виджеты построчно по columns в ряд.
              Удобно для плиток и карточек.
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QGridLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for i, w in enumerate(widgets):
            row = i // columns
            col = i % columns
            layout.addWidget(w, row, col)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def create_form(parent, rows, spacing=10, margins=(0, 0, 0, 0),
                    alignment=Qt.AlignLeft, fixed_width=None,
                    fixed_height=None, background_color="transparent",
                    object_name=None):
        """Создаёт контейнер с формой (метка + поле).

        Вход:
            parent — родительский виджет.
            rows — список кортежей (label_widget, field_widget).
                   Если label_widget — строка, создаётся QLabel
                   с этим текстом.
            spacing, margins, alignment — параметры layout.
            fixed_width, fixed_height — фиксированные размеры.
            background_color — цвет фона.
            object_name — objectName.

        Выход: QWidget с QFormLayout.

        Роль: используется в диалогах для пар «Название: [поле]».
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QFormLayout(container)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        layout.setAlignment(alignment)

        for label, field in rows:
            if isinstance(label, str):
                label_widget = QLabel(label)
                layout.addRow(label_widget, field)
            else:
                layout.addRow(label, field)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def create_stacked(parent, widgets, current_index=0,
                       margins=(0, 0, 0, 0), fixed_width=None,
                       fixed_height=None, background_color="transparent",
                       object_name=None):
        """Создаёт контейнер со стеком виджетов.

        Вход:
            parent — родительский виджет.
            widgets — список виджетов для стека.
            current_index — индекс изначально видимого.
            margins — отступы.
            fixed_width, fixed_height — фиксированные размеры.
            background_color — цвет фона.
            object_name — objectName.

        Выход: QWidget с QStackedLayout.

        Роль: одновременно виден только один виджет;
              переключение — через layout.setCurrentIndex().
        """
        container = QWidget(parent)
        if object_name:
            container.setObjectName(object_name)

        layout = QStackedLayout(container)
        layout.setContentsMargins(*margins)

        for w in widgets:
            layout.addWidget(w)

        layout.setCurrentIndex(current_index)

        if fixed_width is not None:
            container.setFixedWidth(fixed_width)
        if fixed_height is not None:
            container.setFixedHeight(fixed_height)

        container.setStyleSheet(f"background: {background_color};")
        return container

    @staticmethod
    def add_centered_widget(main_layout, widget):
        """Добавляет виджет в layout с горизонтальным центрированием.

        Вход:
            main_layout — QVBoxLayout или QHBoxLayout.
            widget — виджет для центрирования.

        Выход: нет.

        Роль: оборачивает виджет в QHBoxLayout с растяжками
              по краям — так он центрируется внутри родительского
              layout.
        """
        h_layout = QHBoxLayout()
        h_layout.addStretch()
        h_layout.addWidget(widget)
        h_layout.addStretch()
        main_layout.addLayout(h_layout)