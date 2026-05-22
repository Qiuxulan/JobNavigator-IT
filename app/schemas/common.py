from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BaseResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    timestamp: datetime = datetime.utcnow()


class HealthResponse(BaseModel):
    status: str
    env: str
    version: Optional[str] = "v1"

