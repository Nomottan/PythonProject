import json, os, tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict

from utils.path_manager import PathManager

class _BatchContext:
    """Контекстный менеджер для батчинга сохранений KizStorage.

    Назначение:
        Позволяет обернуть группу операций изменения хранилища в блок `with`.
        Внутри блока add_or_update НЕ сохраняет на диск при каждом изменении —
        только помечает батч «грязным» и считает изменения. Один финальный save()
        выполняется на выходе из самого внешнего батча. Плюс промежуточные
        сохранения каждые BATCH_SAVE_THRESHOLD изменений.

    Атрибуты:
        _storage: KizStorage — родительское хранилище, чьи счётчики батча
                  мы инкрементируем и декрементируем.

    Роль в программе:
        Помощник, возвращаемый KizStorage.batch(). Напрямую не используется.
    """

    def __init__(self, storage):
        # Сохраняем ссылку на хранилище — через неё доступны счётчики и _data
        self._storage = storage

    def __enter__(self):
        # Увеличиваем глубину вложенности: add_or_update увидит, что мы в батче,
        # и не будет сохранять при каждом изменении
        self._storage._batch_depth += 1
        # Возвращаем само хранилище — на случай, если понадобится as-биндинг
        return self._storage

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Уменьшаем глубину: выходим с одного уровня вложенности
        self._storage._batch_depth -= 1

        # Сохраняем ТОЛЬКО при выходе с самого внешнего уровня.
        # Вложенные батчи сохранять не должны — иначе смысл батчинга теряется.
        if self._storage._batch_depth == 0:
            # Пустой батч (только чтения) не должен вызывать I/O
            if self._storage._batch_dirty:
                # save() может бросить исключение — оно полетит наружу.
                # Это желаемое поведение: ошибку сохранения нельзя скрывать.
                self._storage.save()
            # Сбрасываем флаги, чтобы следующий батч начал с чистого состояния
            self._storage._batch_dirty = False
            self._storage._batch_changes_count = 0
        return False

class KizStorage:
    """Хранилище КИЗов в JSON-файле.

    Формат: {КИЗ: {"sold_date": "DD-MM-YYYY", "returned_date": "DD-MM-YYYY"}}.

    Не потокобезопасен. При использовании из нескольких потоков одновременно
    возможны гонки при изменении _data и счётчиков батча. Вне текущего скоупа.
    """

    # Порог промежуточного сохранения внутри батча. Перестраховка: чтобы
    # при долгом прогоне (2–3 тыс. КИЗов) не копить всё в памяти до конца.
    BATCH_SAVE_THRESHOLD = 250

    def __init__(self, file_path, log_callback=None):
        self._file_path = Path(file_path)
        self._log_callback = log_callback or (lambda msg: None)
        self._data = {}
        self._log_path = None
        # NEW: флаг автосохранения вне батча. True — поведение как раньше:
        # add_or_update сразу пишет на диск. Нужен для легаси-кода,
        # который вызывает add_or_update без батча.
        self._autosave_enabled = True

        # NEW: счётчик глубины вложенных batch(). Сохраняем только при выходе с 0.
        self._batch_depth = 0

        # NEW: взведён, если внутри батча были реальные изменения.
        # Определяет, нужен ли финальный save() на выходе.
        self._batch_dirty = False

        # NEW: счётчик всех вызовов add_or_update внутри батча (включая
        # повторные обновления одного КИЗа). По достижении порога — промежуточный save.
        self._batch_changes_count = 0

    def set_log_path(self, work_dir: Path) -> None:
        self._log_path = work_dir / "kiz_validation.log"

    def _log(self, message: str) -> None:
        """Пишет сообщение в файл лога и, если задан, вызывает колбэк.

        Раньше метод был перекрыт lambda-атрибутом self._log — файл
        kiz_validation.log не писался никогда. Теперь атрибут называется
        self._log_callback, метод класса достижим.

        Вход: message — текст для записи.
        Выход: нет.
        """
        # 1. Пишем в файл, только если set_log_path уже вызван
        if self._log_path is not None:
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] {message}\n")
            except Exception:
                # Ошибка логирования не должна ронять основную логику
                pass

        # 2. Дополнительно зовём колбэк, если он был передан в конструктор.
        #    Оборачиваем в try, чтобы падение UI-колбэка не рушило хранилище.
        try:
            self._log_callback(message)
        except Exception:
            pass

    # ---------- Основные методы ----------

    def load(self):
        """Загружает _data из файла. Семантика не менялась.

        Важно: load() может вызвать save() (при отсутствии файла или миграции
        старого формата). Если load() вызван внутри батча, это приведёт
        к неожиданному промежуточному сохранению — поэтому пишем предупреждение.
        """
        # NEW: предупреждаем, если load() попал внутрь батча
        if self._batch_depth > 0:
            self._log(
                "ПРЕДУПРЕЖДЕНИЕ: load() вызван внутри батча. "
                "Это может привести к неожиданному промежуточному сохранению."
            )
        if not self._file_path.exists():
            self._log("Файл used_kiz.json не найден, будет создан новый.")
            self._data = {}
            self.save()
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # --- МИГРАЦИЯ: обрезаем ключи до 31 символа ---
            from utils.kiz_utils import KizUtils
            migrated = False
            new_data = {}
            for kiz, record in raw_data.items():
                storage_list = KizUtils.clean_kiz_for_storage(kiz)
                if storage_list:
                    clean_kiz = storage_list[0]  # обычно один
                    if clean_kiz != kiz:
                        migrated = True
                        self._log(f"Миграция: {kiz[:30]}... → {clean_kiz}")
                    # Если ключ уже существует, перезаписываем (можно объединять даты, но упростим)
                    new_data[clean_kiz] = record
                else:
                    # Некорректный КИЗ – удаляем
                    self._log(f"Миграция: удалена некорректная запись {kiz[:30]}...")
                    migrated = True

            self._data = new_data
            if migrated:
                self.save()
                self._log("Миграция завершена: все ключи обрезаны до 31 символа, некорректные удалены.")
            # -------------------------------------

            self._log(f"Загружено {len(self._data)} записей из used_kiz.json")
        except Exception as e:
            self._log(f"Ошибка чтения: {e}. Создан новый словарь.")
            self._data = {}
            self.save()

    def save(self):
        """Атомарная запись _data в файл.

        Использует временный файл в той же директории и os.replace. Это
        гарантирует, что used_kiz.json никогда не окажется в промежуточном
        состоянии: либо старый файл целиком, либо новый целиком.

        Исключения ПРОБРАСЫВАЮТСЯ наверх (не подавляются): если сохранение
        не удалось, вызывающий код должен об этом знать.
        """
        # tmp_path храним снаружи, чтобы удалить его в finally, если os.replace не сработал
        tmp_path = None
        try:
            # На случай, если директории ещё нет (первый запуск)
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

            # NamedTemporaryFile в ТОЙ ЖЕ директории: os.replace атомарен только
            # в пределах одной файловой системы. delete=False — иначе файл
            # удалится сам при закрытии, и мы не сможем его переименовать.
            with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._file_path.parent,
                    delete=False,
                    suffix=".tmp",
            ) as f:
                tmp_path = Path(f.name)
                # indent=None — компактный файл, пишется быстрее.
                # ensure_ascii=False — кириллица в КИЗах сохраняется читаемо.
                # sort_keys=True — стабильный порядок ключей (удобно для diff).
                json.dump(self._data, f, indent=None, ensure_ascii=False, sort_keys=True)

            # Атомарная замена: старый used_kiz.json либо целый, либо новый целый
            os.replace(tmp_path, self._file_path)
            # После успешной замены tmp_path больше не существует — сбрасываем,
            # чтобы finally не пытался его удалить
            tmp_path = None
        except Exception as e:
            # Логируем и пробрасываем: скрывать проблему нельзя
            self._log(f"Ошибка сохранения {self._file_path}: {e}")
            raise
        finally:
            # Подчищаем tmp-файл, если os.replace не сработал
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    # Если удалить не удалось — не маскируем основное исключение
                    pass

    def get(self, kiz: str) -> Optional[Dict[str, Optional[str]]]:
        return self._data.get(kiz)

    def add_or_update(self, kiz, sold_date, returned_date=None):
        """Добавляет или обновляет запись КИЗа в _data.

        Вход:
            kiz — строка КИЗа.
            sold_date — дата продажи (строка "DD-MM-YYYY" или None).
            returned_date — дата возврата (строка "DD-MM-YYYY" или None).

        Выход: нет.

        Роль: единственная точка изменения _data. Внутри батча откладывает
        запись на диск; вне батча — сохраняет сразу (обратная совместимость).

        Семантика записи — ПОЛНАЯ ПЕРЕЗАПИСЬ. Оба поля всегда устанавливаются
        явно из аргументов, включая None. Это нужно для сценария повторной
        продажи: validate_for_sale передаёт returned_date=None и тем самым
        стирает прежний возврат. Если бы поля не затирались при None,
        этот сценарий сломался бы.
        """
        # REPLACE: полная перезапись записи — восстановленная оригинальная логика.
        # Оба поля берутся из аргументов «как есть», без проверки на None.
        self._data[kiz] = {
            "sold_date": sold_date,
            "returned_date": returned_date,
        }

        # NEW: логика батча
        if self._batch_depth > 0:
            # Мы внутри батча — откладываем сохранение
            self._batch_dirty = True
            self._batch_changes_count += 1

            if self._batch_changes_count >= self.BATCH_SAVE_THRESHOLD:
                # Промежуточное сохранение: чтобы не копить слишком много
                # изменений в памяти при долгом прогоне
                self.save()
                # Сбрасываем счётчики после промежуточного сохранения
                self._batch_dirty = False
                self._batch_changes_count = 0
                self._log(
                    f"Батч: промежуточное сохранение после {self.BATCH_SAVE_THRESHOLD} "
                    f"изменений (всего в _data: {len(self._data)} записей)."
                )
        elif self._autosave_enabled:
            # Обратная совместимость: вне батча сохраняем сразу
            self.save()

    def batch(self):
        """Возвращает контекстный менеджер для группировки сохранений.

        Использование:
            with storage.batch():
                storage.add_or_update(...)   # не сохраняется сразу
                storage.add_or_update(...)   # не сохраняется сразу
            # здесь, на выходе, происходит один save()

        Вход: нет.
        Выход: _BatchContext.
        Роль: точка входа для сервисов, которым нужно писать много КИЗов.
        """
        return _BatchContext(self)

    # ---------- Очистка старых записей ----------

    def clean_old_entries(self, months: int = 1) -> int:
        if not self._data:
            self._log("Очистка: нет записей для удаления.")
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
                    to_delete.append((kiz, sold_date_str))
            except ValueError:
                self._log(f"Очистка: некорректная дата продажи '{sold_date_str}' для КИЗа {kiz}, запись пропущена")
                continue

        if not to_delete:
            self._log(f"Очистка: нет записей старше {months} месяца(ев).")
            return 0

        for kiz, sold_date_str in to_delete:
            del self._data[kiz]
            self._log(f"Очистка: удалён КИЗ {kiz} с датой продажи {sold_date_str}")

        self.save()
        self._log(f"Очистка завершена: удалено {len(to_delete)} записей.")
        return len(to_delete)

    # ---------- Дополнительные ----------

    def get_all(self) -> Dict[str, Dict[str, Optional[str]]]:
        return self._data.copy()

    def clear(self) -> None:
        self._data.clear()
        self.save()
        self._log("Все записи удалены.")