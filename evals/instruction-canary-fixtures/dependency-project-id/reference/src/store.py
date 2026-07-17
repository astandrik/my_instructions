from src import canonical_project_id


def put_project(store: dict[str, object], value: str, payload: object) -> None:
    store[canonical_project_id(value)] = payload
