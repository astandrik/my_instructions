class Cache:
    def __init__(self) -> None:
        self._values: dict[str, object] = {}

    def get(self, key: str | None) -> object | None:
        if key is None:
            return None
        return self._values.get(key)
