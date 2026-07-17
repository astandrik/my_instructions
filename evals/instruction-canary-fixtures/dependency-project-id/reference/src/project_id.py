import re


def canonical_project_id(value: str) -> str:
    return re.sub(r"\s+", "-", value.strip().lower())
