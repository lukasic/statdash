import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient) -> None:
    response = await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert not data["is_superuser"]


@pytest.mark.asyncio
async def test_login_sets_cookie(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
    })
    response = await client.post("/api/auth/jwt/login", data={
        "username": "test@example.com",
        "password": "password123",
    })
    assert response.status_code == 204
    assert "statdash_auth" in response.cookies


@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
    })
    await client.post("/api/auth/jwt/login", data={
        "username": "test@example.com",
        "password": "password123",
    })
    response = await client.get("/api/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={
        "email": "test@example.com",
        "password": "password123",
    })
    response = await client.post("/api/auth/jwt/login", data={
        "username": "test@example.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 400
