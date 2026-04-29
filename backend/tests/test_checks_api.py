from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

import app.api.checks as checks_module
from app.core.app_config import AppConfig, Icinga2SourceConfig, SectionConfig
from app.core.auth import current_user_or_token
from app.core.config import settings
from app.main import app

ICINGA_SOURCE = Icinga2SourceConfig(
    name="icinga-prod",
    type="icinga2",
    url="https://icinga.example.com:5665",
    username="root",
    password="secret",
    verify_ssl=False,
)

CONFIG = AppConfig(
    pull_interval=10,
    sources=[ICINGA_SOURCE],
    sections=[SectionConfig(name="All", catchall=True)],
)

DASHBOARD_RESPONSE = {
    "sections": [{"name": "All", "description": None, "checks": []}],
    "sources": [{"name": "icinga-prod", "type": "icinga2", "available": True, "last_updated": None}],
}


async def _login(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={"email": "u@example.com", "password": "password123"})
    await client.post("/api/auth/jwt/login", data={"username": "u@example.com", "password": "password123"})


@pytest.mark.asyncio
async def test_list_checks_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/checks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_checks_with_cookie_auth(client: AsyncClient) -> None:
    await _login(client)
    with patch.object(checks_module, "get_app_config", return_value=CONFIG):
        with patch("app.api.checks.get_dashboard_data", new_callable=AsyncMock, return_value=DASHBOARD_RESPONSE):
            response = await client.get("/api/checks")
    assert response.status_code == 200
    assert "sections" in response.json()
    assert "sources" in response.json()


@pytest.mark.asyncio
async def test_list_checks_with_bearer_token(client: AsyncClient) -> None:
    token = "test-api-token-abc123"
    original = settings.api_token
    settings.api_token = token
    try:
        with patch.object(checks_module, "get_app_config", return_value=CONFIG):
            with patch("app.api.checks.get_dashboard_data", new_callable=AsyncMock, return_value=DASHBOARD_RESPONSE):
                response = await client.get(
                    "/api/checks",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert response.status_code == 200
    finally:
        settings.api_token = original


@pytest.mark.asyncio
async def test_list_checks_with_wrong_bearer_token(client: AsyncClient) -> None:
    original = settings.api_token
    settings.api_token = "correct-token"
    try:
        response = await client.get(
            "/api/checks",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401
    finally:
        settings.api_token = original


@pytest.mark.asyncio
async def test_list_checks_bearer_rejected_when_no_token_configured(client: AsyncClient) -> None:
    original = settings.api_token
    settings.api_token = None
    try:
        response = await client.get(
            "/api/checks",
            headers={"Authorization": "Bearer anything"},
        )
        assert response.status_code == 401
    finally:
        settings.api_token = original
