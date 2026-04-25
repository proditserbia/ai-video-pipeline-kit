from __future__ import annotations

import pytest

from app.core.security import hash_password, validate_password_length, verify_password


def test_hash_password_normal():
    """A password within the 72-byte limit is hashed successfully."""
    pw = "StrongPass1!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed)


def test_hash_password_exactly_72_bytes():
    """A password that is exactly 72 bytes is accepted."""
    pw = "a" * 72
    hashed = hash_password(pw)
    assert verify_password(pw, hashed)


def test_hash_password_too_long_raises():
    """A password longer than 72 bytes raises a clear ValueError."""
    pw = "a" * 73
    with pytest.raises(ValueError, match="72"):
        hash_password(pw)


def test_hash_password_multibyte_too_long_raises():
    """Multi-byte characters can push byte length over 72 even with fewer chars."""
    # Each "é" is 2 bytes in UTF-8, so 37 of them = 74 bytes
    pw = "é" * 37
    assert len(pw.encode("utf-8")) > 72
    with pytest.raises(ValueError, match="72"):
        hash_password(pw)


def test_validate_password_length_ok():
    validate_password_length("short")


def test_validate_password_length_fails():
    with pytest.raises(ValueError):
        validate_password_length("x" * 73)
