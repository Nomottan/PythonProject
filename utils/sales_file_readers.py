"""
Ридеры файлов продаж (результат SalesFileGenerator).

Класс SalesFileKizReader читает файлы продаж формата
"{от_кого} - {кому} : {ИНН}.xlsx" — структура
[Наименование, КИЗ, GTIN, Цена] — и собирает множество КИЗов.

Роль в программе:
    Используется SalesAccumulatorService при аккумуляции продаж.
    Не путать с utils/report_readers.py — там ридеры отчётов МП
    и ЧЗ МП, а здесь — ридеры файлов продаж.
"""

from pathlib import Path

import openpyxl


class SalesFileKizReader:
    """Читает КИЗы из файла продаж.

    Роль:
        Единая точка чтения КИЗов из второго столбца файла продаж.
        Возвращает set[str]. Ошибки чтения не пробрасываются —
        возвращается пустое множество (аккумуляция продолжается).
    """

    # Индекс столбца с КИЗом (0-based): [Наименование, КИЗ, GTIN, Цена].
    KIZ_COLUMN_INDEX = 1

    @staticmethod
    def read(file_path) -> set:
        """Возвращает множество непустых КИЗов из файла.

        Вход:
            file_path — путь к файлу продаж (Path или str).

        Выход:
            set[str] — непустые КИЗы из второго столбца, без
            дубликатов. Пустое множество при ошибке чтения.

        Роль:
            Точный перенос SalesAccumulatorService._collect_kiz_set.
            Строки, короче KIZ_COLUMN_INDEX+1 или с пустым КИЗом,
            пропускаются.
        """
        try:
            wb = openpyxl.load_workbook(
                Path(file_path), read_only=True, data_only=True,
            )
        except Exception:
            return set()

        try:
            sheet = wb.active
            kiz_set = set()
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) > SalesFileKizReader.KIZ_COLUMN_INDEX:
                    raw = row[SalesFileKizReader.KIZ_COLUMN_INDEX]
                    if raw:
                        kiz = str(raw).strip()
                        if kiz:
                            kiz_set.add(kiz)
            return kiz_set
        finally:
            wb.close()