"""
Буфер отложенной записи продаж КИЗов.

Файл pending_kiz.json живёт в папке «Обработка» текущего прогона.
Используется между шагами «Подготовка» и «Обработка»:
    PreparationService собирает решения evaluate_for_sale
    и складывает их сюда;
    FinalProcessingService после создания ИТОГ-файлов
    применяет их к used_kiz.json и удаляет буфер.

Формат: {31-символьный КИЗ: "DD-MM-YYYY"}.
"""

import json
import os
from pathlib import Path

class FbsBufferKiz:
    """Буфер отложенных продаж КИЗов.

    Роль:
        Переносит решения «КИЗ продан» из «Подготовки» в «Обработку»
        через JSON-файл. Не постоянное хранилище: файл привязан
        к конкретной рабочей папке прогона и удаляется после
        успешной записи в used_kiz.json.

    Поля:
        _path: Path — путь к pending_kiz.json.
    """

    FILENAME = "pending_kiz.json"

    def __init__(self, processing_dir) -> None:
        """Конструктор.

        Вход:
            processing_dir — папка «Обработка» рабочей папки прогона.

        Роль:
            Сохраняет путь. Файл не создаётся и не читается
            в конструкторе.
        """
        self._path: Path = Path(processing_dir) / self.FILENAME

    # ---------- Публичный API ----------

    def load(self) -> dict:
        """Читает буфер.

        Вход: нет.

        Выход:
            dict {31-символьный КИЗ: "DD-MM-YYYY"} или {} при
            отсутствии файла, ошибке чтения или неверном корне.

        Роль:
            Ошибки не пробрасываются: вызывающий код работает
            с пустым словарём. Пустой буфер означает «нечего
            применять».
        """
        if not self._path.is_file():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, data: dict) -> None:
        """Атомарно записывает буфер.

        Вход:
            data — dict {31-символьный КИЗ: "DD-MM-YYYY"}.

        Выход: нет.

        Роль:
            Пишет во временный файл рядом и заменяет целевой через
            os.replace. При сбое исходный буфер остаётся целым.
            Ошибки пробрасываются: решение, что делать, принимает
            сервис.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def clear(self) -> None:
        """Удаляет буфер, если он есть.

        Вход: нет.
        Выход: нет.

        Роль:
            Вызывается в начале «Подготовки» (чтобы не подхватить
            прошлый прогон) и после успешной записи в used_kiz.json.
            Отсутствие файла — не ошибка.
        """
        if self._path.exists():
            self._path.unlink()