"""
Базовые JSON-хранилища проекта.

Модуль содержит четыре класса с единой логикой чтения и записи:
    BaseJsonStorage   — абстрактная база: атомарная запись, чтение,
                        хуки _on_load / _default_data / _to_raw.
    ListJsonStorage   — для файлов, где корень JSON — список элементов.
    DictJsonStorage   — для файлов, где корень JSON — словарь.
    ConfigJsonStorage — упрощённый вариант для конфигов (без remove).

Использование:
    Наследники переопределяют _default_data, _to_raw и, при
    необходимости, _on_load. Для ListJsonStorage дополнительно
    _get_id, _deserialize, _serialize.

    Пример:
        class MyStorage(ListJsonStorage):
            def _default_data(self): return []
            def _to_raw(self): return [self._serialize(x) for x in self._data]
            def _get_id(self, item): return item.id
            def _deserialize(self, raw): return MyModel.from_dict(raw)
            def _serialize(self, item): return item.to_dict()
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple


class BaseJsonStorage:
    """Базовое JSON-хранилище.

    Роль: единая точка работы с JSON-файлом — атомарное чтение и
          запись, обработка отсутствующего или битого файла.
          Наследники добавляют прикладную логику: что именно лежит
          в self._data и как с этим работать.

    Поля:
        _file_path: Path — путь к JSON-файлу.
        _logger: Optional[Logger] — логгер, созданный через LogManager.
        _data: Any — данные в памяти. Тип определяет наследник
                     (list, dict или что-то ещё).

    Контракт наследника:
        _default_data() — что вернуть, если файла нет или он битый.
        _to_raw() — что записать в JSON (обычно просто self._data).
        _on_load(raw) -> (data, changed) — при необходимости
                     мигрировать старые форматы или нормализовать данные.
                     По умолчанию возвращает данные как есть.
    """
    _JSON_INDENT = 2
    _JSON_SORT_KEYS = False

    def __init__(self, file_path, log_manager=None, source: str = "") -> None:
        """Конструктор.

        Вход:
            file_path — путь к JSON-файлу (str или Path).
            log_manager — LogManager для логирования. Если None —
                          сообщения уйдут в stderr через sys.stderr.
            source — строка-идентификатор источника для лога,
                     например "MainConfig.main_config". Помогает
                     различать записи в errors.txt.

        Роль: сохраняет путь, создаёт logger при необходимости,
              вызывает load() для первичной загрузки данных.
        """
        self._file_path: Path = Path(file_path)
        self._logger = None
        if log_manager is not None and source:
            # work_folder=None: пишем только в errors.txt и UI,
            # не плодим отдельный лог-файл на каждое хранилище.
            self._logger = log_manager.create_logger(
                source=source, work_folder=None,
            )
        # _data инициализируется в load() — на этапе __init__ мы ещё
        # не знаем, есть ли файл и валиден ли он.
        self._data: Any = None
        self.load()

    # ---------- Публичный API ----------

    def load(self) -> None:
        """Загружает данные из файла.

        Роль:
            - Если файла нет — self._data = self._default_data().
            - Если файл битый — warning + self._data = self._default_data().
            - Иначе — json.load и передача в _on_load. Если _on_load
              вернул changed=True (например, миграция формата),
              тут же перезаписываем файл в новом формате.

        Вход: нет.
        Выход: нет.
        """
        if not self._file_path.exists():
            # Ленивое создание файла: он появится при первом save().
            self._data = self._default_data()
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            # Битый файл — не роняем приложение, начинаем с дефолта.
            # При следующем save() файл перезапишется корректно.
            self._log_warning(
                f"Ошибка загрузки {self._file_path.name}: {e}"
            )
            self._data = self._default_data()
            return

        data, changed = self._on_load(raw)
        self._data = data

        # Если наследник мигрировал формат — сохраняем сразу,
        # чтобы следующая загрузка шла уже по новой схеме.
        if changed:
            self.save()

    def save(self) -> None:
        """Атомарно записывает self._to_raw() в файл.

        Роль: запись во временный файл + os.replace. Так при падении
              между шагами исходный файл остаётся целым — либо старая
              версия, либо новая, но никогда половинчатая.
              Ошибки пробрасываются: вызывающий код сам решает,
              что делать.

        Вход: нет.
        Выход: нет.
        """
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        raw = self._to_raw()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", dir=self._file_path.parent, delete=False,
                suffix=".tmp", encoding="utf-8",
            ) as f:
                tmp_path = f.name
                json.dump(
                    raw, f,
                    ensure_ascii=False,
                    indent=self._JSON_INDENT,
                    sort_keys=self._JSON_SORT_KEYS,
                )
            os.replace(tmp_path, self._file_path)
        except Exception as e:
            self._log_error(
                f"Ошибка сохранения {self._file_path.name}: {e}"
            )
            # Подчищаем tmp-файл, если os.replace не сработал —
            # чтобы не копить мусор рядом с данными.
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

    # ---------- Хуки для наследников ----------

    def _on_load(self, data: Any) -> Tuple[Any, bool]:
        """Хук постобработки при чтении.

        Вход: data — то, что прочитано из JSON (list или dict).
        Выход: кортеж (data, changed):
            data — данные для self._data.
            changed — если True, файл перезаписывается сразу после
                      загрузки. Например, при миграции старого формата.

        Роль: по умолчанию ничего не делает. Наследники переопределяют,
              если нужна миграция или нормализация.
        """
        return data, False

    def _default_data(self) -> Any:
        """Что вернуть, если файла нет или он битый.

        Роль: абстрактный. Наследник решает — пустой список, пустой
              словарь или что-то другое.
        """
        raise NotImplementedError

    def _to_raw(self) -> Any:
        """Что записать в файл при save().

        Роль: абстрактный. Обычно возвращает self._data, но наследник
              может сериализовать модели в примитивы.
        """
        raise NotImplementedError

    # ---------- Логирование ----------

    def _log_warning(self, message: str) -> None:
        """Пишет WARNING в logger или stderr.

        Вход: message — текст сообщения.
        Роль: единая точка логирования предупреждений.
        """
        if self._logger is not None:
            self._logger.warning(message)
        else:
            sys.stderr.write(f"[{type(self).__name__}] WARNING: {message}\n")

    def _log_error(self, message: str) -> None:
        """Пишет ERROR в logger или stderr.

        Вход: message — текст сообщения.
        Роль: единая точка логирования ошибок.
        """
        if self._logger is not None:
            self._logger.error(message)
        else:
            sys.stderr.write(f"[{type(self).__name__}] ERROR: {message}\n")


class ListJsonStorage(BaseJsonStorage):
    """Хранилище для JSON, где корень — список элементов.

    Роль: типовой сценарий для planner_tasks.json и planner_archive.json —
          список задач с уникальным id.

    Наследник определяет:
        _get_id(item) — как достать id из элемента.
        _deserialize(raw) — превратить dict из JSON в модель.
        _serialize(item) — превратить модель в dict для JSON.

    self._data — это list[модель].
    """

    def _default_data(self) -> list:
        """По умолчанию — пустой список."""
        return []

    def _to_raw(self) -> list:
        """Сериализует каждый элемент через _serialize."""
        return [self._serialize(item) for item in self._data]

    def _on_load(self, data: Any) -> Tuple[list, bool]:
        """Десериализует каждый элемент через _deserialize.

        Вход: data — list из JSON.
        Выход: (list[модель], False). Миграция обычно не нужна —
               модель сама умеет восстанавливаться из dict.

        Роль: защита от битого корня. Если в файле не список —
              логируем warning и возвращаем пустой список.
        """
        if not isinstance(data, list):
            self._log_warning(
                f"{self._file_path.name}: ожидался список, "
                f"получен {type(data).__name__}. Использую пустой."
            )
            return [], False
        return [self._deserialize(item) for item in data], False

    # ---------- Публичный API ----------

    def get_all(self) -> list:
        """Возвращает копию списка элементов.

        Выход: list — новый список с теми же объектами. Мутация самих
               объектов видна в storage, но добавление/удаление
               элементов в копии — нет.

        Роль: безопасная выдача наружу, чтобы случайное изменение
              копии не портило внутреннее состояние.
        """
        return list(self._data)

    def add(self, item) -> None:
        """Добавляет элемент и сохраняет на диск.

        Вход: item — модель.
        Роль: append + save. Ошибка сохранения пробрасывается.
        """
        self._data.append(item)
        self.save()

    def remove(self, item_id) -> bool:
        """Удаляет элемент по id и сохраняет файл.

        Вход: item_id — идентификатор (task_id и т.п.).
        Выход: True — элемент найден и удалён; False — не найден.

        Роль: пересобирает список без элемента с нужным id. Если
              длина не изменилась — логирует warning и возвращает
              False без сохранения.
        """
        original_len = len(self._data)
        self._data = [t for t in self._data if self._get_id(t) != item_id]
        if len(self._data) == original_len:
            self._log_warning(
                f"Удаление: элемент с id={item_id} не найден "
                f"в {self._file_path.name}"
            )
            return False
        self.save()
        return True

    # ---------- Абстрактные хуки ----------

    def _get_id(self, item):
        """Как достать идентификатор из элемента.

        Вход: item — модель.
        Выход: id (обычно int или str).
        Роль: абстрактный. Нужен для remove.
        """
        raise NotImplementedError

    def _deserialize(self, raw):
        """Превратить dict из JSON в модель.

        Вход: raw — dict из прочитанного файла.
        Выход: экземпляр модели.
        Роль: абстрактный. Вызывается при загрузке.
        """
        raise NotImplementedError

    def _serialize(self, item):
        """Превратить модель в dict для JSON.

        Вход: item — модель.
        Выход: dict с примитивами.
        Роль: абстрактный. Вызывается при сохранении.
        """
        raise NotImplementedError


class DictJsonStorage(BaseJsonStorage):
    """Хранилище для JSON, где корень — словарь.

    Роль: типовой сценарий для used_kiz.json и mappings.json —
          словарь {key: value}.

    self._data — dict.
    """

    def _default_data(self) -> dict:
        """По умолчанию — пустой словарь."""
        return {}

    def _to_raw(self) -> dict:
        """Пишем self._data как есть."""
        return self._data

    def _on_load(self, data: Any) -> Tuple[dict, bool]:
        """Нормализует данные.

        Вход: data — dict из JSON.
        Выход: (dict, False) или ({}, False) при неверном корне.

        Роль: если корень не dict — warning и пустой словарь.
              Наследники могут переопределить для миграции формата.
        """
        if not isinstance(data, dict):
            self._log_warning(
                f"{self._file_path.name}: ожидался словарь, "
                f"получен {type(data).__name__}. Использую пустой."
            )
            return {}, False
        return data, False

    # ---------- Публичный API ----------

    def get(self, key, default=None):
        """Возвращает значение по ключу или default.

        Вход: key — ключ; default — что вернуть, если ключа нет.
        Выход: значение или default.
        """
        return self._data.get(key, default)

    def get_all(self) -> dict:
        """Возвращает копию словаря.

        Выход: dict — поверхностная копия. Вложенные значения
               (если это объекты) — те же ссылки.
        """
        return dict(self._data)

    def set(self, key, value) -> None:
        """Устанавливает значение и сохраняет на диск.

        Вход: key — ключ; value — значение.
        Роль: set + save. Ошибка сохранения пробрасывается.
        """
        self._data[key] = value
        self.save()

    def replace_all(self, data: dict) -> None:
        """Полностью заменяет содержимое словаря и сохраняет.

        Вход: data — новый словарь.
        Роль: нужен там, где перезаписывается ВЕСЬ словарь сразу
              (mappings.json при сохранении сопоставлений). Через
              цикл set() это делало бы N сохранений — неэффективно.
              Здесь одно сохранение.
        """
        self._data = dict(data)
        self.save()

    def remove(self, key) -> bool:
        """Удаляет значение по ключу и сохраняет.

        Вход: key — ключ.
        Выход: True — ключ был; False — не было.
        Роль: если ключа нет — warning и False без save.
        """
        if key not in self._data:
            self._log_warning(
                f"Удаление: ключ '{key}' не найден в {self._file_path.name}"
            )
            return False
        del self._data[key]
        self.save()
        return True

    def clear(self) -> None:
        """Очищает словарь и сохраняет пустой.

        Роль: удобно для полного сброса. Сохраняем сразу — иначе
              на диске останется старая версия.
        """
        self._data.clear()
        self.save()


class ConfigJsonStorage(BaseJsonStorage):
    """Хранилище для файлов-конфигураций.

    Роль: как DictJsonStorage, но без поключевого remove. Конфиг —
          это пара ключ-значение, удаление отдельных ключей редко
          осмысленно; при необходимости — set(key, None).

    self._data — dict.
    """

    def _default_data(self) -> dict:
        """По умолчанию — пустой словарь."""
        return {}

    def _to_raw(self) -> dict:
        """Пишем self._data как есть."""
        return self._data

    def _on_load(self, data: Any) -> Tuple[dict, bool]:
        """Если файл битый или не словарь — пустой конфиг.

        Вход: data — что угодно из JSON.
        Выход: (dict, False).
        """
        if not isinstance(data, dict):
            self._log_warning(
                f"{self._file_path.name}: ожидался словарь, "
                f"получен {type(data).__name__}. Использую пустой."
            )
            return {}, False
        return data, False

    # ---------- Публичный API ----------

    def get(self, key, default=None):
        """Возвращает значение по ключу или default.

        Вход: key — ключ; default — что вернуть, если ключа нет.
        Выход: значение или default.
        """
        return self._data.get(key, default)

    def get_all(self) -> dict:
        """Возвращает копию конфигурации."""
        return dict(self._data)

    def set(self, key, value) -> None:
        """Устанавливает значение и сохраняет на диск.

        Вход: key — ключ; value — значение.
        Роль: set + save. Ошибка сохранения пробрасывается.
        """
        self._data[key] = value
        self.save()