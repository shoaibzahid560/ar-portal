from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    created_at: datetime
    read: bool


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int
