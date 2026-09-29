import shutil
from pathlib import Path

class FileHelper:
    @staticmethod
    def copy_file_with_log(src, dst, ctx, description="файл", overwrite=False):
        src_path = Path(src)
        dst_path = Path(dst)
        if not overwrite and dst_path.exists():
            ctx.log(f"Файл уже существует: {dst_path.name}")
            return False
        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            ctx.log(f"Скопирован {description}: {dst_path.name}")
            return True
        except Exception as e:
            ctx.log(f"Ошибка копирования {description}: {e}")
            return False

    @staticmethod
    def find_files_by_pattern(folder, pattern):
        folder_path = Path(folder)
        return list(folder_path.glob(pattern))

    @staticmethod
    def find_sales_files(folder) -> list:
        """Возвращает файлы продаж в папке по формату имён.

        Вход:
            folder — папка (Path или str) для поиска.

        Выход:
            list[Path] — файлы *.xlsx, в имени которых есть
            " - " и " _ " (отличительный признак нового формата
            файлов продаж: "{от_кого} - {кому} : {ИНН}.xlsx").
            Пустой список, если папки нет.

        Роль:
            Единая точка поиска файлов продаж. Раньше логика жила
            в SalesAccumulatorService._find_sales_files — вынесена
            сюда, чтобы сервис стал тонким оркестратором.
        """
        folder_path = Path(folder)
        if not folder_path.exists():
            return []
        return [
            f for f in folder_path.glob("*.xlsx")
            if " - " in f.stem and " _ " in f.stem
        ]

    @staticmethod
    def ensure_file_exists(ctx, file_path, description="файл"):
        path = Path(file_path)
        if not path.is_file():
            ctx.log(f"Нет {description}: {path.name}")
            return None
        return path
