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