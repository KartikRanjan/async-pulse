"""Tests for the user endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_user(client):
    """POST /api/v1/users/ — should create and return a new user."""
    payload = {
        "email": "alice@example.com",
        "username": "alice",
        "password": "securepass123",
    }
    response = await client.post("/api/v1/users/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["username"] == "alice"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client):
    """POST /api/v1/users/ — duplicate email should return 409."""
    payload = {
        "email": "bob@example.com",
        "username": "bob",
        "password": "securepass123",
    }
    resp1 = await client.post("/api/v1/users/", json=payload)
    assert resp1.status_code == 201

    payload2 = {
        "email": "bob@example.com",
        "username": "bob2",
        "password": "securepass123",
    }
    resp2 = await client.post("/api/v1/users/", json=payload2)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_list_users(client):
    """GET /api/v1/users/ — should return paginated users."""
    # Create two users
    for i in range(2):
        await client.post(
            "/api/v1/users/",
            json={
                "email": f"user{i}@example.com",
                "username": f"user{i}",
                "password": "securepass123",
            },
        )

    response = await client.get("/api/v1/users/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_get_user(client):
    """GET /api/v1/users/{id} — should return a single user."""
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "charlie@example.com",
            "username": "charlie",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["id"]

    response = await client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["email"] == "charlie@example.com"


@pytest.mark.asyncio
async def test_get_user_not_found(client):
    """GET /api/v1/users/{id} — nonexistent ID should return 404."""
    response = await client.get("/api/v1/users/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user(client):
    """PATCH /api/v1/users/{id} — should update and return the user."""
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "dave@example.com",
            "username": "dave",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["id"]

    response = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "david"},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "david"


@pytest.mark.asyncio
async def test_delete_user(client):
    """DELETE /api/v1/users/{id} — should delete and return 204."""
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "eve@example.com",
            "username": "eve",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["id"]

    response = await client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 204

    # Verify deleted
    get_resp = await client.get(f"/api/v1/users/{user_id}")
    assert get_resp.status_code == 404
