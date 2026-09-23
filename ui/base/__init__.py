"""
Пакет ui.base — абстрактные базовые классы для окон и диалогов.

Содержит инфраструктуру, которую наследуют конкретные окна, но
сами по себе эти классы не открываются и не используются напрямую.

Модули:
    dialog_setup_mixin.py — DialogSetupMixin: миксин для настройки
                            каркаса QDialog через ExtendedWindowFactory.
    base_edit_dialog.py   — BaseEditDialog: базовый диалог
                            редактирования (QDialog + миксин).

Реэкспорты здесь не делаются — импорт идёт по полному пути:
    from ui.base.base_edit_dialog import BaseEditDialog
"""

from ui.base.dialog_setup_mixin import DialogSetupMixin
from ui.base.base_edit_dialog import BaseEditDialog

__all__ = ["DialogSetupMixin", "BaseEditDialog"]