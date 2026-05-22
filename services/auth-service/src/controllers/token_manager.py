import logging
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from src.Config.settings import settings
from src.Config.redis import set_value, get_value
from src.controllers.zoho_oauth import zoho_oauth

logger = logging.getLogger("auth-service")

class TokenManager:
    def __init__(self):
        try:
            self.fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        except Exception as e:
            logger.error(f"Failed to initialize Fernet encryption. Invalid ENCRYPTION_KEY. Error: {str(e)}")
            raise RuntimeError(f"Invalid ENCRYPTION_KEY: {str(e)}") from e

    def encrypt_token(self, token: str) -> str:
        return self.fernet.encrypt(token.encode()).decode()

    def decrypt_token(self, encrypted: str) -> str:
        try:
            return self.fernet.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failure: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Decryption of Zoho refresh token failed."
            )

    async def store_zoho_refresh_token(self, user_id: str, refresh_token: str, db):
        encrypted = self.encrypt_token(refresh_token)
        try:
            payload = {
                "user_id": user_id,
                "zoho_refresh_token": encrypted
            }
            await db.table("user_tokens").upsert(payload, on_conflict="user_id").execute()
            logger.info(f"Successfully stored encrypted Zoho refresh token for user_id={user_id}")
        except Exception as e:
            logger.error(f"Failed to upsert Zoho refresh token for user_id={user_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error storing Zoho refresh token: {str(e)}"
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

    async def rotate_all_access_tokens(self, redis, db):
        try:
            res = await db.table("user_tokens").select("user_id, zoho_refresh_token").execute()
        except Exception as e:
            logger.error(f"Failed to fetch user tokens for background rotation: {str(e)}")
            raise

        for row in res.data:
            user_id = row.get("user_id")
            encrypted_refresh = row.get("zoho_refresh_token")
            if not user_id or not encrypted_refresh:
                continue
            try:
                refresh_token = self.decrypt_token(encrypted_refresh)
                new_access_token = await zoho_oauth.refresh_access_token(refresh_token)
                await set_value(redis, f"token:{user_id}", new_access_token, 3600)
                logger.info(f"Successfully rotated Zoho access token in background for user_id={user_id}")
            except Exception as e:
                logger.error(f"Failed to rotate Zoho access token in background for user_id={user_id}: {str(e)}")

token_manager = TokenManager()
