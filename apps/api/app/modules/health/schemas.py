from typing import Literal

from pydantic import BaseModel

DatabaseStatus = Literal["ok", "unavailable", "not_configured", "needs_update"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    version: str
    database: DatabaseStatus
    schema_version: str | None = None
    expected_schema_version: str
