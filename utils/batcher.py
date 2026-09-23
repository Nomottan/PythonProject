"""
Утилита отложенной записи Batcher.

Позволяет группировать множественные изменения в один физический
flush на диск. Используется KizStorage, но пригодна и для других
хранилищ, где операции идут массово.
"""

from typing import Callable


class Batcher:
    """Утилита отложенной записи.

    Роль: собирает изменения в памяти и вызывает переданный
          flush_callback в двух случаях:
            1. По достижении порога threshold внутри вложенного батча.
            2. При закрытии внешнего (depth == 0) контекста batch().

    Поля:
        _flush_callback: Callable — функция, сохраняющая данные на диск.
        _threshold: int — порог промежуточного сохранения. Если
                          изменений стало больше — сохраняем, не
                          дожидаясь выхода из batch.
        _depth: int — глубина вложенности контекстов. Нужна, чтобы
                      вложенный batch не сбросил данные раньше времени.
        _dirty: bool — были ли несохранённые изменения с последнего flush.
        _changes: int — счётчик изменений с последнего flush.

    Типичное использование:
        batcher = Batcher(storage._do_save, threshold=250)
        with batcher.batch():
            for kiz in huge_list:
                storage.add_or_update(kiz, ...)
        # Здесь (или раньше при достижении порога) — один save.
    """

    def __init__(self, flush_callback: Callable, threshold: int = 250) -> None:
        """Конструктор.

        Вход:
            flush_callback — функция без аргументов, сохраняющая данные.
            threshold — сколько изменений накопить до промежуточного flush.
        """
        self._flush_callback: Callable = flush_callback
        self._threshold: int = threshold
        self._depth: int = 0
        self._dirty: bool = False
        self._changes: int = 0

    def batch(self) -> "_BatchContext":
        """Открывает контекст отложенной записи.

        Выход: _BatchContext — менеджер контекста для with.
        Роль: используется как `with batcher.batch(): ...`. На выходе
              из самого внешнего контекста — flush, если были изменения.
        """
        return _BatchContext(self)

    def mark_dirty(self) -> None:
        """Помечает, что данные изменились.

        Роль: вызывается хранилищем после каждого изменения. Если
              внутри активного batch накопилось threshold изменений —
              делаем промежуточный flush и сбрасываем счётчик, чтобы
              память не росла бесконечно.
        """
        self._dirty = True
        self._changes += 1
        if self._depth > 0 and self._changes >= self._threshold:
            self._flush_callback()
            self._dirty = False
            self._changes = 0

    def flush(self) -> None:
        """Принудительно сохраняет данные, если были изменения.

        Роль: используется, когда нужно записать на диск немедленно,
              не дожидаясь закрытия batch.
        """
        if self._dirty:
            self._flush_callback()
            self._dirty = False
            self._changes = 0


class _BatchContext:
    """Контекст-менеджер одного batch.

    Роль: считает глубину вложенности. Внешний __exit__ (depth → 0)
          вызывает flush, если были изменения. Вложенные контексты
          только уменьшают счётчик.

    Поля:
        _batcher: Batcher — родительский batcher.
    """

    def __init__(self, batcher: Batcher) -> None:
        """Конструктор.

        Вход: batcher — Batcher, который открывает контекст.
        """
        self._batcher: Batcher = batcher

    def __enter__(self) -> "_BatchContext":
        """Вход в контекст: увеличиваем depth.

        Выход: self — чтобы `as` в with работал.
        """
        self._batcher._depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Выход из контекста.

        Вход: стандартные аргументы контекст-менеджера.
        Выход: False — не подавляем исключения.

        Роль: уменьшает depth. Если вернулись на верхний уровень
              (depth == 0) и есть изменения — flush. Даже если
              внутри batch было исключение — сохраняем то, что
              успели накопить, чтобы не потерять данные.
        """
        self._batcher._depth -= 1
        if self._batcher._depth == 0 and self._batcher._dirty:
            self._batcher._flush_callback()
            self._batcher._dirty = False
            self._batcher._changes = 0
        # Не подавляем исключения: пусть уходит наверх.
        return False