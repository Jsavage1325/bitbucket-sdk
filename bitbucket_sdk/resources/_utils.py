def _require(name: str, value: str) -> None:
    if not value or not str(value).strip():
        raise ValueError(f"'{name}' must not be empty")
