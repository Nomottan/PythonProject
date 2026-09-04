from datetime import datetime


class DateTimeUtils:
    @staticmethod
    def get_current_datetime_text() -> str:
        now = datetime.now()

        month_names = [
            "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        month_str = month_names[now.month]

        day_abbr = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
        day_str = f"{now.day} {day_abbr[now.weekday()]}"

        time_str = now.strftime("%H:%M")

        return f"{month_str}\n{day_str}\n{time_str}"