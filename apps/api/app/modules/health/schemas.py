from typing import Literal

from pydantic import BaseModel

DatabaseStatus = Literal["ok", "unavailable", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    version: str
    database: DatabaseStatus
