"""
Сервис высокоуровневых операций над Counterparty.

MainConfig — хранилище config.json. Сервис знает про Counterparty,
конвертирует dict ↔ Counterparty и пишет по ключу "counterparties".
"""

from PySide6.QtCore import QObject, Signal

from models.models import Counterparty
from storage.main_config import MainConfig

class CounterpartiesService(QObject):
    """Высокоуровневые операции над Counterparty.

    Роль: между UI и MainConfig. UI не конвертирует dict ↔
          Counterparty — это работа сервиса.

    Поля:
        _config: MainConfig — хранилище config.json.
        _logger: LoggerV2 или None.

    Сигналы:
        counterparties_changed — список контрагентов сохранён.

    Публичный API:
        get_counterparties_objects, set_counterparties_objects.
    """

    counterparties_changed = Signal()

    def __init__(self, main_config: MainConfig,
                 log_manager_v2=None) -> None:
        """Конструктор.

        Вход:
            main_config — хранилище конфига.
            log_manager_v2 — LogManagerV2 или None. При None —
                             self._logger тоже None, все вызовы
                             logger.* молча пропускаются.

        Роль: сохраняет ссылки, создаёт логгер для сообщений
              о работе с моделями и записями в config.json.
        """
        super().__init__()
        self._config: MainConfig = main_config
        self._log_manager_v2 = log_manager_v2
        self._logger = None
        if log_manager_v2 is not None:
            self._logger = log_manager_v2.create_logger_v2(
                source="CounterpartiesService",
                domain="counterparties",
            )

    def get_counterparties_objects(self) -> list:
        """Возвращает список Counterparty.

        Выход: list[Counterparty].

        Роль: читает список dict-ов из конфига по ключу
              "counterparties", конвертирует через
              Counterparty.from_dict. Восстановление связей
              не требуется — у контрагентов их нет.

        Логирование:
            warning — если корень «counterparties» не список
                      или элемент не dict (битый конфиг).
            debug — количество прочитанных контрагентов.
        """
        raw_list = self._config.get("counterparties", [])
        if not isinstance(raw_list, list):
            if self._logger is not None:
                self._logger.warning(
                    "config.json: ключ 'counterparties' должен быть "
                    f"списком, получен {type(raw_list).__name__}. "
                    "Возвращаю []."
                )
            return []

        counterparties = []
        for item in raw_list:
            if not isinstance(item, dict):
                if self._logger is not None:
                    self._logger.warning(
                        "config.json: элемент списка 'counterparties' "
                        f"не является словарём ({type(item).__name__}), "
                        "пропущен."
                    )
                continue
            counterparties.append(Counterparty.from_dict(item))

        if self._logger is not None:
            self._logger.debug(
                "get_counterparties_objects: прочитано "
                f"{len(counterparties)} контрагентов"
            )
        return counterparties

    def set_counterparties_objects(self, counterparties: list) -> bool:
        """Сохраняет список Counterparty в конфиг.

        Вход: counterparties — list[Counterparty].
        Выход: True — сериализация и запись прошли; False —
               исключение перехвачено и залогировано через
               critical(can_influence=False).

        Роль: сериализует через to_dict, пишет в MainConfig по
              ключу "counterparties". MainConfig сам вызывает
              save(). После успешной записи эмитит
              counterparties_changed.

        Логирование:
            debug — количество сохранённых контрагентов.
            critical — если сериализация или запись упали.
        """
        try:
            serialized = [c.to_dict() for c in counterparties]
            self._config.set("counterparties", serialized)
            if self._logger is not None:
                self._logger.debug(
                    "set_counterparties_objects: сохранено "
                    f"{len(serialized)} контрагентов"
                )
            self.counterparties_changed.emit()
            return True
        except Exception as e:
            if self._logger is not None:
                self._logger.critical(
                    f"Ошибка сохранения контрагентов: {e}",
                    can_influence=False,
                )
            return False