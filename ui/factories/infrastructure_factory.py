"""
Инфраструктурные фабрики: файловые диалоги и фоновые потоки.

Содержит два класса:
    ThreadFactory     — запуск функций в фоновых потоках.
    FileDialogFactory — диалоги выбора файлов и папок.

Оба класса — утилиты без стилей. Не наследуют BaseWidgetFactory.
"""

import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog


class ThreadFactory:
    """Фабрика запуска функций в фоновых потоках.

    Роль: обёртки вокруг threading.Thread с безопасной доставкой
          результата в главный поток Qt через QTimer.singleShot(0).

    Публичный API:
        create_thread — с блокировкой кнопок и колбэками.
        run_in_thread — простой запуск без блокировки.
    """

    @staticmethod
    def create_thread(parent, buttons, target_func, args=(), kwargs=None,
                      on_finished=None, error_callback=None):
        """Запускает функцию в фоновом потоке с блокировкой кнопок.

        Вход:
            parent — виджет, у которого лежат кнопки.
            buttons — список имён атрибутов-кнопок для блокировки.
            target_func — функция для выполнения в потоке.
            args — позиционные аргументы для target_func.
            kwargs — именованные аргументы.
            on_finished — вызывается в главном потоке при успехе.
            error_callback — вызывается в главном потоке при ошибке,
                             получает строку исключения.

        Выход: нет.

        Роль: блокирует кнопки на время работы, запускает функцию
              в daemon-потоке, по завершении (успех/ошибка)
              разблокирует кнопки и вызывает соответствующий колбэк.
              Проверка завершения — QTimer.singleShot(200, check).
        """
        if kwargs is None:
            kwargs = {}

        for btn_name in buttons:
            btn = getattr(parent, btn_name, None)
            if btn:
                btn.setEnabled(False)

        thread_error = None

        def wrapper():
            nonlocal thread_error
            try:
                target_func(*args, **kwargs)
            except Exception as e:
                thread_error = str(e)

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()

        def check():
            if thread.is_alive():
                QTimer.singleShot(200, check)
            else:
                for btn_name in buttons:
                    btn = getattr(parent, btn_name, None)
                    if btn:
                        btn.setEnabled(True)
                if thread_error is not None:
                    if error_callback:
                        error_callback(thread_error)
                elif on_finished:
                    on_finished()

        check()

    @staticmethod
    def run_in_thread(target_func, args=(), kwargs=None,
                      on_finished=None, error_callback=None):
        """Простой запуск функции в фоновом потоке.

        Вход:
            target_func — функция для выполнения.
            args — позиционные аргументы.
            kwargs — именованные аргументы.
            on_finished — вызывается в главном потоке с результатом.
            error_callback — вызывается при ошибке (строка исключения).

        Выход: threading.Thread.

        Роль: без блокировки кнопок. Результат доставляется в
              главный поток через QTimer.singleShot(0, ...).
        """
        if kwargs is None:
            kwargs = {}

        def wrapper():
            try:
                result = target_func(*args, **kwargs)
                if on_finished:
                    QTimer.singleShot(0, lambda: on_finished(result))
            except Exception as e:
                if error_callback:
                    QTimer.singleShot(0, lambda: error_callback(str(e)))

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return thread


class FileDialogFactory:
    """Фабрика диалогов выбора файлов и папок.

    Роль: обёртки над QFileDialog с готовыми фильтрами и
          обработкой отмены.

    Публичный API:
        open_directory_dialog — выбор папки.
        open_file_dialog — выбор одного файла.
        open_files_dialog — выбор одного или нескольких файлов.
        open_save_file_dialog — диалог сохранения.
    """

    SUPPORTED_FILES_FILTER = (
        "Поддерживаемые файлы (*.xlsx *.xls *.csv);;"
        "Excel (*.xlsx);;"
        "Excel 97-2003 (*.xls);;"
        "CSV (*.csv)"
    )

    @staticmethod
    def open_directory_dialog(parent, title="Выберите папку",
                              default_dir=None, options=None):
        """Открывает диалог выбора существующей папки.

        Вход:
            parent — родительский виджет.
            title — заголовок окна.
            default_dir — начальная папка. None → домашняя.
            options — дополнительные QFileDialog.Option.

        Выход: путь к папке (str) или None при отмене.

        Роль: единая точка выбора папок во всём проекте.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        if options is not None:
            path = QFileDialog.getExistingDirectory(
                parent, title, default_dir, options
            )
        else:
            path = QFileDialog.getExistingDirectory(
                parent, title, default_dir
            )
        return path if path else None

    @staticmethod
    def open_file_dialog(parent, title="Выберите файл",
                         default_dir=None, filter="Все файлы (*.*)"):
        """Открывает диалог выбора одного файла.

        Вход:
            parent — родительский виджет.
            title — заголовок окна.
            default_dir — начальная папка. None → домашняя.
            filter — фильтр типов файлов.

        Выход: путь к файлу (str) или None при отмене.

        Роль: единая точка выбора файлов.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            parent, title, default_dir, filter
        )
        return file_path if file_path else None

    @staticmethod
    def open_files_dialog(parent, title="Выберите файлы",
                          default_dir=None, filter="Все файлы (*.*)",
                          multiple=True):
        """Открывает диалог выбора одного или нескольких файлов.

        Вход:
            parent — родительский виджет.
            title — заголовок окна.
            default_dir — начальная папка.
            filter — строка-фильтр или список фильтров.
            multiple — True — разрешить выбор нескольких файлов.

        Выход: список путей или [] при отмене.

        Роль: единая точка выбора файлов с возможностью
              множественного выделения. При multiple=False
              возвращает список из одного элемента — для
              единообразия.
        """
        if default_dir is None:
            default_dir = str(Path.home())

        if isinstance(filter, (list, tuple)):
            filter_str = ";;".join(filter)
        else:
            filter_str = filter

        if multiple:
            files, _ = QFileDialog.getOpenFileNames(
                parent, title, default_dir, filter_str
            )
            return files if files else []
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                parent, title, default_dir, filter_str
            )
            return [file_path] if file_path else []

    @staticmethod
    def open_save_file_dialog(parent, title="Сохранить файл",
                              default_dir=None, default_file="",
                              filter="Все файлы (*.*)"):
        """Открывает диалог сохранения файла.

        Вход:
            parent — родительский виджет.
            title — заголовок окна.
            default_dir — начальная папка. None → домашняя.
            default_file — имя файла по умолчанию.
            filter — фильтр типов файлов.

        Выход: путь для сохранения (str) или None при отмене.

        Роль: единая точка сохранения файлов.
        """
        if default_dir is None:
            default_dir = str(Path.home())
        if default_file:
            start = str(Path(default_dir) / default_file)
        else:
            start = default_dir
        file_path, _ = QFileDialog.getSaveFileName(
            parent, title, start, filter
        )
        return file_path if file_path else None