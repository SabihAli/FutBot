import pytest
from httpx import ASGITransport, AsyncClient

from services.auth.app import create_app


@pytest.mark.asyncio
async def test_register_requires_first_name(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "securepass123"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_returns_pending_2fa(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "securepass123",
            "first_name": "Ada",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["status"] == "pending_2fa"
    assert body["data"]["first_name"] == "Ada"
    assert "setup_token" in body["data"]
