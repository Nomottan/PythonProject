"""
Окно архива задач планировщика.

UI-каркас без данных. Наследник _BasePlannerListWindow.
"""

from ui.windows.planner_base_window import _BasePlannerListWindow


class PlannerArchiveWindow(_BasePlannerListWindow):
    """Окно архива задач планировщика.

    Назначение:
        Показывает архив завершённых/отменённых задач. Сейчас — UI-каркас
        без данных.

    Роль в программе:
        Открывается из PlannerWindow по кнопке «Архив» модально
        (Qt.WindowModal). Визуально идентично PlannerWindow, кроме
        обесцвеченного фона и отсутствия нижних кнопок.
    """

    # 70% обесцвечивания от PlannerWindow.bg_color = (70, 60, 50):
    # avg = 60; r = 70*0.3 + 60*0.7 = 63, g = 60, b = 57.
    ARCHIVE_BG_COLOR = (63, 60, 57, 0.95)

    # В архиве нет колонки действий — только название, приоритет,
    # статус, дата. Название остаётся кнопкой — клик покажет описание.
    TASK_TYPE_COLUMNS = {
        "default": ["title", "priority", "status", "date"],
    }

    def __init__(self, parent=None):
        super().__init__(parent, "Архив", bg_color=self.ARCHIVE_BG_COLOR)
        # Нижних кнопок нет. Первая загрузка — пустая.
        self._reload_tasks()

    def _get_tasks(self):
        """Пока пусто. В будущем — из PlannerArchiveService."""
        return []