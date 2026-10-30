import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.schemas import NamedRef


def upload_label(number: int) -> str:
    return f"UPL-{number:06d}"


class UploadOut(BaseModel):
    id: uuid.UUID
    number: str
    practice: NamedRef
    uploaded_by: NamedRef
    file_name: str
    file_size: int
    status: str
    failure_reason: str | None
    total_rows: int
    created_claims: int
    duplicate_rows: int
    error_rows: int
    review_rows: int
    created_at: datetime
    completed_at: datetime | None


class RowErrorOut(BaseModel):
    row_number: int
    column: str
    message: str


class UploadDetail(UploadOut):
    errors: list[RowErrorOut]
