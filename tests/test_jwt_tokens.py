import time
from datetime import timedelta

import pytest

from futbot_common.errors import TokenError
from futbot_common.jwt_tokens import create_token, decode_token


SECRET = "test-secret-thirty-two-bytes-min!!"


def test_create_and_decode_access_token():
    token = create_token(
        subject="user-1",
        secret=SECRET,
        token_type="access",
        expires_delta=timedelta(minutes=15),
        extra_claims={"email": "a@b.com"},
    )
    payload = decode_token(token, secret=SECRET, expected_type="access")
    assert payload["sub"] == "user-1"
    assert payload["email"] == "a@b.com"
    assert payload["type"] == "access"


def test_rejects_wrong_token_type():
    token = create_token("user-1", SECRET, "setup", timedelta(minutes=5))
    with pytest.raises(TokenError):
        decode_token(token, secret=SECRET, expected_type="access")


def test_rejects_expired_token():
    token = create_token("user-1", SECRET, "access", timedelta(seconds=-1))
    with pytest.raises(TokenError):
        decode_token(token, secret=SECRET, expected_type="access")
