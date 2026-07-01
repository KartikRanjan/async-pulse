from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.main import app
from src.modules.users.dependencies import get_user_service


@pytest.mark.asyncio
async def test_validation_error(client: AsyncClient) -> None:
    """POST /api/v1/users/ with invalid payload should return 422 validation envelope."""
    response = await client.post(
        "/api/v1/users/",
        json={
            "email": "not-an-email",
            "username": "ch",  # too short (min 3)
            # password missing
        },
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["errorCode"] == "VALIDATION_FAILED"
    assert "message" in data
    assert "timestamp" in data
    assert "errors" in data
    assert isinstance(data["errors"], list)
    assert len(data["errors"]) > 0
    for err in data["errors"]:
        assert "field" in err
        assert "message" in err
        assert "rule" in err
    fields = [err["field"] for err in data["errors"]]
    assert "email" in fields
    assert "username" in fields
    assert "password" in fields


class _BrokenUserService:
    """Stand-in for ``UserService`` that fails every call.

    Only implements the public methods exercised by the router — used to
    simulate an internal failure via the public dependency interface rather
    than patching ``UserService`` internals.
    """

    async def get_user(self, user_id: str) -> object:
        """Simulate an internal failure when fetching a user."""
        raise RuntimeError("Simulated internal database failure")


async def _broken_user_service() -> _BrokenUserService:
    return _BrokenUserService()


@pytest.mark.asyncio
async def test_unhandled_exception(db_session: AsyncSession) -> None:
    """Verify that any unhandled generic Exception returns standardized 500 envelope."""

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_user_service] = _broken_user_service
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as custom_client:
        response = await custom_client.get("/api/v1/users/00000000-0000-0000-0000-000000000000")

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["errorCode"] == "INTERNAL_SERVER_ERROR"
        assert data["message"] == "An unexpected error occurred"
        assert "timestamp" in data
        assert "errors" not in data  # Should be omitted when empty

    app.dependency_overrides.clear()
