from pathlib import Path
from utils.logger import ILogger


class FileHelper:
    @staticmethod
    def copy_file_with_log(src, dst, logger: ILogger, description="файл", overwrite=False):
        src_path = Path(src)
        dst_path = Path(dst)

        if not overwrite and dst_path.exists():
            logger.info(f"Файл уже существует: {dst_path.name}")
            return False

        try:
            import shutil
            shutil.copy2(src_path, dst_path)
            logger.info(f"Скопирован {description}: {dst_path.name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка копирования {description}: {e}")
            return False

    @staticmethod
    def ensure_file_exists(file_path, logger: ILogger, description="файл"):
        path = Path(file_path)
        if not path.is_file():
            logger.error(f"Нет {description}: {path.name}")
            return None
        return path

    @staticmethod
    def find_files_by_pattern(folder, pattern):
        folder_path = Path(folder)
        return list(folder_path.glob(pattern))