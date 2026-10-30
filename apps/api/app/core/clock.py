from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def business_today() -> date:
    """Today's date where the AR team works. Follow-ups and aging are counted from this."""
    return datetime.now(ZoneInfo(get_settings().business_timezone)).date()


AGING_BUCKETS = ((15, "0 - 15"), (30, "16 - 30"), (60, "31 - 60"), (90, "61 - 90"), (120, "91 - 120"))


def aging(service_date: date, today: date) -> tuple[int, str]:
    """Days since the service date, and the bucket label used in the AR sheet."""
    days = max((today - service_date).days, 0)
    for limit, label in AGING_BUCKETS:
        if days <= limit:
            return days, label
    return days, "120+"
