from datetime import datetime
from pydantic import BaseModel, EmailStr, UUID4
from typing import Optional

class UserInDB(BaseModel):
    id: UUID4
    zoho_user_id: str
    email: EmailStr
    name: str
    portal_id: str
    created_at: datetime
    last_login: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: UUID4
    email: EmailStr
    name: str
    portal_id: str
    last_login: Optional[datetime] = None

class ZohoTokenData(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
