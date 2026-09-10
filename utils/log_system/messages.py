class LogMessages:
    """Фабрика строк для логов.

    Все методы статические: экземпляр не нужен, состояние не хранится.
    Назначение — единый источник формулировок и форматов.
    """

    @staticmethod
    def file_copied(name: str) -> str:
        """Сообщение о копировании файла."""
        return f"Скопирован файл: {name}"

    @staticmethod
    def file_opened(name: str) -> str:
        """Сообщение об открытии файла."""
        return f"Открыт файл: {name}"

    @staticmethod
    def file_saved(name: str, size_bytes: int) -> str:
        """Многострочное сообщение о сохранении файла.

        Многострочность проверяется в test_logger.py: префикс [source]
        должен стоять на каждой строке.
        """
        return f"Файл сохранён: {name}\nРазмер: {size_bytes} байт"

    @staticmethod
    def error_reading(file: str, error: Exception) -> str:
        """Сообщение об ошибке чтения."""
        return f"Ошибка чтения {file}: {error}"

    @staticmethod
    def error_writing(file: str, error: Exception) -> str:
        """Сообщение об ошибке записи."""
        return f"Ошибка записи {file}: {error}"

    @staticmethod
    def seller_determined(name: str, file: str) -> str:
        """Сообщение об определении продавца по файлу."""
        return f"Продавец {name} определён по файлу {file}"

    @staticmethod
    def records_processed(count: int) -> str:
        """Сообщение о количестве обработанных записей."""
        return f"Обработано записей: {count}"