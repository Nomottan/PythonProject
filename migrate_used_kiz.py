"""
Разовая миграция used_kiz.json на новую схему.

Старый формат (плоский):
    {31-символьный КИЗ: {"sold_date": "DD-MM-YYYY",
                         "returned_date": "DD-MM-YYYY"}}

Новый формат (вложенный):
    {GTIN: {ID: {"sold": "DD-MM-YYYY",
                 "return": "DD-MM-YYYY"}}}

Поля ленивые: None не пишется.

Роль:
    Разовый утилитарный скрипт вне UI и вне слоёв приложения.
    Читает старый used_kiz.json из корня проекта, проверяет
    каждый ключ маской, переносит валидные записи в новый файл
    Data/used_kiz.json и печатает короткий отчёт.

    Невалидные ключи и записи без sold_date игнорируются —
    в новый файл не попадают. Старый файл в корне остаётся
    как резервная копия; скрипт его не удаляет.

    Файл кладётся в корень проекта и запускается командой
    `python migrate_used_kiz.py`.

Выход:
    Data/used_kiz.json — новый файл в формате KizStorage.
    Если Data/used_kiz.json уже существует, он перезаписывается.
    Перед запуском убедись, что старый файл убран из Data
    и положен в корень под именем used_kiz.json.
"""

import os
from pathlib import Path

from storage.fbs_kiz_storage import KizStorage
from utils.kiz_utils import KizUtils
from utils.path_manager import PathManager

INPUT_FILENAME = "used_kiz.json"
OUTPUT_FILENAME = "used_kiz.json"
TEMP_FILENAME = "used_kiz_migrated.json"

class KizStorageMigrator:
    """Разовый перенос used_kiz.json на новую схему.

    Роль:
        Читает старый плоский JSON, чистит ключи через
        KizUtils.clean_kiz_for_storage, пишет валидные записи
        через KizStorage во временный файл и атомарно заменяет
        целевой Data/used_kiz.json.

    Поля:
        _input_path: Path — старый used_kiz.json в корне.
        _output_path: Path — новый Data/used_kiz.json.
        _temp_path: Path — временный файл рядом с целевым.
    """

    def __init__(self, input_path, output_path) -> None:
        """Конструктор.

        Вход:
            input_path — путь к старому used_kiz.json в корне.
            output_path — путь к новому Data/used_kiz.json.

        Роль:
            Сохраняет пути. Временный файл кладётся рядом
            с целевым, чтобы os.replace был атомарным в пределах
            одной файловой системы.
        """
        self._input_path = Path(input_path)
        self._output_path = Path(output_path)
        self._temp_path = self._output_path.parent / TEMP_FILENAME

    # ---------- Публичный API ----------

    def run(self) -> None:
        """Выполняет миграцию.

        Вход: нет.
        Выход: нет.

        Роль:
            Проверяет наличие старого файла, читает его, переносит
            валидные записи во временный KizStorage, сохраняет
            временный файл, атомарно заменяет целевой и печатает
            отчёт.
        """
        if not self._input_path.is_file():
            raise FileNotFoundError(
                f"Старый файл не найден: {self._input_path}"
            )

        old_data = self._read_old()
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._temp_path.exists():
            self._temp_path.unlink()

        storage = KizStorage(self._temp_path)
        stats = self._migrate(old_data, storage)
        storage.save()
        os.replace(self._temp_path, self._output_path)
        self._print_summary(stats)

    # ---------- Приватные методы ----------

    def _read_old(self) -> dict:
        """Читает старый used_kiz.json.

        Вход: нет.

        Выход:
            dict — содержимое старого файла. Пустой dict, если
            корень не словарь.

        Роль:
            Ошибки JSON и IO пробрасываются: миграция не должна
            стартовать на битом файле.
        """
        with open(self._input_path, "r", encoding="utf-8") as f:
            data = json_load(f)
        return data if isinstance(data, dict) else {}

    def _migrate(self, old_data: dict, storage: KizStorage) -> dict:
        """Переносит записи в новый KizStorage.

        Вход:
            old_data — старый плоский словарь.
            storage — KizStorage на временном файле.

        Выход:
            dict со счётчиками: total, migrated, skipped_key,
            skipped_record, skipped_no_sold, duplicates,
            extra_fragments.

        Роль:
            Для каждого старого ключа:
                — чистит ключ до 31 символа;
                — невалидный ключ пропускает;
                — запись не-словарь пропускает;
                — запись без sold_date пропускает;
                — дубликат по очищенному ключу пропускает;
                — переносит sold_date/returned_date в sold/return.
        """
        stats = {
            "total": len(old_data),
            "migrated": 0,
            "skipped_key": 0,
            "skipped_record": 0,
            "skipped_no_sold": 0,
            "duplicates": 0,
            "extra_fragments": 0,
        }
        seen: set = set()

        for raw_key, record in old_data.items():
            cleaned = KizUtils.clean_kiz_for_storage(
                raw_key, logger=None,
            )
            if not cleaned:
                stats["skipped_key"] += 1
                continue
            if len(cleaned) > 1:
                stats["extra_fragments"] += len(cleaned) - 1
            storage_kiz = cleaned[0]

            if storage_kiz in seen:
                stats["duplicates"] += 1
                continue
            seen.add(storage_kiz)

            if not isinstance(record, dict):
                stats["skipped_record"] += 1
                continue

            sold_raw = record.get("sold_date")
            if not sold_raw:
                stats["skipped_no_sold"] += 1
                continue
            sold_date = str(sold_raw).strip()
            if not sold_date:
                stats["skipped_no_sold"] += 1
                continue

            return_raw = record.get("returned_date")
            returned_date = (
                str(return_raw).strip() if return_raw else None
            )
            if returned_date == "":
                returned_date = None

            storage.add_or_update(
                storage_kiz, sold_date, returned_date,
            )
            stats["migrated"] += 1

        return stats

    @staticmethod
    def _print_summary(stats: dict) -> None:
        """Печатает короткий отчёт о миграции.

        Вход:
            stats — счётчики из _migrate.

        Выход: нет.

        Роль:
            Разовый скрипт отчитывается в консоль. Никакого
            LoggerV2 здесь нет.
        """
        print("Миграция used_kiz.json завершена.")
        print(f"  Всего записей: {stats['total']}")
        print(f"  Перенесено: {stats['migrated']}")
        print(
            f"  Пропущено (невалидный ключ): "
            f"{stats['skipped_key']}"
        )
        print(
            f"  Пропущено (не словарь): "
            f"{stats['skipped_record']}"
        )
        print(
            f"  Пропущено (нет sold_date): "
            f"{stats['skipped_no_sold']}"
        )
        print(f"  Дубликатов: {stats['duplicates']}")
        if stats["extra_fragments"]:
            print(
                f"  Лишних фрагментов в ключах: "
                f"{stats['extra_fragments']}"
            )

def json_load(file_obj):
    """Читает JSON из открытого файла.

    Вход:
        file_obj — открытый текстовый файл.

    Выход:
        распарсенный JSON.

    Роль:
        Тонкая обёртка, чтобы не тянуть json в верхнюю часть
        модуля ради одного вызова и сохранить читаемость run.
    """
    import json
    return json.load(file_obj)

def main() -> None:
    """Точка входа скрипта.

    Роль:
        Строит пути (вход — корень проекта, выход — Data/)
        и запускает KizStorageMigrator.run.
    """
    manager = PathManager()
    input_path = manager.app_root / INPUT_FILENAME
    output_path = manager.get_data_file(OUTPUT_FILENAME)
    KizStorageMigrator(input_path, output_path).run()

if __name__ == "__main__":
    main()