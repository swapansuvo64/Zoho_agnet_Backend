from fastapi import Request, HTTPException, status, Depends
from supabase import AsyncClient
from redis.asyncio import Redis
from src.Config.database import get_db
from src.Config.redis import get_redis
from src.controllers.jwt_handler import jwt_handler
from src.controllers.token_manager import token_manager

async def get_current_user(request: Request) -> str:
    access_token = request.cookies.get("access_token")
    if not access_token:
        # Check authorization header if cookie is missing
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            access_token = auth_header.split(" ")[1]
        
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing access token."
        )

    payload = jwt_handler.verify_token(access_token, "access")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing sub."
        )
    return user_id

async def get_zoho_token(
    user_id: str = Depends(get_current_user),
    db: AsyncClient = Depends(get_db),
    redis: Redis = Depends(get_redis)
) -> str:
    return await token_manager.get_zoho_access_token(user_id, redis, db)
