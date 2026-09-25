"""
Утилиты формирования имён файлов.

Класс FilenameUtils — единая точка подстановки даты и нумерации
в шаблоны имён. Используется сервисами, которые больше не создают
TaskContext с логированием, но всё ещё формируют имена файлов.
"""


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