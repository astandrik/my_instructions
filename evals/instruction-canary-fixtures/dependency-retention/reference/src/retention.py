import re


def parse_retention(value: str) -> int:
    match = re.fullmatch(r"(\d+)d", value.strip())
    if not match:
        raise ValueError("retention must use Nd format")
    return int(match.group(1))
