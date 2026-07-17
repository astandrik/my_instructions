from src import canonical_project_id


def format_project_arg(value: str) -> str:
    return canonical_project_id(value)
