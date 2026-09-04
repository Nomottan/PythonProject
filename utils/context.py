from pathlib import Path
from datetime import date


class TaskContext:
    """
    Контекст выполнения задачи: рабочая папка, дата, логирование.
    """
    def __init__(self, target_dir: str, subfolder_template: str,
                 log_filename: str, log_callback=None):
        self.today = date.today()
        self.date_str = f"{self.today.day}_{self.today.month}_{self.today.year}"
        subfolder_name = subfolder_template.format(date=self.date_str)
        self.work_folder = Path(target_dir) / self.date_str / subfolder_name
        self.work_folder.mkdir(parents=True, exist_ok=True)
        self.log_path = self.work_folder / log_filename
        self.callback = log_callback or print

    def log(self, msg: str):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        if self.callback:
            self.callback(msg)

    def log_separator(self, char="=", length=60):
        self.log(char * length)

    def log_statistics(self, title, data_dict, sorted_keys=True):
        self.log(title)
        self.log_separator()
        if data_dict:
            keys = sorted(data_dict.keys(), key=lambda x: str(x).lower()) if sorted_keys else data_dict.keys()
            for key in keys:
                self.log(f"   {key}: {data_dict[key]}")
        else:
            self.log("   Нет данных")

    def format_filename(self, template: str, extension: str = ".xlsx") -> str:
        return template.format(date=self.date_str) + extension

    def get_work_file(self, template: str, extension: str = ".xlsx") -> Path:
        return self.work_folder / self.format_filename(template, extension)