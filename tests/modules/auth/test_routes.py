"""Tests for the auth endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """POST /api/v1/auth/login — valid credentials should return wrapped tokens."""
    # Create a user first
    await client.post(
        "/api/v1/users/",
        json={
            "email": "auth@example.com",
            "username": "authuser",
            "name": "Test User",
            "password": "securepass123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "auth@example.com",
            "password": "securepass123",
        },
    )
    assert response.status_code == 200
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "Login successful"
    data = res_body["data"]
    token_pair = data["tokenPair"]
    assert "accessToken" in token_pair
    assert "refreshToken" in token_pair
    assert token_pair["tokenType"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient) -> None:
    """POST /api/v1/auth/login — bad password should return 401."""
    await client.post(
        "/api/v1/users/",
        json={
            "email": "auth2@example.com",
            "username": "authuser2",
            "name": "Test User",
            "password": "securepass123",
        },
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "auth2@example.com",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient) -> None:
    """POST /api/v1/auth/refresh — valid refresh token should return wrapped tokens."""
    # Login to get tokens
    await client.post(
        "/api/v1/users/",
        json={
            "email": "refresh@example.com",
            "username": "refreshuser",
            "name": "Test User",
            "password": "securepass123",
        },
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "refresh@example.com",
            "password": "securepass123",
        },
    )
    refresh_token = login_resp.json()["data"]["tokenPair"]["refreshToken"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "Token refreshed successfully"
    data = res_body["data"]
    assert "accessToken" in data
    assert "refreshToken" in data
