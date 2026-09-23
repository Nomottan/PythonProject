"""
Базовый диалог редактирования.

Содержит класс BaseEditDialog — общий каркас для всех форм
редактирования проекта: заголовок, кнопка закрытия, контент,
опциональные кнопки ОК/Отмена. Наследники добавляют содержимое
через _build_content и возвращают результат через _collect_result.

Роль в программе:
    Заменяет дублирование настройки окон в восьми диалогах:
    BrandEditDialog, CompanyDialog, BrandChecklistDialog,
    StringListDialog, PricesEditWindow, BrandMappingsWindow,
    BrandDetailWindow, AveragePriceInputDialog.
"""

from PySide6.QtWidgets import QDialog

from ui.base.dialog_setup_mixin import DialogSetupMixin


class BaseEditDialog(QDialog, DialogSetupMixin):
    """Базовый диалог редактирования.

    Назначение:
        Каркас формы: заголовок, закрытие, контент, ОК/Отмена.
        Наследники переопределяют:
            _build_content(layout) — добавляют виджеты.
            _collect_result() — возвращают данные (опционально).
            _validate() -> bool — проверка перед accept (опционально).

    Роль в программе:
        Единый источник каркаса. Диалоги типа 2 больше не дёргают
        ExtendedWindowFactory напрямую — только наследуются.

    Порядок MRO: BaseEditDialog → QDialog → ... → DialogSetupMixin.
    Метод setup_dialog_frame доступен наследникам через миксин.
    """

    def __init__(self, parent=None, title="", bg_color=(64, 48, 66, 0.8),
                 width=400, height=350, close_button=True, ok_cancel=True,
                 draggable=False, close_on_click_outside=False,
                 modal=True, center=True, on_close=None):
        """Конструктор.

        Вход:
            parent — родительское окно.
            title — заголовок диалога.
            bg_color — цвет фона.
            width, height — размеры по умолчанию.
            close_button — показывать ли крестик.
            ok_cancel — показывать ли кнопки ОК/Отмена.
            draggable — перетаскивание за тело.
            close_on_click_outside — закрывать при клике вне.
            modal — модальность.
            center — центрировать относительно parent.
            on_close — callback при закрытии.

        Роль: вызывает setup_dialog_frame (из DialogSetupMixin),
              получает content_layout и передаёт его в _build_content.
        """
        super().__init__(parent)
        # Результат _collect_result. По умолчанию None.
        self._result = None

        # Настраиваем каркас и получаем layout для контента.
        content_layout = self.setup_dialog_frame(
            parent=parent,
            title=title,
            bg_color=bg_color,
            width=width,
            height=height,
            close_button=close_button,
            ok_cancel=ok_cancel,
            draggable=draggable,
            close_on_click_outside=close_on_click_outside,
            modal=modal,
            center=center,
            on_close=on_close,
        )

        # Наследник наполняет layout.
        self._build_content(content_layout)

    # ---------- Публичный API ----------

    def get_result(self):
        """Возвращает результат, собранный в _collect_result.

        Выход: то, что вернул _collect_result (или None).
        Роль: вызывающий код после exec() может получить данные
              через get_result(), не завязываясь на конкретные поля.
        """
        return self._result

    # ---------- Переопределяемые методы ----------

    def accept(self) -> None:
        """Обработка кнопки ОК.

        Роль: перед закрытием вызывает _validate. Если проверка
              не прошла — диалог остаётся открытым. Иначе —
              _collect_result и super().accept().

        Если ok_cancel=False — эта кнопка не создаётся в каркасе,
        но accept() может быть вызван программно из своей
        кнопки «Сохранить» в _build_content.
        """
        if not self._validate():
            return
        self._result = self._collect_result()
        super().accept()

    def _build_content(self, layout) -> None:
        """Добавляет виджеты в content_layout.

        Вход: layout — QVBoxLayout, созданный setup_dialog_frame.
        Роль: абстрактный. Наследник обязан переопределить.
        """
        raise NotImplementedError(
            f"{type(self).__name__} должен реализовать _build_content"
        )

    def _collect_result(self):
        """Собирает результат диалога.

        Выход: любые данные (или None).
        Роль: по умолчанию возвращает None. Наследники, которым нужен
              результат (например, AveragePriceInputDialog), переопределяют.
        """
        return None

    def _validate(self) -> bool:
        """Проверка перед accept.

        Выход: True — можно закрывать; False — остаться.
        Роль: по умолчанию True. Наследники с валидацией
              (AveragePriceInputDialog, PlannerDayPickerDialog)
              переопределяют.
        """
        return True