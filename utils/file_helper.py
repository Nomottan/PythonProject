"""
Утилиты работы с файлами.

Класс FileHelper — единая точка копирования и проверки файлов,
а также поиска файлов продаж по формату имени. Все методы —
статические, состояние не хранится.

Роль в программе:
    Логирование идёт через LoggerV2: логика файловых операций
    не зависит от наличия логгера, но при его отсутствии
    сообщения просто не пишутся. Логгер обязан передать вызывающий
    (сервис создаёт его в начале публичного метода).
"""

import shutil
from pathlib import Path


class FileHelper:
    """Операции над файлами.

    Роль:
        Копирование, проверка существования, поиск файлов продаж
        по формату имени. Публичное API:
            copy_file_with_log(src, dst, logger, ...)
            ensure_file_exists(logger, file_path, ...)
            find_files_by_pattern(folder, pattern)
            find_sales_files(folder)
    """

    @staticmethod
    def copy_file_with_log(src, dst, logger, description="файл",
                           overwrite=False) -> bool:
        """Копирует файл с логированием через LoggerV2.

        Вход:
            src — путь к исходному файлу.
            dst — путь к целевому файлу.
            logger — LoggerV2 или None. При None сообщения
                     не пишутся, копирование всё равно выполняется.
            description — описание для сообщений («отчёт», «ЧЗ МП»).
            overwrite — перезаписывать ли существующий файл.

        Выход:
            True — файл скопирован.
            False — файл уже существует (при overwrite=False) или
                    ошибка копирования.

        Роль:
            Единая точка копирования. WARNING при пропуске,
            report при успехе, critical при ошибке. Ошибка
            не пробрасывается: вызывающий код продолжает работу.
        """
        src_path = Path(src)
        dst_path = Path(dst)

        if not overwrite and dst_path.exists():
            if logger is not None:
                logger.warning(f"Файл уже существует: {dst_path.name}")
            return False

        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            if logger is not None:
                logger.report(f"Скопирован {description}: {dst_path.name}")
            return True
        except Exception as e:
            if logger is not None:
                logger.critical(
                    f"Ошибка копирования {description}: {e}",
                    can_influence=False,
                )
            return False

    @staticmethod
    def ensure_file_exists(logger, file_path, description="файл"):
        """Проверяет, что файл существует.

        Вход:
            logger — LoggerV2 или None.
            file_path — путь к файлу.
            description — описание для сообщения об ошибке.

        Выход:
            Path к файлу или None, если файла нет.

        Роль:
            Единая проверка «есть ли файл». При отсутствии пишет
            critical(can_influence=False) — вызывающий код должен
            прервать шаг.
        """
        path = Path(file_path)
        if not path.is_file():
            if logger is not None:
                logger.critical(
                    f"Нет {description}: {path.name}",
                    can_influence=False,
                )
            return None
        return path

    @staticmethod
    def find_files_by_pattern(folder, pattern) -> list:
        """Возвращает файлы в папке по glob-шаблону.

        Вход: folder — папка; pattern — glob-шаблон.
        Выход: list[Path]. Порядок не сортируется.
        """
        folder_path = Path(folder)
        return list(folder_path.glob(pattern))

    @staticmethod
    def find_sales_files(folder) -> list:
        """Возвращает файлы продаж в папке по формату имён.

        Вход:
            folder — папка (Path или str) для поиска.

        Выход:
            list[Path] — файлы *.xlsx, в имени которых есть
            " - " и " _ " (отличительный признак нового формата
            файлов продаж: "{от_кого} - {кому} : {ИНН}.xlsx").
            Пустой список, если папки нет.

        Роль:
            Единая точка поиска файлов продаж. Используется
            SalesAccumulatorService.
        """
        folder_path = Path(folder)
        if not folder_path.exists():
            return []
        return [
            f for f in folder_path.glob("*.xlsx")
            if " - " in f.stem and " _ " in f.stem
        ]

class FilenameUtils:
    """Формирование имён файлов по шаблону.

    Роль: принимает шаблон с плейсхолдером {date} и строку даты,
          возвращает готовое имя файла. Все методы — static:
          класс не хранит состояние.
    """

    @staticmethod
    def format(template: str, date_str: str,
               index: int | None = None) -> str:
        """Подставляет дату в шаблон и опционально добавляет индекс.

        Вход:
            template — шаблон имени, например "ЧЗ_МП_{date}".
            date_str — строка даты, например "25_9_2026".
            index — опциональный числовой суффикс. None — без суффикса.

        Выход:
            Готовое имя файла. При index=None — template.format(date=date_str).
            При index=int — f"{template.format(date=date_str)}_{index}".

        Роль:
            Заменяет прямое использование ctx.format_filename в сервисах,
            которые работают без логирования.
        """
        base = template.format(date=date_str)
        if index is None:
            return base
        return f"{base}_{index}"

    @staticmethod
    def format_with_extension(template: str, date_str: str,
                              extension: str = ".xlsx",
                              index: int | None = None) -> str:
        """Подставляет дату в шаблон и добавляет расширение.

        Вход:
            template — шаблон имени, например "ЧЗ_МП_{date}".
            date_str — строка даты, например "25_9_2026".
            extension — расширение с точкой. По умолчанию ".xlsx".
            index — опциональный числовой суффикс. None — без суффикса.

        Выход:
            Имя файла с расширением. При index=None — как
            format(template, date_str) + extension.
            При index=int — с суффиксом перед расширением:
            f"{base}_{index}{extension}".

        Роль:
            Полный аналог TaskContext.format_filename, но без привязки
            к контексту задачи.
        """
        base = FilenameUtils.format(template, date_str, index)
        return base + extension