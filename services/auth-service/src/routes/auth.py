from datetime import datetime, timezone
import logging
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from supabase import AsyncClient
from redis.asyncio import Redis

from src.Config.settings import settings
from src.Config.database import get_db
from src.Config.redis import get_redis, set_value, delete_value
from src.controllers.zoho_oauth import zoho_oauth
from src.controllers.token_manager import token_manager
from src.controllers.jwt_handler import jwt_handler
from src.routes.dependencies import get_current_user
from src.models.user import UserResponse

logger = logging.getLogger("auth-service")
router = APIRouter()

@router.get("/login")
async def login():
    auth_url = zoho_oauth.build_authorization_url()
    return RedirectResponse(url=auth_url)

@router.get("/callback")
async def callback(code: str, db: AsyncClient = Depends(get_db), redis: Redis = Depends(get_redis)):
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code."
        )

    # 1. Exchange code for Zoho tokens
    zoho_tokens = await zoho_oauth.exchange_code_for_tokens(code)
    zoho_access_token = zoho_tokens["access_token"]
    zoho_refresh_token = zoho_tokens.get("refresh_token")

    # 2. Get Zoho User Info and Portal ID
    user_info = await zoho_oauth.get_user_info(zoho_access_token)
    portal_id = await zoho_oauth.get_portal_id(zoho_access_token)

    # 3. Upsert user in the Supabase 'users' table
    # This will create a new user or update the last login if the user already exists
    user_payload = {
        "zoho_user_id": user_info["zoho_user_id"],
        "email": user_info["email"],
        "name": user_info["name"],
        "portal_id": portal_id,
        "last_login": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        res = await db.table("users").upsert(user_payload, on_conflict="zoho_user_id").execute()
    except Exception as e:
        logger.error(f"Failed to upsert user record in Supabase: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during user registration: {str(e)}"
        )

    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user record after database upsert."
        )

    user_id = res.data[0]["id"]

    # 4. Save Zoho Refresh Token (only if provided in response)
    if zoho_refresh_token:
        await token_manager.store_zoho_refresh_token(user_id, zoho_refresh_token, db)

    # 5. Cache Zoho Access Token in Redis
    await set_value(redis, f"token:{user_id}", zoho_access_token, 3600)

    # 6. Generate app-specific JWT Access & Refresh Tokens
    app_access_token = jwt_handler.create_access_token(user_id)
    app_refresh_token = jwt_handler.create_refresh_token(user_id)

    # 7. Store app-specific JWT Refresh Token in Redis
    await jwt_handler.store_refresh_token(user_id, app_refresh_token, redis)

    # 8. Set HttpOnly cookies on RedirectResponse to Frontend Chat
    redirect_url = f"{settings.FRONTEND_URL.rstrip('/')}/chat"
    response = RedirectResponse(url=redirect_url)
    
    response.set_cookie(
        key="access_token",
        value=app_access_token,
        max_age=settings.JWT_ACCESS_EXPIRE,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    response.set_cookie(
        key="refresh_token",
        value=app_refresh_token,
        max_age=settings.JWT_REFRESH_EXPIRE,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    
    logger.info(f"User successful authentication callback. user_id={user_id}")
    return response

@router.get("/refresh")
async def refresh(request: Request, redis: Redis = Depends(get_redis)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie."
        )

    # Rotate JWT tokens (checks for token reuse internally)
    new_access, new_refresh = await jwt_handler.rotate_jwt(refresh_token, redis)

    response = JSONResponse(content={"message": "tokens rotated"})
    response.set_cookie(
        key="access_token",
        value=new_access,
        max_age=settings.JWT_ACCESS_EXPIRE,
        httponly=True,
        secure=True,
        samesite="lax"
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        max_age=settings.JWT_REFRESH_EXPIRE,
        httponly=True,
        secure=True,
        samesite="lax"
    )

    return response

@router.post("/logout")
async def logout(request: Request, response: Response, redis: Redis = Depends(get_redis)):
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token."
        )

    payload = jwt_handler.verify_token(access_token, "access")
    user_id = payload.get("sub")

    if user_id:
        # Delete sessions from Redis
        await delete_value(redis, f"token:{user_id}")
        await delete_value(redis, f"session_refresh:{user_id}")
        logger.info(f"User logged out successfully. user_id={user_id}")

    # Clear response cookies
    response.delete_cookie("access_token", httponly=True, secure=True, samesite="lax")
    response.delete_cookie("refresh_token", httponly=True, secure=True, samesite="lax")

    return {"message": "logged out"}

@router.get("/me", response_model=UserResponse)
async def me(user_id: str = Depends(get_current_user), db: AsyncClient = Depends(get_db)):
    try:
        res = await db.table("users").select("*").eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"Failed to fetch user me data for user_id={user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error retrieving user profile."
        )

    if not res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    return res.data[0]

@router.get("/token")
async def get_token(request: Request):
    """Return the raw access token from HttpOnly cookie.
    Used by the frontend to pass the token as a query param for WebSocket connections."""
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token cookie."
        )
    # Verify token is still valid before returning it
    jwt_handler.verify_token(access_token, "access")
    return {"token": access_token}

@router.get("/zoho/token")
async def get_zoho_token(
    user_id: str = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    try:
        zoho_access_token = await token_manager.get_zoho_access_token(user_id, redis, db)
        return {"zoho_access_token": zoho_access_token}
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching/refreshing Zoho token in auth-service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving Zoho token: {str(e)}"
        )
