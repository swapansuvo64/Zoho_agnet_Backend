"""
Dependency: verifies the user's app JWT and fetches the Zoho access token
from auth-service. All zoho-service routes use this.
"""
import logging
import httpx
from fastapi import Request, HTTPException, status
import jwt as pyjwt

from src.config.settings import settings

logger = logging.getLogger("zoho-service")


def _extract_bearer(request: Request) -> str:
    """Pull JWT from Authorization header or access_token cookie."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    cookie = request.cookies.get("access_token")
    if cookie:
        return cookie
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing access token (Authorization header or cookie).",
    )


def _verify_jwt(token: str) -> str:
    """Verify app JWT and return user_id (sub claim)."""
    try:
        payload = pyjwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing sub claim.",
            )
        return user_id
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
        )
    except pyjwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {str(e)}",
        )


async def get_zoho_token(request: Request) -> str:
    """
    Full dependency used by all zoho-service endpoints.
    1. Verifies the app JWT.
    2. Forwards the JWT to auth-service /auth/zoho/token to get a fresh Zoho access token.
    Returns the Zoho access token string.
    """
    app_token = _extract_bearer(request)
    _verify_jwt(app_token)  # validates locally first

    # Call auth-service to get the Zoho token (handles refresh if needed)
    auth_url = f"{settings.AUTH_SERVICE_URL}/auth/zoho/token"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                auth_url,
                headers={"Authorization": f"Bearer {app_token}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            zoho_token = data.get("zoho_access_token")
            if not zoho_token:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="auth-service returned empty Zoho token.",
                )
            return zoho_token
        elif resp.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not authenticate with Zoho. Please re-login.",
            )
        else:
            logger.error(f"auth-service error: {resp.status_code} - {resp.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"auth-service error: {resp.status_code}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reach auth-service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach auth-service to fetch Zoho token.",
        )
