import logging
import httpx
from src.Config.settings import settings

logger = logging.getLogger("agent-service")

_PORTAL_ID_CACHE = None


class BaseZohoTool:
    """
    Base class for all Zoho Projects API tools.
    Encapsulates headers, authentication, and HTTP request logic.
    """
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}
        # Derives base url dynamically from settings or defaults to Zoho.in base API
        self.base_url = "https://projectsapi.zoho.in/restapi"

    async def get_portal_id(self) -> str:
        """
        Retrieves the primary Zoho Portal ID.
        """
        global _PORTAL_ID_CACHE
        if _PORTAL_ID_CACHE is not None:
            return _PORTAL_ID_CACHE
        url = f"{self.base_url}/portals/"
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(url, headers=self.headers)
                if resp.status_code == 200:
                    data = resp.json()
                    portals = data.get("portals", [])
                    if portals:
                        # Return the first active portal ID
                        _PORTAL_ID_CACHE = str(portals[0]["id"])
                        return _PORTAL_ID_CACHE
                logger.error(f"Failed to fetch portals from Zoho: Status {resp.status_code}, Response: {resp.text}")
                raise ValueError(f"Could not retrieve Zoho Portal ID (Status {resp.status_code}): {resp.text}")
            except Exception as e:
                logger.error(f"Exception fetching Zoho portals: {str(e)}")
                raise ValueError(f"Could not retrieve Zoho Portal ID (Exception): {str(e)}")
