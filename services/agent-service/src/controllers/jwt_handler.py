from jose import jwt, JWTError
from fastapi import HTTPException, status
from src.Config.settings import settings

class JWTHandler:
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

jwt_handler = JWTHandler()

