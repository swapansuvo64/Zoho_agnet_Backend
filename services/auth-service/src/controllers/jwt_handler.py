from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, status
from src.Config.settings import settings
from src.Config.redis import set_value, get_value, delete_value

class JWTHandler:
    def create_access_token(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_ACCESS_EXPIRE)
        payload = {
            "sub": user_id,
            "type": "access",
            "exp": expire
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_REFRESH_EXPIRE)
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": expire
        }
        return jwt.encode(payload, settings.JWT_REFRESH_SECRET, algorithm=settings.JWT_ALGORITHM)

    def verify_token(self, token: str, expected_type: str) -> dict:
        secret = settings.JWT_SECRET if expected_type == "access" else settings.JWT_REFRESH_SECRET
        try:
            payload = jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
            token_type = payload.get("type")
            if token_type != expected_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected: {expected_type}, Got: {token_type}"
                )
            return payload
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification failed: {str(e)}"
            )

    async def store_refresh_token(self, user_id: str, refresh_token: str, redis):
        key = f"session_refresh:{user_id}"
        await set_value(redis, key, refresh_token, settings.JWT_REFRESH_EXPIRE)

    async def rotate_jwt(self, refresh_token: str, redis) -> tuple[str, str]:
        payload = self.verify_token(refresh_token, "refresh")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing subject."
            )

        key = f"session_refresh:{user_id}"
        stored_refresh = await get_value(redis, key)

        if not stored_refresh or stored_refresh != refresh_token:
            # Token reuse attack or session expired. Clean up Redis entry.
            await delete_value(redis, key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token or session has expired."
            )

        # Generate new pair
        new_access = self.create_access_token(user_id)
        new_refresh = self.create_refresh_token(user_id)

        # Update in Redis
        await self.store_refresh_token(user_id, new_refresh, redis)

        return new_access, new_refresh

jwt_handler = JWTHandler()
