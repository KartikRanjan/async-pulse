"""Tests for the user endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.users.models import UserModel


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
    """POST /api/v1/users/ — should create and return a new user wrapped in SuccessResponse."""
    payload = {
        "email": "alice@example.com",
        "username": "alice",
        "name": "Alice",
        "password": "securepass123",
    }
    response = await client.post("/api/v1/users/", json=payload)
    assert response.status_code == 201
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "User created successfully"
    data = res_body["data"]
    assert data["email"] == "alice@example.com"
    assert data["username"] == "alice"
    assert data["isActive"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient) -> None:
    """POST /api/v1/users/ — duplicate email should return 409."""
    payload = {
        "email": "bob@example.com",
        "username": "bob",
        "name": "Bob",
        "password": "securepass123",
    }
    resp1 = await client.post("/api/v1/users/", json=payload)
    assert resp1.status_code == 201

    payload2 = {
        "email": "bob@example.com",
        "username": "bob2",
        "name": "Bob Two",
        "password": "securepass123",
    }
    resp2 = await client.post("/api/v1/users/", json=payload2)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient) -> None:
    """GET /api/v1/users/ — should return paginated users wrapped in SuccessResponse."""
    # Create two users
    for i in range(2):
        await client.post(
            "/api/v1/users/",
            json={
                "email": f"user{i}@example.com",
                "username": f"user{i}",
                "name": f"User {i}",
                "password": "securepass123",
            },
        )

    response = await client.get("/api/v1/users/")
    assert response.status_code == 200
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "Users retrieved successfully"
    data = res_body["data"]
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 20


@pytest.mark.asyncio
async def test_get_user(client: AsyncClient) -> None:
    """GET /api/v1/users/{id} — should return a single user wrapped in SuccessResponse."""
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "charlie@example.com",
            "username": "charlie",
            "name": "Charlie",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["data"]["id"]

    response = await client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "User retrieved successfully"
    assert res_body["data"]["email"] == "charlie@example.com"


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient) -> None:
    """GET /api/v1/users/{id} — nonexistent ID should return standardized 404 envelope."""
    import uuid

    nonexistent_uuid = str(uuid.uuid4())
    response = await client.get(f"/api/v1/users/{nonexistent_uuid}")
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert "errorCode" in data
    assert "message" in data
    assert "timestamp" in data
    assert "errors" not in data  # Should be omitted when empty


@pytest.mark.asyncio
async def test_get_user_invalid_uuid_format(client: AsyncClient) -> None:
    """GET /api/v1/users/{id} — malformed UUID should return standardized 422 envelope."""
    response = await client.get("/api/v1/users/nonexistent-id")
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["errorCode"] == "VALIDATION_FAILED"
    assert "message" in data
    assert "errors" in data


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient) -> None:
    """PATCH /api/v1/users/{id} — should update and return the user wrapped in SuccessResponse."""
    # Create user
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "dave@example.com",
            "username": "dave",
            "name": "Dave",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["data"]["id"]

    # Login to get access token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dave@example.com", "password": "securepass123"},
    )
    token = login_resp.json()["data"]["tokenPair"]["accessToken"]

    # Update with auth
    response = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "david"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    res_body = response.json()
    assert res_body["success"] is True
    assert res_body["message"] == "User updated successfully"
    assert res_body["data"]["username"] == "david"


@pytest.mark.asyncio
async def test_delete_user_requires_superuser(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /api/v1/users/{id} — requires superuser privileges."""
    # Create user
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "eve@example.com",
            "username": "eve",
            "name": "Eve",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["data"]["id"]

    # Login as regular user
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "eve@example.com", "password": "securepass123"},
    )
    token = login_resp.json()["data"]["tokenPair"]["accessToken"]

    # Regular user cannot delete — should return 403
    response = await client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_as_superuser(client: AsyncClient, db_session: AsyncSession) -> None:
    """DELETE /api/v1/users/{id} — superuser can soft-delete a user."""
    # Create user to delete
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "victim@example.com",
            "username": "victim",
            "name": "Victim",
            "password": "securepass123",
        },
    )
    victim_id = create_resp.json()["data"]["id"]

    # Create superuser
    admin_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "admin@example.com",
            "username": "admin",
            "name": "Admin",
            "password": "securepass123",
        },
    )
    admin_id = admin_resp.json()["data"]["id"]

    # Promote to superuser directly in DB
    from sqlalchemy import select

    from src.modules.users.entities import UserRole

    await db_session.execute(
        update(UserModel).where(UserModel.id == admin_id).values(role=UserRole.SUPERUSER)
    )
    await db_session.commit()

    # Login as superuser
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "securepass123"},
    )
    admin_token = login_resp.json()["data"]["tokenPair"]["accessToken"]

    # Delete with superuser auth — should soft-delete (204)
    response = await client.delete(
        f"/api/v1/users/{victim_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 204

    # Verify soft-deleted: user is no longer accessible via GET (returns 404)
    get_resp = await client.get(f"/api/v1/users/{victim_id}")
    assert get_resp.status_code == 404

    # Verify soft-deleted state exists in DB
    db_row = (
        await db_session.execute(select(UserModel).where(UserModel.id == victim_id))
    ).scalar_one()
    assert db_row.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_user_unauthenticated(client: AsyncClient) -> None:
    """DELETE /api/v1/users/{id} — anonymous request should return 401."""
    # Create user
    create_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "anon@example.com",
            "username": "anon",
            "name": "Anon",
            "password": "securepass123",
        },
    )
    user_id = create_resp.json()["data"]["id"]

    # No auth header
    response = await client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 401
