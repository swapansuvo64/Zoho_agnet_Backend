import httpx
import urllib.parse
from fastapi import HTTPException, status
from src.Config.settings import settings

class ZohoOAuth:
    def build_authorization_url(self) -> str:
        scopes = [
            "ZohoProjects.portals.READ",
            "ZohoProjects.projects.READ",
            "ZohoProjects.tasks.ALL",
            "ZohoProjects.users.READ",
            "AaaServer.profile.READ"
        ]
        params = {
            "client_id": settings.ZOHO_CLIENT_ID,
            "response_type": "code",
            "access_type": "offline",
            "redirect_uri": settings.ZOHO_REDIRECT_URI,
            "scope": " ".join(scopes),
            "prompt": "consent"
        }
        query_string = urllib.parse.urlencode(params)
        return f"{settings.ZOHO_AUTH_URL}?{query_string}"

    async def exchange_code_for_tokens(self, code: str) -> dict:
        data = {
            "code": code,
            "client_id": settings.ZOHO_CLIENT_ID,
            "client_secret": settings.ZOHO_CLIENT_SECRET,
            "redirect_uri": settings.ZOHO_REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(settings.ZOHO_TOKEN_URL, data=data)
                res_data = response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to communicate with Zoho token server: {str(e)}"
                )

        if "error" in res_data or response.status_code != 200:
            error_msg = res_data.get("error", "Unknown token exchange error")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zoho token exchange failed: {error_msg}"
            )
        return res_data

    async def get_user_info(self, access_token: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(settings.ZOHO_USER_INFO_URL, headers=headers)
                res_data = response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to connect to Zoho user info: {str(e)}"
                )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zoho user info request failed: {response.text}"
            )

        # Zoho user profile fields
        email = res_data.get("Email") or res_data.get("email")
        name = res_data.get("Display_Name") or res_data.get("name") or res_data.get("display_name")
        zoho_user_id = (
            res_data.get("ZAUID")
            or res_data.get("zauid")
            or res_data.get("ZUID")
            or res_data.get("zuid")
            or res_data.get("id")
        )

        if not zoho_user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zoho user info missing key properties (ZAUID/ZUID/Email). Response: {res_data}"
            )

        return {
            "zoho_user_id": str(zoho_user_id),
            "email": email,
            "name": name or email.split("@")[0]
        }

    async def get_portal_id(self, access_token: str) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(settings.ZOHO_PORTALS_URL, headers=headers)
                res_data = response.json()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to connect to Zoho portals: {str(e)}"
                )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zoho portals request failed: {response.text}"
            )

        portals = res_data.get("portals", [])
        if not portals:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No portals found for this Zoho account."
            )

        portal_id = portals[0].get("id") or portals[0].get("id_string")
        if not portal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid portal object structure."
            )
        return str(portal_id)

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
