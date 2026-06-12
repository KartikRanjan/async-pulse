"""Tests for the auth endpoints."""

import pytest


@pytest.mark.asyncio
async def test_login_success(client):
    """POST /api/v1/auth/login — valid credentials should return tokens."""
    # Create a user first
    await client.post(
        "/api/v1/users/",
        json={
            "email": "auth@example.com",
            "username": "authuser",
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
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"  # noqa: S105


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    """POST /api/v1/auth/login — bad password should return 401."""
    await client.post(
        "/api/v1/users/",
        json={
            "email": "auth2@example.com",
            "username": "authuser2",
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
async def test_refresh_token(client):
    """POST /api/v1/auth/refresh — valid refresh token should return new tokens."""
    # Login to get tokens
    await client.post(
        "/api/v1/users/",
        json={
            "email": "refresh@example.com",
            "username": "refreshuser",
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
    refresh_token = login_resp.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
