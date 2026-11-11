from helpers import format_result


def calculate(value: int, multiplier: int = 2) -> str:
    result = value * multiplier
    return format_result(result)


def main() -> str:
    return calculate(21)
