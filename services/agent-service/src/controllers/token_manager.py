import logging
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from src.Config.settings import settings
from src.Config.redis import set_value, get_value
from src.controllers.zoho_oauth import zoho_oauth

logger = logging.getLogger("agent-service")

class TokenManager:
    def __init__(self):
        try:
            self.fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        except Exception as e:
            logger.error(f"Failed to initialize Fernet encryption. Invalid ENCRYPTION_KEY. Error: {str(e)}")
            raise RuntimeError(f"Invalid ENCRYPTION_KEY: {str(e)}") from e

    def decrypt_token(self, encrypted: str) -> str:
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failure: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Decryption of Zoho refresh token failed."
            )

    async def get_zoho_access_token(self, user_id: str, redis, db) -> str:
        redis_key = f"token:{user_id}"
        cached_token = await get_value(redis, redis_key)
        if cached_token:
            return cached_token

        try:
            res = await db.table("user_tokens").select("zoho_refresh_token").eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"Failed to retrieve user token from DB for user_id={user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error retrieving user token."
            )

        if not res.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No Zoho refresh token found. Please re-authenticate."
            )

        encrypted_refresh = res.data[0]["zoho_refresh_token"]
        refresh_token = self.decrypt_token(encrypted_refresh)

        # Refresh access token via Zoho
        new_access_token = await zoho_oauth.refresh_access_token(refresh_token)

        # Store in Redis (TTL 3600)
        await set_value(redis, redis_key, new_access_token, 3600)
        logger.info(f"Refreshed and cached Zoho access token for user_id={user_id}")

        return new_access_token

token_manager = TokenManager()

