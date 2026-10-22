from datetime import timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.time import utcnow


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("Secret123")
    assert hashed != "Secret123"
    assert hashed.startswith("$argon2id$")
    assert verify_password("Secret123", hashed)
    assert not verify_password("Secret124", hashed)


def test_verify_password_without_hash_is_false() -> None:
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_access_token_roundtrip(settings: Settings) -> None:
    token = create_access_token(7, settings)
    assert decode_access_token(token, settings) == 7


def test_expired_access_token_is_rejected(settings: Settings) -> None:
    payload = {"sub": "1", "type": "access", "exp": utcnow() - timedelta(seconds=1)}
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, settings)


def test_token_of_wrong_type_is_rejected(settings: Settings) -> None:
    payload = {"sub": "1", "type": "refresh", "exp": utcnow() + timedelta(minutes=5)}
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token, settings)


def test_token_signed_with_other_key_is_rejected(settings: Settings) -> None:
    payload = {"sub": "1", "type": "access", "exp": utcnow() + timedelta(minutes=5)}
    token = jwt.encode(payload, "another-secret-another-secret-123", algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, settings)


def test_refresh_tokens_are_random_and_hash_is_stable() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()
    assert a != b
    assert hash_token(a) == hash_token(a)
    assert len(hash_token(a)) == 64


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        Settings(_env_file=None, jwt_secret="short")  # type: ignore[call-arg]
