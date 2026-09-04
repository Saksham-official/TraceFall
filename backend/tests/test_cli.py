from app.cli import COMMON_PASSWORDS
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_every_common_password_is_long_enough_to_be_reachable() -> None:
    """A shorter entry is dead code: the length rule would reject it first."""
    assert all(len(p) >= MIN_PASSWORD_LENGTH for p in COMMON_PASSWORDS)


def test_password_hashing_round_trip() -> None:
    digest = hash_password("correct-horse-battery")
    assert digest.startswith("$argon2")
    assert "correct-horse-battery" not in digest
    assert verify_password("correct-horse-battery", digest)
    assert not verify_password("wrong-password-entirely", digest)
    assert not needs_rehash(digest)


def test_verify_does_not_raise_on_a_malformed_hash() -> None:
    assert not verify_password("anything", "not-a-valid-argon2-hash")


def test_hashes_are_salted() -> None:
    assert hash_password("same-password-twice") != hash_password("same-password-twice")
