def float_display(value: float | None, width: int) -> str:
    if value is None:
        return ' ' * width
    return f'{value:.1f}'.rjust(width)


def int_or_default(string, default=None):
    if string == '' or string.isspace():
        return default
    return int(string)


def float_or_default(string, default=None):
    if string == '' or string.isspace():
        return default
    return float(string)


def _split_parts(value: str, width: int) -> list[str]:
    return [value[i : i + width].strip() for i in range(0, len(value.rstrip()), width)]


def split_ints(value: str, width: int) -> list[int]:
    return [int(part) for part in _split_parts(value, width)]


def split_optional_ints(value: str, width: int) -> list[int | None]:
    return [int(part or 0) or None for part in _split_parts(value, width)]
