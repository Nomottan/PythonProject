"""
Хранилище КИЗов FBS.

Формат хранения: {GTIN: {ID: {"sold": "DD-MM-YYYY", "return": "DD-MM-YYYY"}}}.
Поля ленивые: отсутствующий ключ означает None.
Публичный API: get, add_or_update, remove_many, clear, batch, save,
clean_old_entries, count, full_kizs, info, report, warning.

Логирование — через LoggerV2. Публичные каналы info/report/warning
оставлены для KizValidator: он транслирует свои сообщения в хранилище.
"""

from datetime import datetime, timedelta
from typing import Optional

from utils.batcher import Batcher
from utils.kiz_utils import KizUtils
from storage.base_json_storage import DictJsonStorage


class KizStorage(DictJsonStorage):
    """Хранилище КИЗов в JSON-файле.

    Формат: {GTIN: {ID: {"sold": "DD-MM-YYYY", "return": "DD-MM-YYYY"}}}.
    Ключи GTIN и ID извлекаются из 31-символьного КИЗа.
    Хранилище НЕ чистит КИЗ повторно: на вход ожидается КИЗ,
    уже прошедший KizUtils.clean_kiz_for_storage.

    Не потокобезопасен: при использовании из нескольких потоков
    одновременно возможны гонки при изменении _data и счётчиков батча.

    Поля:
        _data: dict[str, dict[str, dict]] — данные в памяти.
        _batcher: Batcher — менеджер отложенной записи.

    Публичный API: get, add_or_update, remove_many, clear, batch, save,
    clean_old_entries, count, full_kizs, info, report, warning.
    get_all() унаследован от DictJsonStorage и возвращает вложенное
    представление; для плоского множества КИЗов — full_kizs().
    """

    # Порог промежуточного сохранения внутри батча. При долгом прогоне
    # (2–3 тыс. КИЗов) не копим всё в памяти до конца.
    BATCH_SAVE_THRESHOLD = 250
    _JSON_INDENT = None
    _JSON_SORT_KEYS = True

    def __init__(self, file_path, log_manager_v2=None) -> None:
        """Конструктор.

        Вход:
            file_path — путь к used_kiz.json.
            log_manager_v2 — LogManagerV2. Если передан — создаём
                             LoggerV2 с source="KizStorage.fbs_kiz_storage".

        Роль: сохраняет путь, создаёт Batcher поверх _do_save,
              загружает файл через базовый класс.
        """
        super().__init__(
            file_path, log_manager_v2,
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

    # ---------- Публичные каналы логирования ----------

    def info(self, message: str) -> None:
        """Информационное сообщение.

        Вход: message — текст.
        Роль: канал для KizValidator — сводные сообщения о валидации.
        """
        if self._logger is not None:
            self._logger.info(message)

    def report(self, message: str) -> None:
        """Пошаговое сообщение журнала.

        Вход: message — текст.
        Роль: канал для KizValidator — диагностика по каждому КИЗу
              (списание, отсев, возврат). Не попадает в info-файл
              домена, идёт в report-журнал LoggerV2.
        """
        if self._logger is not None:
            self._logger.report(message)

    def warning(self, message: str) -> None:
        """Предупреждение.

        Вход: message — текст.
        Роль: канал для KizValidator — некритичные аномалии
              (битая дата, отсутствие записи).
        """
        if self._logger is not None:
            self._logger.warning(message)

    # ---------- Приватные помощники ----------

    def _get_bucket(self, gtin: str) -> dict:
        """Возвращает GTIN-бакет, создавая его при необходимости.

        Вход:
            gtin — 14-символьный GTIN.

        Выход:
            dict — словарь {ID: запись} внутри self._data.

        Роль:
            Единая точка ленивого создания бакета. Используется
            add_or_update; чтение (get) обходится без создания.
        """
        return self._data.setdefault(gtin, {})

    def _drop_empty_bucket(self, gtin: str) -> None:
        """Удаляет GTIN-бакет, если он опустел.

        Вход:
            gtin — 14-символьный GTIN.

        Выход: нет.

        Роль:
            После удаления последней записи бакет не должен
            оставаться в файле пустым словарём.
        """
        bucket = self._data.get(gtin)
        if bucket is not None and not bucket:
            del self._data[gtin]

    @staticmethod
    def _set_field(record: dict, key: str, value: Optional[str]) -> None:
        """Устанавливает или удаляет ленивое поле записи.

        Вход:
            record — словарь записи {"sold": ..., "return": ...}.
            key — имя поля ("sold" или "return").
            value — строка даты или None.

        Выход: нет.

        Роль:
            None означает «поля нет»: ключ удаляется. Не-None —
            значение записывается. Так работает ленивая схема.
        """
        if value is None:
            record.pop(key, None)
        else:
            record[key] = value

    # ---------- Батчинг ----------

    def batch(self):
        """Открывает контекст отложенной записи.

        Выход: контекст-менеджер Batcher.

        Роль:
            Прокси к Batcher.batch(). `as` в `with storage.batch()`
            больше не возвращает storage — ни один вызывающий код
            этим не пользуется.
        """
        return self._batcher.batch()

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
        """Возвращает копию записи по КИЗу или None.

        Вход:
            kiz — 31-символьный КИЗ.

        Выход:
            dict {"sold": ..., "return": ...} с только присутствующими
            полями или None, если записи нет.

        Роль:
            Единая точка чтения. Разбирает КИЗ на GTIN и ID через
            KizUtils.parse_storage_kiz; невалидный КИЗ даёт None.
            Возвращает копию, чтобы вызывающий код не мог случайно
            изменить внутреннее состояние хранилища.
        """
        parsed = KizUtils.parse_storage_kiz(kiz)
        if parsed is None:
            return None
        gtin, identifier = parsed
        bucket = self._data.get(gtin)
        if not bucket:
            return None
        record = bucket.get(identifier)
        if record is None:
            return None
        return dict(record)

    def add_or_update(self, kiz, sold_date,
                      returned_date=None) -> None:
        """Добавляет или обновляет запись КИЗа.

        Вход:
            kiz — 31-символьный КИЗ (уже очищенный снаружи).
            sold_date — дата продажи (строка "DD-MM-YYYY" или None).
            returned_date — дата возврата (строка "DD-MM-YYYY" или None).

        Выход: нет.

        Роль:
            Единственная точка изменения _data. Разбирает КИЗ на
            GTIN и ID, пишет ленивые поля: None удаляет ключ,
            не-None записывает. Пустая запись удаляется вместе
            с опустевшим бакетом. Невалидный КИЗ — warning и
            пропуск (валидация уже выполнена в clean_kiz_for_storage;
            это защита от вызова в обход очистки).
        """
        parsed = KizUtils.parse_storage_kiz(kiz)
        if parsed is None:
            self.warning(
                f"add_or_update: невалидный КИЗ {kiz!r}, "
                f"запись пропущена"
            )
            return
        gtin, identifier = parsed
        bucket = self._get_bucket(gtin)
        record = bucket.setdefault(identifier, {})
        self._set_field(record, "sold", sold_date)
        self._set_field(record, "return", returned_date)
        if not record:
            bucket.pop(identifier, None)
            self._drop_empty_bucket(gtin)
        self._batcher.mark_dirty()

    def remove_many(self, keys) -> int:
        """Удаляет пачку записей по ключам.

        Вход:
            keys — итерируемое 31-символьных КИЗов. Пустое → no-op.

        Выход:
            int — сколько записей реально удалено (отсутствующие
            и невалидные ключи не считаются).

        Роль:
            Единая точка массового удаления. Разбирает каждый КИЗ
            на GTIN и ID, удаляет запись и опустевший бакет.
            Правки — только в памяти и через _batcher.mark_dirty().
            save() не вызывается: сохранение на диск делает либо
            внешний batch(), либо явный flush().
        """
        removed = 0
        for kiz in keys:
            parsed = KizUtils.parse_storage_kiz(kiz)
            if parsed is None:
                continue
            gtin, identifier = parsed
            bucket = self._data.get(gtin)
            if not bucket or identifier not in bucket:
                continue
            del bucket[identifier]
            removed += 1
            self._drop_empty_bucket(gtin)
        if removed > 0:
            self._batcher.mark_dirty()
        return removed

    def clean_old_entries(self, months: int = 1) -> int:
        """Удаляет записи старше N месяцев по дате продажи.

        Вход: months — порог в месяцах (1 месяц = 30 дней).
        Выход: количество удалённых записей.

        Роль: используется при подготовке к прогону. Обходит
              вложенную схему GTIN → ID → запись, считает возраст
              по полю "sold" формата "%d-%m-%Y". Записи без "sold"
              или с непарсящейся датой пропускаются. После удаления
              опустевшие бакеты убираются.
        """
        if not self._data:
            self.info("Очистка: нет записей для удаления.")
            return 0

        cutoff = datetime.now() - timedelta(days=months * 30)
        to_delete = []
        for gtin, bucket in self._data.items():
            for identifier, record in bucket.items():
                sold_date_str = record.get("sold")
                if not sold_date_str:
                    continue
                try:
                    sold_date = datetime.strptime(
                        sold_date_str, "%d-%m-%Y"
                    )
                    if sold_date < cutoff:
                        to_delete.append((gtin, identifier))
                except ValueError:
                    self.info(
                        f"Очистка: некорректная дата продажи "
                        f"'{sold_date_str}' для КИЗа "
                        f"{KizUtils.build_storage_kiz(gtin, identifier)}, "
                        f"запись пропущена"
                    )
                    continue

        if not to_delete:
            self.info(f"Очистка: нет записей старше {months} месяца(ев).")
            return 0

        for gtin, identifier in to_delete:
            bucket = self._data.get(gtin)
            if not bucket:
                continue
            bucket.pop(identifier, None)
            self._drop_empty_bucket(gtin)

        # Немедленная запись — операция разовая, батчинг не нужен.
        self._batcher.mark_dirty()
        self._batcher.flush()
        self.info(f"Очистка завершена: удалено {len(to_delete)} записей.")
        return len(to_delete)

    def count(self) -> int:
        """Возвращает количество КИЗов в хранилище.

        Вход: нет.
        Выход:
            int — суммарное количество записей во всех GTIN-бакетах.

        Роль:
            Замена len(get_all()) для счётчиков и проверок
            «база не пуста». Не собирает полные КИЗы.
        """
        return sum(len(bucket) for bucket in self._data.values())

    def full_kizs(self) -> set:
        """Возвращает множество полных 31-символьных КИЗов.

        Вход: нет.
        Выход:
            set[str] — все КИЗы, восстановленные из GTIN и ID.

        Роль:
            Замена set(get_all().keys()) для сверки и фильтрации.
        """
        result = set()
        for gtin, bucket in self._data.items():
            for identifier in bucket:
                result.add(KizUtils.build_storage_kiz(gtin, identifier))
        return result

    def clear(self) -> None:
        """Очищает хранилище и сохраняет пустой файл."""
        self._data.clear()
        self.save()
        self.warning("Все записи удалены.")
