"""
Фабрика блочных контейнеров для компоновки окон.

Содержит WindowBlockFactory — декларативный сборщик компоновок:
шапки, вертикальные стеки, сервисные боксы. Поддерживает
QWidget и QLayoutItem (включая QSpacerItem).
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLayoutItem, QSizePolicy,
)
from ui.factories.layout_factory import LayoutFactory


class WindowBlockFactory:
    """Фабрика для создания стандартных блоков компоновки.

    Роль:
        Единая точка сборки декларативных контейнеров. Позволяет
        передавать QWidget и QLayoutItem (например, QSpacerItem)
        в списках элементов.
    """

    @staticmethod
    def _add_element(layout, element, stretch=0):
        """Добавляет виджет или QLayoutItem в layout.

        Вход:
            layout — QLayout, в который добавляем.
            element — QWidget или QLayoutItem (например, QSpacerItem).
            stretch — коэффициент растяжения (только для QWidget).
        """
        if isinstance(element, QWidget):
            layout.addWidget(element, stretch)
        elif isinstance(element, QLayoutItem):
            layout.addItem(element)

    @staticmethod
    def create_header_block(parent, rows: list[dict], spacing: int = 8,
                            margins: tuple = (0, 0, 0, 0)) -> QWidget | None:
        """Создаёт блок шапки из строк виджетов.

        Вход:
            parent — родитель.
            rows — список словарей:
                   {"widgets": [...], "stretch_factors": [...],
                    "alignment": ..., "spacing": ...}.
        Выход: QWidget или None, если rows пуст.
        """
        if not rows:
            return None
        container = QWidget(parent)
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(*margins)
        vbox.setSpacing(spacing)

        for row in rows:
            widgets = row.get("widgets") or []
            if not widgets:
                continue
            stretch_factors = row.get("stretch_factors")
            alignment = row.get("alignment", Qt.AlignCenter)
            spacing = row.get("spacing", 10)
            row_widget = LayoutFactory.create_row(
                container, *widgets,
                stretch_factors=stretch_factors,
                alignment=alignment, spacing=spacing
            )
            vbox.addWidget(row_widget)
        return container

    @staticmethod
    def create_field_stack(parent, items: list,
                           alignment=Qt.AlignTop,
                           spacing: int = 6,
                           width: int | None = None) -> QWidget | None:
        """Создаёт вертикальный стек элементов.

        Вход:
            parent — родитель.
            items — плоский список QWidget или QLayoutItem.
                    Например: [label1, field1, label2, field2] или
                    просто [button1, button2, button3].
            alignment — выравнивание (по умолчанию Qt.AlignTop).
            spacing — отступ между элементами.
        Выход: QWidget или None, если items пуст.
        """
        if not items:
            return None
        container = QWidget(parent)

        if width is not None:
            container.setFixedWidth(width)
        else:
            container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(spacing)
        vbox.setAlignment(alignment | Qt.AlignHCenter)

        for item in items:
            WindowBlockFactory._add_element(vbox, item)

        return container

    @staticmethod
    def create_service_box(parent, header_widget=None, body_widget=None,
                           footer_widget=None,
                           margins: tuple = (20, 20, 20, 20),
                           spacing: int = 12,
                           width: int | None = None) -> QWidget:
        """Создаёт сервисный бокс (шапка + тело + подвал).

        Вход:
            parent — родитель.
            header_widget — шапка (QWidget или QLayoutItem, или None).
            body_widget — тело (QWidget или QLayoutItem, или None).
            footer_widget — подвал (QWidget или QLayoutItem, или None).
            margins — отступы от краёв.
            spacing — отступ между элементами.
        Выход: QWidget.
        """
        container = QWidget(parent)

        if width is not None:
            container.setFixedWidth(width)
        elif body_widget is not None:
            container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        else:
            container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(*margins)
        vbox.setSpacing(spacing)

        if header_widget is not None:
            WindowBlockFactory._add_element(vbox, header_widget)
        if body_widget is not None:
            WindowBlockFactory._add_element(vbox, body_widget)
        if footer_widget is not None:
            WindowBlockFactory._add_element(vbox, footer_widget)

        return container

    @staticmethod
    def build_layout(parent, config: dict) -> QWidget | None:
        """Рекурсивно собирает макет по декларативному словарю.

        Вход:
            parent — родительский виджет.
            config — словарь с описанием макета. Ключ "type" задаёт
                     тип узла:
                     - "header": {"rows": [...]}
                     - "stack": {"items": [...], "alignment": ..., "spacing": ...}
                     - "row": {"items": [...], "stretch_factors": [...], "alignment": ...}
                     - "box": {"header": {...}, "body": {...}, "footer": {...}}
        Выход: QWidget или None.
        """
        if not config:
            return None

            # Если это уже готовый виджет или QLayoutItem — возвращаем как есть
        if not isinstance(config, dict):
            return config

        node_type = config.get("type")
        # Извлекаем настройки из отдельного блока или используем пустой словарь
        settings = config.get("settings") or {}

        if node_type == "header":
            return WindowBlockFactory.create_header_block(
                parent,
                rows=config.get("rows", []),
                spacing=settings.get("spacing", 8),
                margins=settings.get("margins", (0, 0, 0, 0))
            )

        elif node_type == "stack":
            return WindowBlockFactory.create_field_stack(
                parent,
                items=config.get("items", []),
                alignment=settings.get("alignment", Qt.AlignTop),
                spacing=settings.get("spacing", 6),
                width=settings.get("width"),
            )

        elif node_type == "row":
            children = [
                WindowBlockFactory.build_layout(parent, child)
                for child in config.get("items", [])
            ]
            children = [c for c in children if c is not None]
            return LayoutFactory.create_row(
                parent,
                *children,
                stretch_factors=settings.get("stretch_factors", [0] * len(children)),
                alignment=settings.get("alignment", Qt.AlignTop),
                spacing=settings.get("spacing", 10),
                add_side_stretches=settings.get("add_side_stretches", True),
            )

        elif node_type == "box":
            header = WindowBlockFactory.build_layout(parent, config.get("header")) if config.get("header") else None
            body = WindowBlockFactory.build_layout(parent, config.get("body")) if config.get("body") else None
            footer = WindowBlockFactory.build_layout(parent, config.get("footer")) if config.get("footer") else None

            return WindowBlockFactory.create_service_box(
                parent,
                header_widget=header,
                body_widget=body,
                footer_widget=footer,
                margins=settings.get("margins", (20, 20, 20, 20)),
                spacing=settings.get("spacing", 12),
                width=settings.get("width"),
            )

        return None