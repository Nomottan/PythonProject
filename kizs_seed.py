"""
Скрипт-сидер used_kiz.json.

Роль:
    Разовый утилитарный скрипт вне UI и вне слоёв приложения.
    Читает файл «кизы» из корня проекта (по одному полному
    неочищенному КИЗу на строку), очищает каждый КИЗ через
    KizUtils.clean_kiz_for_storage и ДОПОЛНЯЕТ used_kiz.json
    записями с фиксированными датами продажи и возврата.

    Существующие записи не перезаписываются: если очищенный КИЗ
    уже есть в used_kiz.json — он пропускается. Повторяющиеся
    КИЗы внутри входного файла также дедуплицируются.

    Файл кладётся в корень проекта и запускается командой
    `python kizs_seed.py`.

Даты (константы ниже):
    SOLD_DATE              — дата продажи, одинаковая для всех.
    RETURNED_DATE_START    — базовая дата возврата.
    RETURNED_DATE_STEP_DAYS — шаг инкремента возврата:
        0 — всем КИЗам одна и та же дата RETURNED_DATE_START;
        N — +N дней каждому следующему КИЗу.

Выход:
    Data/used_kiz.json — тот же файл, что пишет KizStorage.
    Формат записи совпадает с program-овским: compact JSON,
    ключи отсортированы, поля sold_date / returned_date
    в формате "DD-MM-YYYY".

Логирования нет: при отсутствии входного файла кидается
FileNotFoundError, чтобы прогон не завершался молчаливым
успехом. Остальные ошибки (IO, JSON) пробрасываются наверх —
их видно в трассировке.
"""

from datetime import datetime, timedelta
from pathlib import Path

from storage.fbs_kiz_storage import KizStorage
from utils.kiz_utils import KizUtils
from utils.path_manager import PathManager


# ---------- Конфигурация ----------

INPUT_FILENAME = "кизы.txt"
OUTPUT_FILENAME = "used_kiz.json"

SOLD_DATE = "19-11-2026"
RETURNED_DATE_START = "20-11-2026"
RETURNED_DATE_STEP_DAYS = 0  # 0 — всем одна дата; 1 — +1 день каждому


class KizsSeeder:
    """Сидер used_kiz.json из файла «кизы».

    Роль:
        Разовый утилитарный класс. Принимает пути, читает входной
        файл, чистит КИЗы и дополняет KizStorage. Состояния между
        запусками не держит.
    """

    def __init__(self, input_path, storage_path) -> None:
        """Конструктор.

        Вход:
            input_path — путь к файлу «кизы».
            storage_path — путь к used_kiz.json.

        Роль: сохраняет пути. Никакого IO в конструкторе.
        """
        self._input_path = Path(input_path)
        self._storage_path = Path(storage_path)

    # ---------- Публичный API ----------

    def run(self) -> None:
        """Выполняет полный прогон.

        Вход: нет.
        Выход: нет.
        Роль:
            Проверяет наличие входного файла, читает used_kiz.json
            через KizStorage, собирает новые КИЗы (с дедупликацией
            и пропуском существующих), пишет в хранилище.
        """
        if not self._input_path.is_file():
            raise FileNotFoundError(
                f"Входной файл не найден: {self._input_path}"
            )
        print("файл найден")
        storage = KizStorage(self._storage_path)
        raw_lines = self._read_input()
        new_kizs = self._collect_new(storage, raw_lines)
        self._write(storage, new_kizs)

    # ---------- Приватные методы ----------

    def _read_input(self) -> list[str]:
        """Читает файл «кизы» и возвращает непустые строки.

        Вход: нет.
        Выход:
            list[str] — непустые строки без краевых пробелов,
            в исходном порядке.

        Роль:
            utf-8-sig — на случай BOM в начале файла. Пустые
            строки выбрасываются.
        """
        text = self._input_path.read_text(encoding="utf-8-sig")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _collect_new(self, storage: KizStorage,
                     raw_lines: list[str]) -> list[str]:
        """Собирает очищенные КИЗы, которых ещё нет в хранилище.

        Вход:
            storage — KizStorage с уже загруженным used_kiz.json.
            raw_lines — строки из входного файла.

        Выход:
            list[str] — 31-символьные КИЗы в порядке первого
            появления во входном файле. Без дублей и без тех,
            что уже есть в storage.

        Роль:
            Прогоняет каждую строку через KizUtils.clean_kiz_for_storage
            (logger=None — без логов). Внутри одного входного файла
            дедуплицирует по очищенному виду: один и тот же КИЗ,
            встретившийся дважды или расщепившийся на фрагменты,
            добавляется один раз. Существующие в storage записи
            пропускаются — они не перезаписываются.
        """
        cleaned_seen: set[str] = set()
        new_kizs: list[str] = []
        for raw in raw_lines:
            for kiz in KizUtils.clean_kiz_for_storage(raw, logger=None):
                if kiz in cleaned_seen:
                    continue
                cleaned_seen.add(kiz)
                print("Киз", kiz, )
                new_kizs.append(kiz)
                if storage.get(kiz) is not None:
                    continue
                new_kizs.append(kiz)
        return new_kizs

    def _write(self, storage: KizStorage, new_kizs: list[str]) -> None:
        """Дописывает новые КИЗы в хранилище и сохраняет файл.

        Вход:
            storage — KizStorage.
            new_kizs — список очищенных КИЗов.

        Выход: нет.

        Роль:
            Открывает batch, для каждого КИЗа вызывает add_or_update
            с фиксированной датой продажи и рассчитанной датой
            возврата. По выходу из batch dirty-состояние сбрасывается
            на диск через _do_save. Если new_kizs пуст — batch
            ничего не пишет, файл остаётся как был.
        """
        with storage.batch():
            for idx, kiz in enumerate(new_kizs):
                print("Добавлен КИЗ: ", kiz, " с датой продажи: ", "SOLD_DATE", " и датой возврата: ", self._return_date_for(idx))
                storage.add_or_update(
                    kiz,
                    sold_date=SOLD_DATE,
                    returned_date=self._return_date_for(idx),
                )

    @staticmethod
    def _return_date_for(index: int) -> str:
        """Дата возврата для КИЗа с порядковым номером index.

        Вход:
            index — 0-based номер добавляемого КИЗа.

        Выход:
            строка "DD-MM-YYYY".

        Роль:
            Базовая дата — RETURNED_DATE_START, шаг —
            RETURNED_DATE_STEP_DAYS. При шаге 0 все КИЗы получают
            одну и ту же дату.
        """
        base = datetime.strptime(RETURNED_DATE_START, "%d-%m-%Y")
        dt = base + timedelta(days=index * RETURNED_DATE_STEP_DAYS)
        return dt.strftime("%d-%m-%Y")


def main() -> None:
    """Точка входа скрипта.

    Роль:
        Строит пути (вход — корень проекта, выход — Data/),
        запускает KizsSeeder.run.
    """
    root = PathManager().app_root
    input_path = root / INPUT_FILENAME
    storage_path = PathManager().get_data_file(OUTPUT_FILENAME)
    KizsSeeder(input_path, storage_path).run()


if __name__ == "__main__":
    main()