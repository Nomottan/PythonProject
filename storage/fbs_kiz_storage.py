"""
Хранилище КИЗов FBS.

Переработка utils/kiz_storage.py на DictJsonStorage + Batcher.
Публичный API сохранён без изменений — вся прикладная семантика
(полная перезапись записи, формат дат, логика очистки) воспроизведена
один в один.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from utils.batcher import Batcher
from storage.base_json_storage import DictJsonStorage


class KizStorage(DictJsonStorage):
    """Хранилище КИЗов в JSON-файле.

    Формат: {КИЗ: {"sold_date": "DD-MM-YYYY", "returned_date": "DD-MM-YYYY"}}.
    Ключ — КИЗ, уже прошедший очистку снаружи (KizUtils.clean_kiz_for_storage).
    Хранилище НЕ чистит КИЗ повторно.

    Не потокобезопасен: при использовании из нескольких потоков
    одновременно возможны гонки при изменении _data и счётчиков батча.

    Поля:
        _data: dict[str, dict] — данные в памяти.
        _batcher: Batcher — менеджер отложенной записи.
        _log_path: Optional[Path] — путь к старому логу (легаси).
        _log_callback: Callable — легаси-колбэк.

    Публичный API: get, get_all, add_or_update, clear, batch, save,
    clean_old_entries, set_log_path.
    """

    # Порог промежуточного сохранения внутри батча. При долгом прогоне
    # (2–3 тыс. КИЗов) не копим всё в памяти до конца.
    BATCH_SAVE_THRESHOLD = 250
    _JSON_INDENT = None
    _JSON_SORT_KEYS = True
    def __init__(self, file_path, log_callback=None, log_manager=None) -> None:
        """Конструктор.

        Вход:
            file_path — путь к used_kiz.json.
            log_callback — легаси-колбэк (msg) -> None. Оставлен
                           для обратной совместимости.
            log_manager — LogManager. Если передан — создаём Logger
                          с source="KizStorage.fbs_kiz_storage".

        Роль: сохраняет путь и каналы логирования, создаёт Batcher
              поверх _do_save, загружает файл через базовый класс.
        """
        # Легаси-канал до super().__init__ — иначе _log_warning
        # во время загрузки его не увидит.
        self._log_callback = log_callback or (lambda msg: None)
        self._log_path: Optional[Path] = None

        super().__init__(
            file_path, log_manager,
            source="KizStorage.fbs_kiz_storage",
        )
        # Batcher поверх метода _do_save. Порог 250 — как в оригинале.
        self._batcher = Batcher(
            self._do_save, threshold=self.BATCH_SAVE_THRESHOLD,
        )

    # ---------- Хуки BaseJsonStorage ----------

    def _default_data(self) -> dict:
        """Пустой словарь, если файла нет или он битый."""
        return {}

    def _to_raw(self) -> dict:
        """Пишем self._data как есть."""
        return self._data

    # ---------- Легаси-совместимость ----------

    def set_log_path(self, work_dir) -> None:
        """Устанавливает путь к старому логу kiz_validation.log.

        Вход: work_dir — рабочая папка задачи.
        Выход: нет.

        Роль: сохранён для обратной совместимости с sells_fbs_service.py.
              При активном LogManager этот путь не используется —
              записи идут через errors.txt и UI. Если LogManager
              не передан — fallback-логирование пойдёт в этот файл.
        """
        self._log_path = Path(work_dir) / "kiz_validation.log"

    def _log(self, message: str) -> None:
        """Легаси-fallback логирования.

        Вход: message — текст.
        Роль: используется только если LogManager не передан.
              Пишет в kiz_validation.log (если путь задан) и в колбэк.
        """
        import sys
        if self._log_path is not None:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] {message}\n")
            except Exception as error:
                sys.stderr.write(
                    f"[KizStorage] Не удалось записать в {self._log_path}: {error}\n"
                )
        try:
            self._log_callback(message)
        except Exception as error:
            sys.stderr.write(f"[KizStorage] Ошибка log_callback: {error}\n")

    def debug(self, message: str) -> None:
        """Отладочное сообщение. В fallback-режиме игнорируется."""
        if self._logger is not None:
            self._logger.debug(message)

    def info(self, message: str) -> None:
        """Информационное сообщение."""
        if self._logger is not None:
            self._logger.info(message)
        else:
            self._log(message)

    def warning(self, message: str) -> None:
        """Предупреждение."""
        if self._logger is not None:
            self._logger.warning(message)
        else:
            self._log(f"[WARNING] {message}")

    def error(self, message: str) -> None:
        """Ошибка."""
        if self._logger is not None:
            self._logger.error(message)
        else:
            self._log(f"[ERROR] {message}")

    # ---------- Батчинг ----------

    def batch(self):
        """Открывает контекст отложенной записи.

        Выход: контекст-менеджер. При `with ... as s` s == self (storage),
               как в оригинале.
        """
        return _BatchContext(self)

    def _do_save(self) -> None:
        """Callback для Batcher: реальная запись на диск.

        Роль: вызывается только из Batcher, идёт в BaseJsonStorage.save
              напрямую — минуя наш публичный save(), чтобы не было
              рекурсии.
        """
        super().save()

    def save(self) -> None:
        """Публичный save: сохраняет на диск немедленно.

        Роль: если кто-то снаружи вызывает save() вне batch — ожидает
              мгновенной записи. Помечаем dirty и сразу flush.
        """
        self._batcher.mark_dirty()
        self._batcher.flush()

    # ---------- Операции ----------

    def get(self, kiz: str) -> Optional[dict]:
        """Возвращает запись по КИЗу или None."""
        return self._data.get(kiz)

    def add_or_update(self, kiz, sold_date,
                      returned_date=None) -> None:
        """Добавляет или обновляет запись КИЗа.

        Вход:
            kiz — строка КИЗа (уже очищенная снаружи).
            sold_date — дата продажи (строка "DD-MM-YYYY" или None).
            returned_date — дата возврата (строка "DD-MM-YYYY" или None).

        Выход: нет.

        Роль: единственная точка изменения _data. Семантика —
              ПОЛНАЯ ПЕРЕЗАПИСЬ: оба поля всегда устанавливаются
              из аргументов, включая None. Это нужно для повторной
              продажи — validate_for_sale передаёт returned_date=None
              и тем самым стирает прежний возврат.
        """
        self._data[kiz] = {
            "sold_date": sold_date,
            "returned_date": returned_date,
        }
        self._batcher.mark_dirty()

    def clean_old_entries(self, months: int = 1) -> int:
        """Удаляет записи старше N месяцев по дате продажи.

        Вход: months — порог в месяцах (1 месяц = 30 дней).
        Выход: количество удалённых записей.

        Роль: используется при подготовке к прогону. Считаем возраст
              по sold_date формата "%d-%m-%Y". Записи без sold_date
              или с непарсящейся датой пропускаются.
        """
        if not self._data:
            self.info("Очистка: нет записей для удаления.")
            return 0

        cutoff = datetime.now() - timedelta(days=months * 30)
        to_delete = []
        for kiz, record in self._data.items():
            sold_date_str = record.get("sold_date")
            if not sold_date_str:
                continue
            try:
                sold_date = datetime.strptime(sold_date_str, "%d-%m-%Y")
                if sold_date < cutoff:
                    to_delete.append(kiz)
            except ValueError:
                self.info(
                    f"Очистка: некорректная дата продажи "
                    f"'{sold_date_str}' для КИЗа {kiz}, запись пропущена"
                )
                continue

        if not to_delete:
            self.info(f"Очистка: нет записей старше {months} месяца(ев).")
            return 0

        for kiz in to_delete:
            del self._data[kiz]

        # Немедленная запись — операция разовая, батчинг не нужен.
        self._batcher.mark_dirty()
        self._batcher.flush()
        self.info(f"Очистка завершена: удалено {len(to_delete)} записей.")
        return len(to_delete)

    def get_all(self) -> dict:
        """Возвращает копию словаря записей."""
        return self._data.copy()

    def clear(self) -> None:
        """Очищает хранилище и сохраняет пустой файл."""
        self._data.clear()
        super().save()
        self.warning("Все записи удалены.")


class _BatchContext:
    """Контекст-менеджер батча для KizStorage.

    Роль: увеличивает глубину вложенности у хранилища. add_or_update
          внутри батча только помечает dirty. На выходе с внешнего
          уровня — flush, если были изменения.

    Поля:
        _storage: KizStorage — родительское хранилище.
    """

    def __init__(self, storage: "KizStorage") -> None:
        """Конструктор.

        Вход: storage — хранилище, чей батч открываем.
        """
        self._storage = storage

    def __enter__(self) -> "KizStorage":
        """Вход: увеличиваем глубину. Возвращает сам storage —
        чтобы `with storage.batch() as s:` работал как раньше."""
        self._storage._batcher._depth += 1
        return self._storage

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Выход: уменьшаем глубину. На внешнем уровне — flush."""
        self._storage._batcher._depth -= 1
        if self._storage._batcher._depth == 0 and self._storage._batcher._dirty:
            self._storage._batcher._flush_callback()
            self._storage._batcher._dirty = False
            self._storage._batcher._changes = 0
        return False