from pathlib import Path
from datetime import datetime
from typing import Optional
from utils.kiz_storage import KizStorage

class KizValidator:
    """
    Валидатор КИЗов. Использует KizStorage для доступа к данным.
    Реализует бизнес-логику для Отчётов МП, ЧЗ МП и Возвратов.
    """

    def __init__(self, storage: KizStorage) -> None:
        self.storage = storage

    # ---------- Управление хранилищем ----------

    def load(self) -> None:
        """Загружает данные из used_kiz.json."""
        self.storage.load()

    def batch(self):
        """Прокси к KizStorage.batch().

        Возвращает контекстный менеджер, чтобы сервисы могли писать
        with self.kiz_validator.batch(): и не зависеть от внутреннего
        устройства KizStorage.

        Вход: нет.
        Выход: _BatchContext.
        Роль: единая точка группировки сохранений для всех сервисов.
        """
        return self.storage.batch()

    def set_log_path(self, work_dir: Path) -> None:
        """Устанавливает путь к логу kiz_validation.log в рабочей папке."""
        self.storage.set_log_path(work_dir)

    def clean_old_entries(self, months: int = 1) -> int:
        """Очищает старые записи и логирует результат."""
        deleted = self.storage.clean_old_entries(months)
        self.storage._log(f"Очистка старых записей: удалено {deleted} записей.")
        return deleted

    # ---------- Валидация для продаж (Отчёты МП и ЧЗ МП) ----------

    def validate_for_sale(self, kiz: str, sale_date_str: Optional[str] = None) -> bool:
        """
        Проверяет КИЗ для списания (продажа).
        - Если sale_date_str не указана (ЧЗ МП) → используется сегодняшняя дата.
        - Если указана (Отчёт МП) → парсится из строки вида "HH:MM:SS DD.MM.YYYY".
        Возвращает True, если КИЗ можно добавить в список списания.
        Логирует все значимые события в kiz_validation.log.
        """
        # Определяем дату продажи
        if sale_date_str is None:
            sale_date = datetime.now().strftime("%d-%m-%Y")
            self.storage._log(f"ЧЗ МП: дата продажи для КИЗа {kiz} установлена как сегодня ({sale_date})")
        else:
            try:
                # Парсим "HH:MM:SS DD.MM.YYYY"
                dt = datetime.strptime(sale_date_str, "%H:%M:%S %d.%m.%Y")
                sale_date = dt.strftime("%d-%m-%Y")
            except ValueError:
                # Если формат не совпадает, пробуем просто "DD.MM.YYYY"
                try:
                    dt = datetime.strptime(sale_date_str, "%d.%m.%Y")
                    sale_date = dt.strftime("%d-%m-%Y")
                except ValueError:
                    self.storage._log(f"ОШИБКА: не удалось распарсить дату '{sale_date_str}' для КИЗа {kiz}. Использую сегодняшнюю.")
                    sale_date = datetime.now().strftime("%d-%m-%Y")

        # Проверяем, есть ли КИЗ в хранилище
        existing = self.storage.get(kiz)

        if existing is None:
            # Новый КИЗ – добавляем
            self.storage.add_or_update(kiz, sale_date, None)
            self.storage._log(f"Добавлен новый КИЗ {kiz} с датой продажи {sale_date}")
            return True

        # КИЗ уже есть
        existing_sold = existing.get("sold_date")
        existing_returned = existing.get("returned_date")

        # Если дата продажи совпадает – дубликат
        if existing_sold == sale_date:
            self.storage._log(f"Дубликат: КИЗ {kiz} уже продан {existing_sold}, повторная попытка продажи в тот же день пропущена")
            return False

        # Если дата продажи отличается
        if existing_returned:
            # Был возврат
            # Проверяем, был ли возврат после предыдущей продажи
            # Если дата возврата > даты предыдущей продажи, то это повторная продажа
            try:
                sold_dt = datetime.strptime(existing_sold, "%d-%m-%Y")
                returned_dt = datetime.strptime(existing_returned, "%d-%m-%Y")
                new_sale_dt = datetime.strptime(sale_date, "%d-%m-%Y")

                if returned_dt > sold_dt:
                    # Возврат был после продажи – это нормальная повторная продажа
                    self.storage._log(
                        f"Повторная продажа {kiz}: ранее был продан {existing_sold}, возвращён {existing_returned}, теперь продаётся {sale_date}"
                    )
                    # Обновляем запись: новая дата продажи, возврат удаляем
                    self.storage.add_or_update(kiz, sale_date, None)
                    return True
                else:
                    # Возврат был до продажи (аномалия) – логируем, но всё равно обновляем дату продажи
                    self.storage._log(
                        f"Аномалия: КИЗ {kiz} имеет возврат {existing_returned} до продажи {existing_sold}. Обновляю дату продажи на {sale_date}, возврат удалён"
                    )
                    self.storage.add_or_update(kiz, sale_date, None)
                    return True
            except Exception as e:
                self.storage._log(f"Ошибка сравнения дат для КИЗа {kiz}: {e}. Обновляю дату продажи.")
                self.storage.add_or_update(kiz, sale_date, None)
                return True
        else:
            # Нет возврата – просто обновляем дату продажи
            self.storage._log(
                f"Обновление даты продажи для КИЗа {kiz}: было {existing_sold}, стало {sale_date}"
            )
            self.storage.add_or_update(kiz, sale_date, None)
            return True

    # ---------- Валидация для возвратов ----------

    def validate_for_return(self, kiz: str) -> bool:
        """
        Проверяет КИЗ для возврата.
        Если КИЗ есть в хранилище, обновляет дату возврата на сегодня и возвращает True.
        Если КИЗа нет – логирует и возвращает False.
        """
        existing = self.storage.get(kiz)
        if existing is None:
            self.storage._log(f"Возврат: КИЗ {kiz} отсутствует в хранилище – пропущен")
            return False

        # КИЗ есть – обновляем дату возврата
        return_date = datetime.now().strftime("%d-%m-%Y")
        self.storage.add_or_update(kiz, existing["sold_date"], return_date)
        self.storage._log(f"Возврат: для КИЗа {kiz} установлена дата возврата {return_date}")
        return True