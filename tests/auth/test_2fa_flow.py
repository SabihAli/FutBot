import pytest
import pyotp
from httpx import AsyncClient
from urllib.parse import parse_qs, urlparse

from services.auth.app import create_app


def _secret_from_uri(secret_uri: str) -> str:
    return parse_qs(urlparse(secret_uri).query)["secret"][0]


async def _register(client: AsyncClient) -> str:
    response = await client.post(
        "/auth/register",
        json={
            "email": "ada@example.com",
            "password": "securepass123",
            "first_name": "Ada",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["setup_token"]


@pytest.mark.asyncio
async def test_2fa_setup_and_verify_issues_tokens(auth_client):
    setup_token = await _register(auth_client)
    enable = await auth_client.post(
        "/auth/2fa/enable",
        headers={"Authorization": f"Bearer {setup_token}"},
    )
    assert enable.status_code == 200
    secret_uri = enable.json()["data"]["secret_uri"]
    secret = _secret_from_uri(enable.json()["data"]["secret_uri"])
    code = pyotp.TOTP(secret).now()
    verify = await auth_client.post(
        "/auth/2fa/verify",
        headers={"Authorization": f"Bearer {setup_token}"},
        json={"code": code},
    )
    assert verify.status_code == 200
    tokens = verify.json()["data"]
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_login_requires_2fa_step_up(auth_client):
    setup_token = await _register(auth_client)
    enable = await auth_client.post(
        "/auth/2fa/enable",
        headers={"Authorization": f"Bearer {setup_token}"},
    )
    secret = _secret_from_uri(enable.json()["data"]["secret_uri"])
    code = pyotp.TOTP(secret).now()
    await auth_client.post(
        "/auth/2fa/verify",
        headers={"Authorization": f"Bearer {setup_token}"},
        json={"code": code},
    )

    login = await auth_client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "securepass123"},
    )
    assert login.status_code == 200
    assert login.json()["data"]["requires_2fa"] is True
    assert "step_up_token" in login.json()["data"]
