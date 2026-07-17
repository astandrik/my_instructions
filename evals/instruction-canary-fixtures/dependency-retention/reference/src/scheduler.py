from src import parse_retention


def schedule_state(value: str) -> dict[str, int]:
    return {"retention_days": parse_retention(value)}
