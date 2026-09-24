"""
Утилиты форматирования логов.

Содержит функции для единообразного представления timestamp,
source и severity в строках логов.
"""

from datetime import datetime


def format_timestamp(dt: datetime) -> str:
    """Форматирует datetime в строку.

    Вход: dt — datetime.
    Выход: строка "%Y-%m-%d %H:%M:%S".
    Роль: единый формат времени во всех логах.
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_source(source: str) -> str:
    """Форматирует источник в квадратные скобки.

    Вход: source — идентификатор источника.
    Выход: строка "[source]".
    Роль: визуально отделяет источник от текста.
    """
    return f"[{source}]"


def format_severity(severity) -> str:
    """Форматирует Severity в строку.

    Вход: severity — Severity.
    Выход: строка "LOW", "MEDIUM" и т.д.
    Роль: единый формат уровня важности.
    """
    return severity.value.upper()