"""Unit and integration tests for RTR, status transitions, grace periods, and hierarchical RBAC."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.cache import get_cache_client
from src.modules.users.entities import User, UserRole, UserStatus
from src.modules.users.exceptions import InvalidStatusTransitionError
from src.modules.users.models import UserModel

# ── 1. Status State Machine Unit Tests ───────────────────


def test_user_status_state_machine_valid_transitions() -> None:
    """Verify allowed user status transitions."""
    user = User(
        user_id="test-id",
        email="test@example.com",
        username="testuser",
        hashed_password="hashed_password",
        status=UserStatus.PENDING_VERIFICATION,
    )

    # PENDING_VERIFICATION -> ACTIVE
    user.transition_to(UserStatus.ACTIVE)
    assert user.status == UserStatus.ACTIVE

    # ACTIVE -> SUSPENDED
    user.transition_to(UserStatus.SUSPENDED)
    assert user.status == UserStatus.SUSPENDED

    # SUSPENDED -> ACTIVE
    user.transition_to(UserStatus.ACTIVE)
    assert user.status == UserStatus.ACTIVE

    # ACTIVE -> BANNED
    user.transition_to(UserStatus.BANNED)
    assert user.status == UserStatus.BANNED


def test_user_status_state_machine_invalid_transitions() -> None:
    """Verify blocked/invalid transitions raise exception."""
    user = User(
        user_id="test-id",
        email="test@example.com",
        username="testuser",
        hashed_password="hashed_password",
        status=UserStatus.BANNED,
    )

    # BANNED is a terminal state, cannot transition to anything
    with pytest.raises(InvalidStatusTransitionError):
        user.transition_to(UserStatus.ACTIVE)


# ── 2. Device limit, Logout & Session Management Integration Tests ─


@pytest.mark.asyncio
async def test_session_device_limits(client: AsyncClient) -> None:
    """POST /auth/login — logging in 6 times should revoke the oldest session (limit 5)."""
    # Create user
    email = "limit@example.com"
    create_resp = await client.post(
        "/api/v1/users/",
        json={"email": email, "username": "limituser", "password": "securepass123"},
    )
    user_id = create_resp.json()["data"]["id"]

    sessions: list[dict[str, Any]] = []
    # Login 6 times
    for i in range(6):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "securepass123"},
            headers={"User-Agent": f"Device-{i}"},
        )
        assert resp.status_code == 200
        sessions.append(resp.json()["data"])

    # First session (sessions[0]) access token should now be invalid/revoked
    first_token = sessions[0]["access_token"]
    protected_resp = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "newlimit"},
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert protected_resp.status_code == 401

    # Last session (sessions[5]) should be active and valid
    last_token = sessions[5]["access_token"]
    protected_resp = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "newlimit2"},
        headers={"Authorization": f"Bearer {last_token}"},
    )
    assert protected_resp.status_code == 200


@pytest.mark.asyncio
async def test_logout_and_logout_all(client: AsyncClient) -> None:
    """POST /auth/logout & /auth/logout-all — should revoke sessions."""
    email = "logout@example.com"
    create_resp = await client.post(
        "/api/v1/users/",
        json={"email": email, "username": "logoutuser", "password": "securepass123"},
    )
    user_id = create_resp.json()["data"]["id"]

    # Create 2 sessions
    resp1 = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "securepass123"}
    )
    resp2 = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "securepass123"}
    )
    tokens1 = resp1.json()["data"]
    tokens2 = resp2.json()["data"]

    # Logout session 1
    logout_resp = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {tokens1['access_token']}"},
    )
    assert logout_resp.status_code == 204

    # Session 1 token is invalid
    check1 = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "logout1"},
        headers={"Authorization": f"Bearer {tokens1['access_token']}"},
    )
    assert check1.status_code == 401

    # Session 2 is still valid
    check2 = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "logout2"},
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )
    assert check2.status_code == 200

    # Logout all
    logout_all_resp = await client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )
    assert logout_all_resp.status_code == 204

    # Session 2 token is now also invalid
    check2_after = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "logout3"},
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )
    assert check2_after.status_code == 401


# ── 3. RTR Token Rotation and Breach Detection ───────────


@pytest.mark.asyncio
async def test_rtr_rotation_and_breach_detection(client: AsyncClient) -> None:
    """RTR — rotation works, and reusing an old refresh token revokes all user sessions."""
    email = "rtr@example.com"
    create_resp = await client.post(
        "/api/v1/users/",
        json={"email": email, "username": "rtruser", "password": "securepass123"},
    )
    user_id = create_resp.json()["data"]["id"]

    # Login to get first session tokens (T1)
    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "securepass123"}
    )
    tokens1 = login_resp.json()["data"]
    r_token1 = tokens1["refresh_token"]

    # Also log in from another device (S2)
    s2_login_resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "securepass123"}
    )
    s2_tokens = s2_login_resp.json()["data"]

    # Rotate T1 -> T2
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": r_token1},
    )
    assert refresh_resp.status_code == 200
    tokens2 = refresh_resp.json()["data"]

    # Clear grace period cache *after* rotation so the replay request
    # falls through to DB breach check
    cache = get_cache_client()
    import jose.jwt

    from src.core.settings import get_settings

    payload = jose.jwt.decode(r_token1, get_settings().SECRET_KEY, algorithms=["HS256"])
    session_id = payload["jti"]
    await cache.delete(f"grace:{session_id}")

    # A delayed replay of R1 (after grace window is gone/cleared)
    replay_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": r_token1},
    )
    # Replay must fail
    assert replay_resp.status_code == 401

    # And ALL sessions for that user (including S2 and T2) must have been revoked
    check_t2 = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "rtr1"},
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )
    assert check_t2.status_code == 401

    check_s2 = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"username": "rtr2"},
        headers={"Authorization": f"Bearer {s2_tokens['access_token']}"},
    )
    assert check_s2.status_code == 401


# ── 4. Rotation Grace Period ─────────────────────────────


@pytest.mark.asyncio
async def test_rtr_rotation_grace_period(client: AsyncClient) -> None:
    """RTR — concurrent requests replaying refresh token within grace window return same tokens."""
    email = "grace@example.com"
    await client.post(
        "/api/v1/users/",
        json={"email": email, "username": "graceuser", "password": "securepass123"},
    )

    login_resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "securepass123"}
    )
    tokens = login_resp.json()["data"]
    r_token = tokens["refresh_token"]

    # Send first refresh request
    resp1 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": r_token},
    )
    assert resp1.status_code == 200
    res1_data = resp1.json()["data"]

    # Send concurrent second refresh request with same token (simulating race conditions)
    resp2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": r_token},
    )
    # Should succeed and return the exact same access & refresh tokens
    assert resp2.status_code == 200
    res2_data = resp2.json()["data"]
    assert res1_data["access_token"] == res2_data["access_token"]
    assert res1_data["refresh_token"] == res2_data["refresh_token"]


# ── 5. Hierarchical RBAC ─────────────────────────────────


@pytest.mark.asyncio
async def test_hierarchical_rbac_delete_user(client: AsyncClient, db_session: AsyncSession) -> None:
    """Hierarchical RBAC — user deletion requires SUPERUSER; USER and ADMIN roles are rejected."""
    # Create target user
    victim_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "victim-rbac@example.com",
            "username": "victimrbac",
            "password": "securepass123",
        },
    )
    victim_id = victim_resp.json()["data"]["id"]

    # Create tester user
    tester_resp = await client.post(
        "/api/v1/users/",
        json={
            "email": "tester-rbac@example.com",
            "username": "testerrbac",
            "password": "securepass123",
        },
    )
    tester_id = tester_resp.json()["data"]["id"]

    # Login as USER
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "tester-rbac@example.com", "password": "securepass123"},
    )
    user_token = login_resp.json()["data"]["access_token"]

    # 1. USER role tries to delete -> 403 Forbidden
    del_resp1 = await client.delete(
        f"/api/v1/users/{victim_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert del_resp1.status_code == 403

    # Clear user cache before role change to prevent stale cache read in token verify
    cache = get_cache_client()
    await cache.delete(f"user:{tester_id}")

    # 2. Promote to ADMIN in DB
    await db_session.execute(
        update(UserModel).where(UserModel.id == tester_id).values(role=UserRole.ADMIN)
    )
    await db_session.commit()

    # ADMIN tries to delete -> 403 Forbidden
    del_resp2 = await client.delete(
        f"/api/v1/users/{victim_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert del_resp2.status_code == 403

    await cache.delete(f"user:{tester_id}")

    # 3. Promote to SUPERUSER in DB
    await db_session.execute(
        update(UserModel).where(UserModel.id == tester_id).values(role=UserRole.SUPERUSER)
    )
    await db_session.commit()

    # SUPERUSER tries to delete -> 204 No Content
    del_resp3 = await client.delete(
        f"/api/v1/users/{victim_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert del_resp3.status_code == 204
