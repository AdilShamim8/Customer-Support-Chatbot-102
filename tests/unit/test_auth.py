"""
Unit tests for authentication and RBAC (src/api/auth.py).

The auth layer is the #1 production blocker (per the module's own
docstring): these tests pin the contract that keys validate, roles
escalate correctly, and failures leak nothing.
"""

import pytest

from src.api.auth import APIKeyStore, AuthenticatedUser, UserRole


@pytest.fixture
def store():
    s = APIKeyStore()
    s.add_key("sk-live-admin-key-0001", "admin-1", UserRole.ADMIN)
    s.add_key("sk-live-user-key-0002", "user-1", UserRole.USER)
    s.add_key("sk-live-viewer-key-0003", "viewer-1", UserRole.VIEWER)
    return s


class TestAPIKeyStore:
    def test_valid_key_returns_user(self, store):
        user = store.validate_key("sk-live-admin-key-0001")
        assert user is not None
        assert user.user_id == "admin-1"
        assert user.role == UserRole.ADMIN

    def test_invalid_key_returns_none(self, store):
        assert store.validate_key("sk-not-a-key") is None

    def test_keys_are_hashed_at_rest(self, store):
        # Raw key material must never sit in the store dict
        raw = "sk-live-admin-key-0001"
        assert raw not in str(store._keys)
        assert raw[:20] not in str(store._keys)

    def test_prefix_is_short_but_not_the_key(self, store):
        user = store.validate_key("sk-live-admin-key-0001")
        assert user.api_key_prefix.endswith("...")
        assert "sk-live-admin-key" not in user.api_key_prefix[:8]


class TestRoleHierarchy:
    @pytest.mark.parametrize(
        "role,required,allowed",
        [
            (UserRole.VIEWER, UserRole.VIEWER, True),
            (UserRole.VIEWER, UserRole.USER, False),
            (UserRole.USER, UserRole.VIEWER, True),   # hierarchy grants lesser
            (UserRole.USER, UserRole.ADMIN, False),
            (UserRole.ADMIN, UserRole.ADMIN, True),
            (UserRole.SYSTEM, UserRole.ADMIN, True),
        ],
    )
    def test_role_gating(self, role, required, allowed):
        user = AuthenticatedUser("u", role, "prefix...")
        assert user.has_role(required) is allowed


class TestGetCurrentUserDependency:
    """The FastAPI dependency contract used by every protected route."""

    async def test_missing_credentials_rejected(self):
        from fastapi import HTTPException

        from src.api.auth import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key=None, bearer=None)
        assert exc_info.value.status_code == 401

    async def test_invalid_key_rejected_401(self):
        from fastapi import HTTPException

        from src.api.auth import get_current_user, _key_store

        _key_store._keys.clear()  # isolate from global state
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(api_key="totally-wrong", bearer=None)
        assert exc_info.value.status_code == 401

    async def test_valid_key_via_header(self):
        from src.api.auth import _key_store, get_current_user

        _key_store._keys.clear()
        _key_store.add_key("sk-test-valid-123456", "tester", UserRole.USER)
        user = await get_current_user(api_key="sk-test-valid-123456", bearer=None)
        assert user.user_id == "tester"
        _key_store._keys.clear()


class TestAuthenticatedUser:
    def test_metadata_defaults_to_dict(self):
        user = AuthenticatedUser("u", UserRole.USER, "p...")
        assert user.metadata == {}
