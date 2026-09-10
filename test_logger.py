"""
Изолированный тест пакета log_system.

Запуск: python test_logger.py из корня проекта.
Скрипт не трогает существующий код и работает в отдельной папке
test_work/, которая создаётся рядом с main.py.

Проверяет 7 сценариев и печатает в stdout результат каждого.
"""

import shutil
import sys
from pathlib import Path

from utils.log_system import LogManager, LogMessages
from utils.log_system.handlers import ErrorFileHandler
from utils.log_system.levels import LogLevel
from utils.log_system.record import LogRecord


def _read(path: Path) -> str:
    """Читает файл, если он существует. Иначе — пустая строка."""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _cleanup(path: Path) -> None:
    """Удаляет папку или файл, если они существуют."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def main() -> int:
    # Рабочая папка для теста — рядом со скриптом.
    test_dir = Path(__file__).parent / "test_work"
    _cleanup(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    # errors.txt пишется в app_root — это корень проекта. Чтобы не
    # засорить реальный файл, подчистим его в начале и в конце.
    # (В проде errors.txt накапливается — тест не должен ему мешать.)
    errors_path = Path(__file__).parent / "errors.txt"
    saved_errors = errors_path.read_text(encoding="utf-8") if errors_path.exists() else None

    failed = []

    # ---------- Сценарий 1: создание LogManager и Logger ----------
    try:
        manager = LogManager()
        logger = manager.create_logger(
            "TestModule.test_logger",
            test_dir,
            "log_test.txt",
        )
        assert logger is not None, "create_logger вернул None"
        print("Сценарий 1: OK")
    except Exception as e:
        failed.append(f"Сценарий 1: {e}")
        print(f"Сценарий 1: FAIL — {e}")

    # ---------- Сценарий 2: запись всех четырёх уровней ----------
    try:
        # debug выключен — debug() не должен никуда попасть.
        logger.debug("Отладочное сообщение")
        logger.info("Информационное сообщение")
        logger.warning("Предупреждение")
        logger.error("Ошибка")

        errors_text = _read(errors_path)
        log_test_text = _read(test_dir / "log_test.txt")

        # errors.txt: только WARNING и ERROR.
        assert "Предупреждение" in errors_text, "WARNING не попал в errors.txt"
        assert "Ошибка" in errors_text, "ERROR не попал в errors.txt"
        assert "Информационное сообщение" not in errors_text, "INFO попал в errors.txt"
        assert "Отладочное сообщение" not in errors_text, "DEBUG попал в errors.txt"

        # log_test.txt: INFO, WARNING, ERROR — без DEBUG.
        assert "Информационное сообщение" in log_test_text, "INFO не попал в task-лог"
        assert "Предупреждение" in log_test_text, "WARNING не попал в task-лог"
        assert "Ошибка" in log_test_text, "ERROR не попал в task-лог"
        assert "Отладочное сообщение" not in log_test_text, "DEBUG попал в task-лог"

        # debug.txt не должен существовать при выключенном debug.
        assert not (test_dir / "debug.txt").exists(), "debug.txt создан при выключенном debug"

        print("Сценарий 2: OK")
    except Exception as e:
        failed.append(f"Сценарий 2: {e}")
        print(f"Сценарий 2: FAIL — {e}")

    # ---------- Сценарий 3: включение debug ----------
    try:
        manager.set_debug(True)
        assert manager.is_debug() is True, "set_debug не переключил флаг"

        logger2 = manager.create_logger(
            "TestModule.test_logger",
            test_dir,
            "log_test.txt",
        )
        logger2.debug("Отладочное сообщение 2")
        logger2.info("Информационное сообщение 2")

        debug_text = _read(test_dir / "debug.txt")
        assert debug_text, "debug.txt пустой или не создан"
        assert "Отладочное сообщение 2" in debug_text, "DEBUG не попал в debug.txt"
        assert "Информационное сообщение 2" in debug_text, "INFO не попал в debug.txt"

        print("Сценарий 3: OK")
    except Exception as e:
        failed.append(f"Сценарий 3: {e}")
        print(f"Сценарий 3: FAIL — {e}")

    # ---------- Сценарий 4: многострочное сообщение ----------
    try:
        logger2.info("Первая строка\nВторая строка")
        debug_text = _read(test_dir / "debug.txt")
        # Каждая строка должна иметь префикс [TestModule.test_logger]
        assert "[TestModule.test_logger] Первая строка" in debug_text, \
            "первая строка без префикса"
        assert "[TestModule.test_logger] Вторая строка" in debug_text, \
            "вторая строка без префикса"

        print("Сценарий 4: OK")
    except Exception as e:
        failed.append(f"Сценарий 4: {e}")
        print(f"Сценарий 4: FAIL — {e}")

    # ---------- Сценарий 5: имитация ошибки записи ----------
    try:
        bad_path = Path("/nonexistent_dir_12345/errors.txt")
        bad_handler = ErrorFileHandler(bad_path)
        record = LogRecord(LogLevel.ERROR, "Тест ошибки записи", "TestModule")
        # emit не должен бросить исключение — ошибка уходит в stderr.
        bad_handler.emit(record)
        # Если дошли сюда — исключения не было.
        print("Сценарий 5: OK")
    except Exception as e:
        failed.append(f"Сценарий 5: {e}")
        print(f"Сценарий 5: FAIL — {e}")

    # ---------- Сценарий 6: отсутствие work_folder ----------
    try:
        # Логгер без work_folder: только errors.txt.
        logger3 = manager.create_logger("TestModule.test_logger", None)
        logger3.warning("Только в errors.txt")

        errors_text = _read(errors_path)
        assert "Только в errors.txt" in errors_text, \
            "WARNING при work_folder=None не попал в errors.txt"

        print("Сценарий 6: OK")
    except Exception as e:
        failed.append(f"Сценарий 6: {e}")
        print(f"Сценарий 6: FAIL — {e}")

    # ---------- Сценарий 7: LogMessages возвращает строки ----------
    try:
        s1 = LogMessages.file_copied("test.xlsx")
        s2 = LogMessages.file_saved("test.xlsx", 1024)
        s3 = LogMessages.error_reading("test.xlsx", Exception("boom"))
        s4 = LogMessages.seller_determined("Иванов", "отчёт.xlsx")
        s5 = LogMessages.records_processed(42)

        assert isinstance(s1, str) and "test.xlsx" in s1
        assert isinstance(s2, str) and "\n" in s2  # многострочное
        assert isinstance(s3, str) and "boom" in s3
        assert isinstance(s4, str) and "Иванов" in s4
        assert isinstance(s5, str) and "42" in s5

        print("Сценарий 7: OK")
    except Exception as e:
        failed.append(f"Сценарий 7: {e}")
        print(f"Сценарий 7: FAIL — {e}")

    # ---------- Итог ----------
    # Восстанавливаем errors.txt: тест не должен оставлять следов.
    if saved_errors is None:
        _cleanup(errors_path)
    else:
        errors_path.write_text(saved_errors, encoding="utf-8")

    if failed:
        print(f"\nПровалено: {failed}")
        return 1
    print("\nВсе сценарии пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())