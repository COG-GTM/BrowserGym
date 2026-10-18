from datetime import datetime, timezone
from typing import Optional


def iso(ts: Optional[float] = None) -> str:
    """ISO-8601 UTC timestamp (millisecond precision, `Z` suffix)."""
    dt = datetime.now(timezone.utc) if ts is None else datetime.fromtimestamp(ts, timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
