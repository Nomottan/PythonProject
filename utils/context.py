"""
Контекст выполнения задачи: рабочая папка и её подпапки.

Содержит TaskContext — dataclass с путями. Логирования здесь нет:
все логи пишутся через LoggerV2 внутри сервисов. TaskContext
отвечает только за:
    - определение рабочей папки задачи (work_folder);
    - ленивое создание подпапок «Логи», «Отчёты», «Продажи»,
      «Обработка» по запросу;
    - сохранение даты запуска (today, date_str).

Роль в программе:
    Создаётся в начале публичного метода сервиса, когда известен
    target_dir и нужно подготовить структуру папок. Сервис сам
    создаёт LoggerV2, передавая ему work_folder=ctx.logs_dir.

    Поле log_filename сохранено для совместимости вызовов — сервисы
    продолжают передавать историческое имя лог-файла третьим
    аргументом. TaskContext его не использует.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from utils.path_manager import PathManager


@dataclass
class TaskContext:
    """Контекст выполнения задачи.

    Поля:
        target_dir: str — корневая папка, куда складываются задачи.
        subfolder_template: str — шаблон имени подпапки, например
                                  "ЧЗ_МП_{date}".
        log_filename: str — историческое имя лог-файла задачи.
                            Не используется внутри TaskContext —
                            нужно только чтобы вызовы сервисов
                            не менялись.
        subfolders: list | None — список разрешённых подпапок.
                                  None → только «Логи».
                                  Значения вне ALL_SUBFOLDERS
                                  игнорируются.

    Атрибуты экземпляра (создаются в __post_init__):
        today: date — дата создания контекста.
        date_str: str — today в формате "D_M_YYYY".
        work_folder: Path — корневая папка задачи.
        _enabled: set[str] — какие подпапки разрешены.
        _subfolder_cache: dict[str, Path] — кэш созданных подпапок.

    Свойства:
        logs_dir, reports_dir, sales_dir, processing_dir — Path или
        None, если подпапка не разрешена. Создаются лениво при
        первом обращении.
    """

    # Допустимые имена подпапок. Всё, чего нет в множестве,
    # игнорируется — защита от опечаток в subfolders.
    ALL_SUBFOLDERS = {"Логи", "Отчёты", "Продажи", "Обработка"}

    target_dir: str
    subfolder_template: str
    log_filename: str
    subfolders: Optional[list] = None

    # Внутренние поля dataclass — инициализируются в __post_init__.
    today: date = field(init=False)
    date_str: str = field(init=False)
    work_folder: Path = field(init=False)
    _enabled: set = field(init=False)
    _subfolder_cache: dict = field(init=False)

    def __post_init__(self) -> None:
        """Инициализирует дату, рабочую папку и кэш подпапок.

        Роль: единственный хук dataclass — здесь создаётся work_folder
              (создаётся на диске сразу) и вычисляется date_str.
              Подпапки не создаются — они ленивые, через свойства.
        """
        self.today = date.today()
        self.date_str = (
            f"{self.today.day}_{self.today.month}_{self.today.year}"
        )

        subfolder_name = self.subfolder_template.format(date=self.date_str)
        self.work_folder = PathManager.ensure_dir(
            Path(self.target_dir) / self.date_str / subfolder_name
        )

        # Разрешённые подпапки. «Логи» добавляется всегда:
        # LoggerV2 пишет туда отчёты и журналы.
        requested = set(self.subfolders or [])
        self._enabled = (requested & self.ALL_SUBFOLDERS) | {"Логи"}
        self._subfolder_cache = {}

    # ---------- Ленивые подпапки ----------

    def _get_subfolder(self, name: str) -> Optional[Path]:
        """Лениво создаёт подпапку при первом обращении.

        Вход:
            name — имя подпапки (Логи, Отчёты, Продажи, Обработка).

        Выход:
            Path к папке или None, если папка не разрешена.

        Роль:
            Единая точка создания подпапок. Кэширует результат,
            чтобы не вызывать mkdir повторно.
        """
        if name not in self._enabled:
            return None
        if name not in self._subfolder_cache:
            self._subfolder_cache[name] = PathManager.ensure_dir(
                self.work_folder / name
            )
        return self._subfolder_cache[name]

    @property
    def logs_dir(self) -> Optional[Path]:
        """Папка «Логи» — журналы и сводные отчёты сервисов.

        Создаётся при первом обращении. Всегда доступна (входит
        в _enabled принудительно).
        """
        return self._get_subfolder("Логи")

    @property
    def reports_dir(self) -> Optional[Path]:
        """Папка «Отчёты» — скопированные отчёты МП и ЧЗ_МП.

        None, если подпапка не входила в subfolders.
        """
        return self._get_subfolder("Отчёты")

    @property
    def sales_dir(self) -> Optional[Path]:
        """Папка «Продажи» — файлы продаж между продавцами.

        None, если подпапка не входила в subfolders.
        """
        return self._get_subfolder("Продажи")

    @property
    def processing_dir(self) -> Optional[Path]:
        """Папка «Обработка» — txt, предитоговые xlsx, буферы цен.

        None, если подпапка не входила в subfolders.
        """
        return self._get_subfolder("Обработка")
