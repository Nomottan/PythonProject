"""
Утилита записи txt-файлов.

Класс TextFileWriter — единая точка записи .txt: с заголовком
или без, с разделителем между заголовком и содержимым.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.subservices.logging import LoggerV2


class TextFileWriter:
    """Единая точка записи .txt.

    Роль:
        Заменяет CompareReportTxtWriter, прямые open().write()
        в сервисах. Все методы — static.
    """

    @staticmethod
    def write(path, header=None, items=None,
              separator="=" * 60, logger=None) -> bool:
        """Пишет .txt-файл с опциональным заголовком.

        Вход:
            path — путь к файлу (Path или str).
            header — строка-заголовок. None → без заголовка.
            items — список строк. None или пустой → return False
                    (файл не создаётся).
            separator — разделитель между header и items.
            logger — LoggerV2 или None.

        Выход:
            True — файл создан.
            False — items пуст или ошибка IO.

        Роль:
            При пустом items — False без создания файла.
            Иначе: открывает файл, пишет header (если задан),
            separator (если header задан), затем каждую строку
            из items. Ошибки IO → logger.critical(can_influence=False),
            return False.
        """
        if not items:
            return False

        path_obj = Path(path)
        try:
            with open(path_obj, "w", encoding="utf-8") as f:
                if header is not None:
                    f.write(header + "\n")
                    f.write(separator + "\n")
                for line in items:
                    f.write(str(line) + "\n")
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка записи в {path_obj.name}: {e}",
                    can_influence=False,
                )
            return False