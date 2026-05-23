import httpx
from fastapi import HTTPException, status
from src.Config.settings import settings

class ZohoOAuth:
    async def refresh_access_token(self, refresh_token: str) -> str:
        data = {
            "refresh_token": refresh_token,
            "client_id": settings.ZOHO_CLIENT_ID,
            "client_secret": settings.ZOHO_CLIENT_SECRET,
            "grant_type": "refresh_token"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(settings.ZOHO_TOKEN_URL, data=data)
                res_data = response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Failed to communicate with Zoho token server: {str(e)}"
                )

        if "error" in res_data or response.status_code != 200:
            error_msg = res_data.get("error", "Unknown token refresh error")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Zoho token refresh failed: {error_msg}"
            )

        access_token = res_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token not returned from Zoho refresh request."
            )
        return access_token

zoho_oauth = ZohoOAuth()

