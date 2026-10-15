"""
src/api/auth.py - Authentication and Authorization for the Customer Support Chatbot API
This is the #1 production blocker.
No auth = anyone can:
  - Query the chatbot without limit
  - Upload malicious documents
  - Delete all documents
  - Access admin endpoints
  - View internal statistics
"""

# Complete implementation:

import hashlib
import hmac
import time
from enum import Enum
from functools import wraps
from typing import Optional

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

logger = structlog.get_logger(__name__)

# ── API Key Authentication ─────────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key for authentication",
)

HTTP_BEARER = HTTPBearer(auto_error=False)


class UserRole(str, Enum):
    """User roles for RBAC."""
    VIEWER = "viewer"      # Can chat only
    USER = "user"          # Can chat + submit feedback
    ADMIN = "admin"        # Full access including document management
    SYSTEM = "system"      # Internal service calls


class AuthenticatedUser:
    """Represents an authenticated user."""

    def __init__(
        self,
        user_id: str,
        role: UserRole,
        api_key_prefix: str,
        metadata: Optional[dict] = None,
    ):
        self.user_id = user_id
        self.role = role
        self.api_key_prefix = api_key_prefix
        self.metadata = metadata or {}

    def has_role(self, required_role: UserRole) -> bool:
        """Check if user has at least the required role level."""
        role_hierarchy = {
            UserRole.VIEWER: 0,
            UserRole.USER: 1,
            UserRole.ADMIN: 2,
            UserRole.SYSTEM: 3,
        }
        return role_hierarchy[self.role] >= role_hierarchy[required_role]


class APIKeyStore:
    """
    API Key store with role-based access.
    In production: use Redis or PostgreSQL, not in-memory.
    """

    def __init__(self):
        # Format: hashed_key → (user_id, role, metadata)
        self._keys: dict[str, tuple[str, UserRole, dict]] = {}

    def add_key(
        self,
        api_key: str,
        user_id: str,
        role: UserRole,
        metadata: Optional[dict] = None,
    ) -> None:
        """Store a hashed API key."""
        hashed = self._hash_key(api_key)
        self._keys[hashed] = (user_id, role, metadata or {})

    def validate_key(
        self, api_key: str
    ) -> Optional[AuthenticatedUser]:
        """Validate API key and return user if valid."""
        hashed = self._hash_key(api_key)
        entry = self._keys.get(hashed)
        if not entry:
            return None
        user_id, role, metadata = entry
        return AuthenticatedUser(
            user_id=user_id,
            role=role,
            api_key_prefix=api_key[:8] + "...",
            metadata=metadata,
        )

    def _hash_key(self, api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()


# Global key store instance
_key_store = APIKeyStore()


def init_api_keys(settings) -> None:
    """
    Initialize API keys from settings/environment.
    Call this during application startup.
    """
    from configs.settings import settings as s

    # Admin key from settings
    if s.admin_api_key:
        _key_store.add_key(
            api_key=s.admin_api_key,
            user_id="admin",
            role=UserRole.ADMIN,
            metadata={"source": "settings"},
        )

    # Default user key for development
    if s.is_development:
        _key_store.add_key(
            api_key="dev-key-12345",
            user_id="dev-user",
            role=UserRole.ADMIN,
            metadata={"source": "development"},
        )
        logger.warning(
            "Development API key active: dev-key-12345",
            warning="DO NOT USE IN PRODUCTION",
        )


# ── FastAPI Dependencies ───────────────────────────────────────────────────

async def get_current_user(
    api_key: Optional[str] = Security(API_KEY_HEADER),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(HTTP_BEARER),
) -> AuthenticatedUser:
    """
    Dependency: validates API key from header or Bearer token.
    Usage: user: AuthenticatedUser = Depends(get_current_user)
    """
    # Try X-API-Key header first
    key_to_validate = api_key

    # Fall back to Bearer token
    if not key_to_validate and bearer:
        key_to_validate = bearer.credentials

    if not key_to_validate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. "
                   "Provide X-API-Key header or Bearer token.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    user = _key_store.validate_key(key_to_validate)
    if not user:
        logger.warning(
            "Invalid API key attempt",
            key_prefix=key_to_validate[:8] + "...",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    logger.debug(
        "Authenticated request",
        user_id=user.user_id,
        role=user.role.value,
    )
    return user


def require_role(required_role: UserRole):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/admin/endpoint")
        async def admin_endpoint(
            user: AuthenticatedUser = Depends(require_role(UserRole.ADMIN))
        ):
    """
    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not user.has_role(required_role):
            logger.warning(
                "Insufficient permissions",
                user_id=user.user_id,
                user_role=user.role.value,
                required_role=required_role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. "
                       f"Required role: {required_role.value}",
            )
        return user

    return role_checker


# Convenience dependencies
require_user = require_role(UserRole.USER)
require_admin = require_role(UserRole.ADMIN)