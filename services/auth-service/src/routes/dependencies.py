from fastapi import Request, HTTPException, status
from src.controllers.jwt_handler import jwt_handler

async def get_current_user(request: Request) -> str:
    access_token = request.cookies.get("access_token")
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
