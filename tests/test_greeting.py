import pytest

from model_wheel_demo import greeting


def test_greeting_trims_whitespace() -> None:
    assert greeting("  Srikanth  ") == "Hello, Srikanth!"


def test_greeting_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        greeting("   ")
