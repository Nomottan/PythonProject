"""
Панель фильтров: FilterPanel.

Содержит FilterPanel — обертку над мастер-дропдауном, внутри
которого лежат категории (тоже DropdownComposite).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from ui.factories.droplist_factory import DroplistFactory
from ui.factories.filter_factory import FilterFactory
from ui.styles import ColorCalculator
from utils.filter_utils import FieldDef, FilterCore


class FilterPanel(QWidget):
    """Панель фильтров.

    Роль:
        Управляет мастер-дропдауном («Фильтры») и логикой тристейтов.
        Всё позиционирование и скролл делегируются DropdownComposite.
    """

    filtered_changed = Signal(list)

    def __init__(self, parent, field_defs: list, get_source, bg_color):
        super().__init__(parent)
        self._field_defs = field_defs
        self._get_source = get_source
        self.bg_color = bg_color
        self._selected: dict = {fd.name: set() for fd in field_defs}
        self._categories: dict = {}
        self._tristate_checkboxes: dict = {}

        self._build_ui()

    def _build_ui(self) -> None:
        """Создает мастер-дропдаун и помещает внутрь него категории."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Затемняем фон панели (отнимаем 2/7 от каждого канала)
        self._popup_bg_color = ColorCalculator.derive(
            self.bg_color,
            r_fn=lambda r: r - (r * 2 // 7),
            g_fn=lambda g: g - (g * 2 // 7),
            b_fn=lambda b: b - (b * 2 // 7),
            alpha=1.0
        )

        self._master_dropdown = DroplistFactory.create_dropdown(self, config={
            "settings": {
                "trigger_items": [{"label": "Фильтры"}],
                "close_on_select": False,
                "popup_bg_color": self._popup_bg_color,
                "layout_direction": "horizontal",
                "preferred_direction": "right",
            }
        })
        # Фиксируем ширину кнопки (чтобы она не растягивалась)
        self._master_dropdown.setFixedWidth(120)

        layout.addWidget(self._master_dropdown, alignment=Qt.AlignLeft)
        layout.addStretch()

        # Создаем контейнер для ряда категорий
        self._categories_row = QWidget()
        self._categories_row.setObjectName("filter_categories_row")
        self._categories_row.setStyleSheet("background: transparent;")  # <--- ДОБАВИТЬ
        row_layout = QHBoxLayout(self._categories_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        row_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for fd in self._field_defs:
            category = self._build_category(self._categories_row, fd)
            self._categories[fd.name] = category
            row_layout.addWidget(category)

        # Добавляем контейнер с категориями в мастер-дропдаун
        self._master_dropdown.add_item({"widget": self._categories_row})

        # Обновляем данные при каждом открытии панели
        self._master_dropdown.opened.connect(self.refresh)
        self.refresh()

    def _build_category(self, parent, field_def: FieldDef):
        """Создаёт DropdownComposite для одной категории."""
        # Тристейт-чекбокс рисуется от единого цвета панели
        tristate_cb = FilterFactory.create_tristate_checkbox(
            parent, self._popup_bg_color, text=""
        )
        tristate_cb.clicked.connect(
            lambda checked, name=field_def.name: self._on_tristate_clicked(name, checked)
        )
        self._tristate_checkboxes[field_def.name] = tristate_cb

        dropdown_config = {
            "settings": {
                "debug": self._master_dropdown.settings.get("debug", False),
                "is_category": True,
                "multi_select": True,
                "close_on_select": False,
                "sync_checkboxes": True,
                "popup_bg_color": self._popup_bg_color,
                "trigger_items": [
                    {"widget": tristate_cb},
                    {"label": field_def.label}
                ],
                "layout_direction": "vertical",
            }
        }

        category = DroplistFactory.create_dropdown(parent, config=dropdown_config)
        category.selection_changed.connect(
            lambda data, name=field_def.name: self._on_category_changed(name, data)
        )
        return category

    # ---------- Логика тристейта ----------

    def _on_tristate_clicked(self, category_name: str, checked: bool) -> None:
        """Клик по тристейт-чекбоксу."""
        category = self._categories[category_name]
        if checked:
            category.select_all()
        else:
            category.clear_selection()

    def _update_tristate(self, category_name: str) -> None:
        """Обновляет состояние тристейт-чекбокса."""
        cb = self._tristate_checkboxes[category_name]
        selected = self._selected[category_name]

        source = self._get_source()
        fd = next(f for f in self._field_defs if f.name == category_name)
        all_values = set(FilterCore.collect_values(source, fd))

        cb.blockSignals(True)
        if not selected:
            cb.setCheckState(Qt.Unchecked)
        elif selected == all_values:
            cb.setCheckState(Qt.Checked)
        else:
            cb.setCheckState(Qt.PartiallyChecked)
        cb.blockSignals(False)

    def _on_category_changed(self, category_name: str, data) -> None:
        """Реакция на изменение выбора в категории."""
        match data:
            case None:
                self._selected[category_name] = set()
            case list():
                self._selected[category_name] = set(data)
            case _:
                self._selected[category_name] = {data}

        self._update_tristate(category_name)

        # ДИНАМИЧЕСКОЕ ОБНОВЛЕНИЕ:
        # Пересобираем другие категории, исключая ту, с которой сейчас работает пользователь
        self.refresh(exclude=category_name)

        filtered = self.get_filtered()

        if self._master_dropdown.settings.get("debug", False):
            prefix = "[DEBUG/ui.widgets.filter_panel/FilterPanel/_on_category_changed]"
            print(f"{prefix} Категория '{category_name}' изменилась.")
            print(f"{prefix}   Выбрано: {self._selected[category_name]}")
            print(f"{prefix}   Отфильтровано элементов: {len(filtered)}")

        self.filtered_changed.emit(filtered)

    # ---------- Публичный API ----------

    def get_filtered(self) -> list:
        """Возвращает отфильтрованный список."""
        source = self._get_source()
        predicates = [
            FilterCore.build_predicate(fd, self._selected[fd.name])
            for fd in self._field_defs
        ]
        return FilterCore.apply(source, predicates)

    def refresh(self, exclude: str = None) -> None:
        """Пересобирает значения категорий с учетом других фильтров.

        Вход:
            exclude — имя категории, которую не нужно пересобирать
                      (обычно та, с которой сейчас работает пользователь).
        """
        source = self._get_source()

        for fd in self._field_defs:
            if fd.name == exclude:
                continue  # Не трогаем список, который сейчас открыт у пользователя

            # 1. Собираем предикаты от ВСЕХ ДРУГИХ категорий
            other_predicates = []
            for other_fd in self._field_defs:
                if other_fd.name != fd.name:
                    other_predicates.append(
                        FilterCore.build_predicate(other_fd, self._selected[other_fd.name])
                    )

            # 2. Фильтруем общий список задач только по этим предикатам
            filtered_source = FilterCore.apply(source, other_predicates)

            # 3. Собираем доступные значения для текущей категории из этого списка
            values = FilterCore.collect_values(filtered_source, fd)

            # 4. Убираем из выбранных те значения, которых больше нет в списке
            self._selected[fd.name] &= set(values)

            # 5. Пересобираем UI
            category = self._categories[fd.name]
            category.clear_items()

            for val in values:
                cb = FilterFactory.create_value_checkbox(
                    category, str(val),
                    checked=(val in self._selected[fd.name]),
                    bg_color=self._popup_bg_color
                )
                category.add_item({"widget": cb, "data": val})

            self._update_tristate(fd.name)

    def reset(self) -> None:
        """Сбрасывает все категории."""
        for fd in self._field_defs:
            self._selected[fd.name] = set()
            self._categories[fd.name].clear_selection()
            self._update_tristate(fd.name)

    def collapse(self) -> None:
        """Публичное сворачивание панели (закрывает мастер-дропдаун)."""
        self._master_dropdown.close()

    def is_open(self) -> bool:
        """Возвращает состояние раскрытия панели."""
        return (
            self._master_dropdown._popup is not None
            and self._master_dropdown._popup.isVisible()
        )
