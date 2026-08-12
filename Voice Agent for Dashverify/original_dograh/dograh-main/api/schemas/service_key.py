from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ServiceKeyBase(BaseModel):
    name: str


class CreateServiceKeyRequest(ServiceKeyBase):
    expires_in_days: Optional[int] = 90


class ServiceKeyResponse(ServiceKeyBase):
    id: int  # Database stores as int
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    created_by: Optional[str] = None  # provider_id from auth

    class Config:
        from_attributes = True


class CreateServiceKeyResponse(BaseModel):
    id: int  # Database stores as int
    name: str
    service_key: str  # Only returned on creation
    key_prefix: str
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True
