from sqlalchemy import Boolean, CheckConstraint, Identity, Integer, SmallInteger, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

# The four dropdowns from the AR sheet. "Assigned To" is not a list: it comes from the users table.
LIST_KEYS = ("claim_status", "pay_status", "check_status", "action_taken")


class OptionListItem(CreatedAt, Base):
    """One choice in a dropdown. Retired choices stay on old claims but can't be picked any more."""

    __tablename__ = "option_list_items"
    __table_args__ = (
        UniqueConstraint("list_key", "value"),
        CheckConstraint(f"list_key IN {LIST_KEYS}", name="list_key_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    list_key: Mapped[str] = mapped_column(Text)
    value: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger)
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")
