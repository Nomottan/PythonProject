"""
Утилиты для Severity.

Содержит карту цветов для подсветки сообщений по важности
в UI-компонентах (StatusLog, будущие панели логов).
"""

from services.subservices.logging.enums import Severity


# Карта цветов: важность → HEX-цвет текста.
SEVERITY_COLORS = {
    Severity.LOW: "#d4d4d4",
    Severity.MEDIUM: "#ffffff",
    Severity.HIGH: "#ffaa00",
    Severity.CRITICAL: "#ff4444",
}