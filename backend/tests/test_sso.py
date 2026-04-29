from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, Response


@pytest.mark.asyncio
async def test_sso_config_disabled(client: AsyncClient) -> None:
    response = await client.get("/api/auth/sso/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["button_label"] is None


@pytest.mark.asyncio
async def test_sso_config_enabled(client: AsyncClient) -> None:
    with patch("app.core.config.settings.keycloak_base_url", "https://keycloak.example.com/auth"), \
         patch("app.core.config.settings.keycloak_realm", "myrealm"), \
         patch("app.core.config.settings.keycloak_client_id", "statdash"), \
         patch("app.core.config.settings.keycloak_client_secret", "secret"), \
         patch("app.core.config.settings.sso_button_label", "Login via Company SSO"):
        response = await client.get("/api/auth/sso/config")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["button_label"] == "Login via Company SSO"


@pytest.mark.asyncio
async def test_sso_login_not_configured(client: AsyncClient) -> None:
    response = await client.get("/api/auth/sso/login", follow_redirects=False)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sso_login_redirects_to_keycloak(client: AsyncClient) -> None:
    with patch("app.api.sso.settings") as mock_settings:
        mock_settings.sso_configured = True
        mock_settings.keycloak_base_url = "https://keycloak.example.com/auth"
        mock_settings.keycloak_realm = "myrealm"
        mock_settings.keycloak_client_id = "statdash"
        mock_settings.sso_callback_url = None

        response = await client.get("/api/auth/sso/login", follow_redirects=False)

    assert response.status_code == 302
    location = response.headers["location"]
    assert "keycloak.example.com" in location
    assert "response_type=code" in location
    assert "scope=openid+email" in location
    assert _STATE_COOKIE_SET(response)


def _STATE_COOKIE_SET(response) -> bool:
    return any("statdash_sso_state" in c for c in response.headers.get_list("set-cookie"))


@pytest.mark.asyncio
async def test_sso_callback_invalid_state(client: AsyncClient) -> None:
    with patch("app.api.sso.settings") as mock_settings:
        mock_settings.sso_configured = True

        response = await client.get(
            "/api/auth/sso/callback",
            params={"code": "somecode", "state": "wrongstate"},
            follow_redirects=False,
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_sso_callback_keycloak_error_redirects(client: AsyncClient) -> None:
    with patch("app.api.sso.settings") as mock_settings:
        mock_settings.sso_configured = True
        mock_settings.sso_frontend_url = "/"

        response = await client.get(
            "/api/auth/sso/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "sso_error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_sso_callback_provisions_new_user(client: AsyncClient) -> None:
    state = "abcdef1234567890"

    token_json = {"access_token": "fake-access-token"}
    userinfo_json = {"email": "newuser@example.com"}

    mock_token_resp = MagicMock(spec=Response)
    mock_token_resp.raise_for_status = MagicMock()
    mock_token_resp.json.return_value = token_json

    mock_userinfo_resp = MagicMock(spec=Response)
    mock_userinfo_resp.raise_for_status = MagicMock()
    mock_userinfo_resp.json.return_value = userinfo_json

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.post = AsyncMock(return_value=mock_token_resp)
    mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

    with patch("app.api.sso.settings") as mock_settings, \
         patch("app.api.sso.httpx.AsyncClient", return_value=mock_http):
        mock_settings.sso_configured = True
        mock_settings.keycloak_base_url = "https://keycloak.example.com/auth"
        mock_settings.keycloak_realm = "myrealm"
        mock_settings.keycloak_client_id = "statdash"
        mock_settings.keycloak_client_secret = "secret"
        mock_settings.sso_callback_url = "http://test/api/auth/sso/callback"
        mock_settings.sso_frontend_url = "/"

        client.cookies.set("statdash_sso_state", state)
        response = await client.get(
            "/api/auth/sso/callback",
            params={"code": "authcode", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "statdash_auth" in response.cookies


@pytest.mark.asyncio
async def test_sso_callback_existing_user_logs_in(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={"email": "existing@example.com", "password": "pass123"})

    state = "abcdef1234567890"

    mock_token_resp = MagicMock(spec=Response)
    mock_token_resp.raise_for_status = MagicMock()
    mock_token_resp.json.return_value = {"access_token": "fake-access-token"}

    mock_userinfo_resp = MagicMock(spec=Response)
    mock_userinfo_resp.raise_for_status = MagicMock()
    mock_userinfo_resp.json.return_value = {"email": "existing@example.com"}

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)
    mock_http.post = AsyncMock(return_value=mock_token_resp)
    mock_http.get = AsyncMock(return_value=mock_userinfo_resp)

    with patch("app.api.sso.settings") as mock_settings, \
         patch("app.api.sso.httpx.AsyncClient", return_value=mock_http):
        mock_settings.sso_configured = True
        mock_settings.keycloak_base_url = "https://keycloak.example.com/auth"
        mock_settings.keycloak_realm = "myrealm"
        mock_settings.keycloak_client_id = "statdash"
        mock_settings.keycloak_client_secret = "secret"
        mock_settings.sso_callback_url = "http://test/api/auth/sso/callback"
        mock_settings.sso_frontend_url = "/"

        client.cookies.set("statdash_sso_state", state)
        response = await client.get(
            "/api/auth/sso/callback",
            params={"code": "authcode", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "statdash_auth" in response.cookies
