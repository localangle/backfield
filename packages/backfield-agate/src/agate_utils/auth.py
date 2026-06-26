"""Shared authentication utilities for Agate APIs."""

import os
import logging
from typing import Optional, Dict, Any, Set
from datetime import datetime
from fastapi import Cookie, HTTPException, status, Header

try:
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
except ImportError:
    raise ImportError("itsdangerous is required for authentication. Install it with: pip install itsdangerous")

logger = logging.getLogger(__name__)

# Configuration from environment
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
SESSION_SECRET = os.getenv("SESSION_SECRET", os.getenv("SECRET_KEY", "dev-secret-key"))
serializer = URLSafeTimedSerializer(SESSION_SECRET)
SESSION_MAX_AGE = 7 * 24 * 60 * 60

# Service-to-service tokens (Bearer auth)
# Support both SERVICE_API_TOKEN (single) and SERVICE_API_TOKENS (comma-separated)
_service_tokens_env = (
    os.getenv("SERVICE_API_TOKENS")
    or os.getenv("SERVICE_API_TOKEN")
    or ""
)
SERVICE_TOKENS: Set[str] = {
    token.strip() for token in _service_tokens_env.split(",") if token and token.strip()
}


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify session token and return full token data dict if valid."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        # Check expiration if present
        if "exp" in data:
            exp_timestamp = data["exp"]
            if datetime.utcnow().timestamp() > exp_timestamp:
                return None
        return data
    except (BadSignature, SignatureExpired):
        return None


def require_auth(session: Optional[str] = Cookie(None, alias="session")) -> str:
    """
    Dependency to require authentication.
    
    Checks for valid session cookie and returns username.
    Raises 401 if not authenticated.
    """
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    token_data = verify_session_token(session)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    return token_data.get("username", "")


def verify_service_token(token: str) -> bool:
    """Check whether the provided service token is authorized."""
    return token in SERVICE_TOKENS


def require_service_auth(authorization: Optional[str] = Header(None, alias="Authorization")) -> str:
    """
    Dependency for service-to-service requests using Bearer tokens.
    
    Validates the Authorization header and returns the token value.
    """
    if not SERVICE_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service authentication not configured",
        )
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    
    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        ) from None
    
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
        )
    
    token = token.strip()
    if not verify_service_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized token",
        )
    
    return token


def require_auth_or_service(
    session: Optional[str] = Cookie(None, alias="session"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Dict[str, Any]:
    """
    Dependency that accepts either session cookie OR service token.
    
    Returns a dict with:
    - "type": "session" or "service"
    - "token_data": token data if session, None if service
    - "is_admin": True if admin session or service token
    """
    # Try service token first
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and verify_service_token(token.strip()):
                return {
                    "type": "service",
                    "token_data": None,
                    "is_admin": True,  # Service tokens have admin privileges
                }
        except (ValueError, AttributeError):
            pass
    
    # Try session token
    if session:
        token_data = verify_session_token(session)
        if token_data:
            return {
                "type": "session",
                "token_data": token_data,
                "is_admin": token_data.get("is_admin", False) or token_data.get("username", "") == ADMIN_USERNAME,
            }
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def require_project_access(
    project_id: int,
    session: Optional[str] = Cookie(None, alias="session"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> str:
    """
    Check if user has access to a core project by querying the auth database.
    Supports both session cookie authentication (for UI) and service token (for workers).
    
    Returns username if user has access to the project.
    Raises 401 if not authenticated, 403 if no access to project.
    """
    # Check for service token first (for service-to-service calls)
    if authorization:
        try:
            scheme, token = authorization.split(" ", 1)
            if scheme.lower() == "bearer" and verify_service_token(token.strip()):
                # Service tokens have access to all projects
                return "service"
        except (ValueError, AttributeError):
            pass
    
    # Fall back to session cookie authentication
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    token_data = verify_session_token(session)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    
    username = token_data.get("username", "")
    user_id = token_data.get("user_id")
    
    # Admin users have access to all projects
    if token_data.get("is_admin", False) or username == ADMIN_USERNAME:
        return username
    
    # Query unified agate_core for project access (user_projects)
    if user_id:
        try:
            from sqlalchemy import text

            from backfield_db.session import get_engine

            with get_engine().connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT 1 FROM user_projects WHERE user_id = :user_id "
                        "AND project_id = :project_id LIMIT 1"
                    ),
                    {"user_id": user_id, "project_id": project_id},
                )
                has_access = result.fetchone() is not None

            if has_access:
                return username
        except Exception as e:
            logger.warning(f"Failed to query user_projects for project access: {e}")
            projects = token_data.get("projects", [])
            if project_id in projects:
                return username
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied to this project"
    )


__all__ = [
    "verify_session_token",
    "require_auth",
    "verify_service_token",
    "require_service_auth",
    "require_auth_or_service",
    "require_project_access",
    "ADMIN_USERNAME",
    "SERVICE_TOKENS",
]
