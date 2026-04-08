from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class PelotonError(Exception):
    """Raised when Peloton requests fail."""


@dataclass
class QueryFilters:
    discipline: str | None = None
    instructor: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    title: str | None = None
    class_type: str | None = None
    duration: int | None = None
    min_duration: int | None = None
    max_duration: int | None = None
    min_difficulty: float | None = None
    max_difficulty: float | None = None
    explicit: bool | None = None
    captions: bool | None = None
    available: bool | None = None
    bookmarked: bool | None = None
    song: str | None = None
    artist: str | None = None
    sort: str | None = None
    bookmark: bool | None = None
    playlist: bool | None = None


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def json_dump(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def format_minutes(seconds: Any) -> str:
    seconds = int(seconds or 0)
    minutes = seconds // 60
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_number(value: Any, digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f}"


def joules_to_kj(value: Any) -> float:
    return float(value or 0) / 1000.0


def percent_change(current: float, previous: float) -> str:
    if previous == 0:
        if current == 0:
            return "0%"
        return "new"
    change = ((current - previous) / previous) * 100.0
    sign = "+" if change > 0 else ""
    return f"{sign}{change:.0f}%"


def parse_bool_arg(flag: str, value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise PelotonError(f"{flag} requires true or false")


def timestamp_to_local(ts: Any) -> str:
    if not ts:
        return "-"
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %I:%M %p")


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def env_key_part(profile: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in profile.upper())
