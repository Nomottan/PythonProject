"""
Буфер цен из отчётов МП.

Рабочий файл прогона: сохраняется в «Обработку» рабочей папки
конкретной задачи, а не в Data/. Живёт только на время прогона.
Используется ExportKizService (запись) и FinalizePricesService (чтение).
"""

import json
from pathlib import Path


class FbsBufferPrices:
    """Буфер цен между выгрузкой КИЗов и финализацией.

    Роль: переносит цены из ExportKizService в FinalizePricesService
          через JSON-файл. Не постоянное хранилище: файл привязан
          к конкретной рабочей папке прогона.

    Формат файла: {"seller_name": {"storage_kiz": int_price, ...}}.
    """

    FILENAME = "prices_from_mp.json"

    def __init__(self, processing_dir) -> None:
        """Конструктор.

        Вход: processing_dir — папка «Обработка» рабочей папки прогона.
              Именно сюда ExportKizService пишет prices_from_mp.json
              и оттуда читает FinalizePricesService.
        """
        self._path: Path = Path(processing_dir) / self.FILENAME

    # ---------- Публичный API ----------

    def load(self) -> dict:
        """Читает цены из файла.

        Выход: dict {seller_name: {storage_kiz: price}} или {} при
               отсутствии / ошибке чтения.

        Роль: ошибки не поднимаются — вызывающий код работает
              с пустым словарём. Это осознанно: прогон без цен
              допустим (пользователь введёт среднюю вручную).
        """
        if not self._path.is_file():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            return {}
        # Защита от битого корня: должен быть dict.
        return data if isinstance(data, dict) else {}

    def save(self, data: dict) -> None:
        """Записывает цены в файл.

        Вход: data — dict {seller_name: {storage_kiz: price}}.

        Роль: ошибки пробрасываются — вызывающий код (ExportKizService)
              сам решит, критично это или нет. Обычно логируется через
              ctx.log и прогон продолжается.
        """
        # Папка должна существовать: processing_dir создаётся через
        # TaskContext.processing_dir, но подстрахуемся.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def clear(self) -> None:
        """Удаляет файл, если он есть.

        Роль: очистка после успешного прогона или при отмене.
              Отсутствие файла — не ошибка.
        """
        if self._path.exists():
            self._path.unlink()