class ValidationNumb:
    @staticmethod
    def is_number(value: str) -> bool:
        if not value:
            return False
        try:
            float(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def to_int(value) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def round_up_to_multiple(value: int, multiple: int = 10) -> int:
        return ((value + multiple - 1) // multiple) * multiple