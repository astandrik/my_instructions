from src import parse_retention


def serialize_config(value: str) -> dict[str, int]:
    return {"retention": parse_retention(value)}
