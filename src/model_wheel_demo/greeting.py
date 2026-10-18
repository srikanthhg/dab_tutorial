"""Simple deterministic function exposed as an agent tool."""


def greeting(name: str) -> str:
    """Return a friendly greeting for a non-empty name."""
    normalized = name.strip()
    if not normalized:
        raise ValueError("name must not be empty")
    return f"Hello, {normalized}!"
