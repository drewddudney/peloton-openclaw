#!/usr/bin/env python3
"""
Peloton skill CLI.

Commands:
  --profile <name>
  me
  settings
  today
  yesterday
  month
  workouts [limit]
  latest
  workout <workout_id>
  metrics <workout_id> [every_n]
  summary [days]
  weekly
  compare [recent_days] [previous_days]
  compare-profiles <profile_a> <profile_b> [days]
  classes [discipline] [limit]
  instructors
  instructor <instructor_id>
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_BASE = "https://api.onepeloton.com"
AUTH_BASE = "https://auth.onepeloton.com"
TOKEN_URL = f"{AUTH_BASE}/oauth/token"
CLIENT_ID = "mgsmWCD0A8Qn6uz6mmqI6qeBNHH9IPwS"
DEFAULT_TIMEOUT = 20
CACHE_TTL_SECONDS = 15 * 60


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


def parse_args(argv: list[str]) -> tuple[str | None, bool, QueryFilters, list[str]]:
    profile = None
    json_output = False
    filters = QueryFilters()
    args: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--profile":
            if i + 1 >= len(argv):
                raise PelotonError("--profile requires a profile name")
            profile = argv[i + 1].strip().lower()
            if not profile:
                raise PelotonError("--profile requires a non-empty profile name")
            i += 2
            continue
        if arg == "--discipline":
            if i + 1 >= len(argv):
                raise PelotonError("--discipline requires a value")
            filters.discipline = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--instructor":
            if i + 1 >= len(argv):
                raise PelotonError("--instructor requires a value")
            filters.instructor = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--title":
            if i + 1 >= len(argv):
                raise PelotonError("--title requires a value")
            filters.title = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--class-type":
            if i + 1 >= len(argv):
                raise PelotonError("--class-type requires a value")
            filters.class_type = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--duration":
            if i + 1 >= len(argv):
                raise PelotonError("--duration requires minutes")
            filters.duration = int(argv[i + 1])
            i += 2
            continue
        if arg == "--min-duration":
            if i + 1 >= len(argv):
                raise PelotonError("--min-duration requires minutes")
            filters.min_duration = int(argv[i + 1])
            i += 2
            continue
        if arg == "--max-duration":
            if i + 1 >= len(argv):
                raise PelotonError("--max-duration requires minutes")
            filters.max_duration = int(argv[i + 1])
            i += 2
            continue
        if arg == "--min-difficulty":
            if i + 1 >= len(argv):
                raise PelotonError("--min-difficulty requires a value")
            filters.min_difficulty = float(argv[i + 1])
            i += 2
            continue
        if arg == "--max-difficulty":
            if i + 1 >= len(argv):
                raise PelotonError("--max-difficulty requires a value")
            filters.max_difficulty = float(argv[i + 1])
            i += 2
            continue
        if arg == "--explicit":
            if i + 1 >= len(argv):
                raise PelotonError("--explicit requires true or false")
            filters.explicit = parse_bool_arg("--explicit", argv[i + 1])
            i += 2
            continue
        if arg == "--captions":
            if i + 1 >= len(argv):
                raise PelotonError("--captions requires true or false")
            filters.captions = parse_bool_arg("--captions", argv[i + 1])
            i += 2
            continue
        if arg == "--available":
            if i + 1 >= len(argv):
                raise PelotonError("--available requires true or false")
            filters.available = parse_bool_arg("--available", argv[i + 1])
            i += 2
            continue
        if arg == "--bookmarked":
            if i + 1 >= len(argv):
                raise PelotonError("--bookmarked requires true or false")
            filters.bookmarked = parse_bool_arg("--bookmarked", argv[i + 1])
            i += 2
            continue
        if arg == "--song":
            if i + 1 >= len(argv):
                raise PelotonError("--song requires a value")
            filters.song = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--artist":
            if i + 1 >= len(argv):
                raise PelotonError("--artist requires a value")
            filters.artist = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--sort":
            if i + 1 >= len(argv):
                raise PelotonError("--sort requires a value")
            filters.sort = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg == "--bookmark":
            if i + 1 >= len(argv):
                raise PelotonError("--bookmark requires true or false")
            filters.bookmark = parse_bool_arg("--bookmark", argv[i + 1])
            i += 2
            continue
        if arg == "--playlist":
            if i + 1 >= len(argv):
                raise PelotonError("--playlist requires true or false")
            filters.playlist = parse_bool_arg("--playlist", argv[i + 1])
            i += 2
            continue
        if arg == "--since":
            if i + 1 >= len(argv):
                raise PelotonError("--since requires YYYY-MM-DD")
            filters.since = parse_date_arg(argv[i + 1], end_of_day=False)
            i += 2
            continue
        if arg == "--until":
            if i + 1 >= len(argv):
                raise PelotonError("--until requires YYYY-MM-DD")
            filters.until = parse_date_arg(argv[i + 1], end_of_day=True)
            i += 2
            continue
        if arg == "--json":
            json_output = True
        else:
            args.append(arg)
        i += 1
    return profile, json_output, filters, args


def parse_date_arg(value: str, *, end_of_day: bool) -> datetime:
    try:
        dt = datetime.strptime(value, "%Y-%m-%d").astimezone()
    except ValueError as exc:
        raise PelotonError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc
    if end_of_day:
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_secrets_path() -> Path:
    explicit = os.environ.get("PELOTON_SECRETS_PATH")
    if explicit:
        return Path(explicit).expanduser()

    profile = os.environ.get("PELOTON_PROFILE")
    filename = f"peloton-{profile}.json" if profile else "peloton.json"
    home = Path.home()
    return home / ".openclaw" / "secrets" / filename


def selected_profile(explicit_profile: str | None) -> str:
    profile = explicit_profile or os.environ.get("PELOTON_PROFILE", "").strip().lower()
    if profile:
        return profile
    return ""


def load_credentials(profile: str) -> dict[str, str]:
    if profile:
        key = env_key_part(profile)
        username = os.environ.get(f"PELOTON_{key}_USERNAME") or os.environ.get(f"PELOTON_{key}")
        password = os.environ.get(f"PELOTON_{key}_PASSWORD")
        if username and password:
            return {"username": username, "password": password}

    username = os.environ.get("PELOTON_USERNAME")
    password = os.environ.get("PELOTON_PASSWORD")
    if username and password:
        return {"username": username, "password": password}

    path = resolve_secrets_path()
    if not path.exists():
        if profile:
            key = env_key_part(profile)
            raise PelotonError(
                f"Missing Peloton credentials for profile '{profile}'. "
                f"Set PELOTON_{key}_USERNAME and PELOTON_{key}_PASSWORD "
                f"or create {path}."
            )
        raise PelotonError(
            "Missing Peloton credentials. Set PELOTON_USERNAME and PELOTON_PASSWORD "
            f"or create {path}, or choose a profile with --profile."
        )

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PelotonError(f"Invalid JSON in secrets file {path}: {exc}") from exc

    if profile:
        profile_data = data.get(profile)
        if not isinstance(profile_data, dict):
            raise PelotonError(
                f"Secrets file {path} must contain a top-level '{profile}' object."
            )
        username = profile_data.get("username")
        password = profile_data.get("password")
    else:
        username = data.get("username")
        password = data.get("password")

    if not username or not password:
        if profile:
            raise PelotonError(
                f"Secrets file {path} must contain {profile}.username and {profile}.password."
            )
        raise PelotonError(
            f"Secrets file {path} must contain username and password for the default profile."
        )

    return {"username": username, "password": password}


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None


class FileCache:
    def __init__(self, namespace: str):
        self.path = Path.home() / ".openclaw" / "cache" / "peloton"
        self.path.mkdir(parents=True, exist_ok=True)
        self.namespace = namespace

    def _file_path(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        return self.path / f"{self.namespace}-{safe}.json"

    def get(self, key: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> Any | None:
        path = self._file_path(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

        cached_at = payload.get("cached_at")
        if not cached_at:
            return None
        age = datetime.now(timezone.utc).timestamp() - float(cached_at)
        if age > ttl_seconds:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        path = self._file_path(key)
        payload = {
            "cached_at": datetime.now(timezone.utc).timestamp(),
            "data": data,
        }
        path.write_text(json.dumps(payload))

    def invalidate_contains(self, text: str) -> None:
        needle = text.lower()
        for path in self.path.glob(f"{self.namespace}-*.json"):
            if needle in path.name.lower():
                path.unlink(missing_ok=True)


class PelotonClient:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.tokens: Tokens | None = None
        self.me_cache: dict[str, Any] | None = None
        self.cache = FileCache(env_key_part(username))
        self.authenticate()

    def authenticate(self) -> None:
        payload = {
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "scope": "offline_access openid",
            "username": self.username,
            "password": self.password,
        }
        response = self._raw_request(
            "POST",
            TOKEN_URL,
            body=payload,
            authorized=False,
            base=None,
        )
        self.tokens = Tokens(
            access_token=response["access_token"],
            refresh_token=response.get("refresh_token"),
            id_token=response.get("id_token"),
        )

    def refresh_access_token(self) -> None:
        if not self.tokens or not self.tokens.refresh_token:
            self.authenticate()
            return

        payload = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": self.tokens.refresh_token,
            "redirect_uri": "https://members.onepeloton.com/callback",
        }
        response = self._raw_request(
            "POST",
            TOKEN_URL,
            body=payload,
            authorized=False,
            base=None,
        )
        self.tokens = Tokens(
            access_token=response["access_token"],
            refresh_token=response.get("refresh_token", self.tokens.refresh_token),
            id_token=response.get("id_token"),
        )

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        base: str | None = API_BASE,
        authorized: bool = True,
        retrying: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if base is None:
            url = path
        else:
            url = f"{base}{path}"

        if params:
            query = urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None},
                doseq=True,
            )
            url = f"{url}?{query}"

        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if authorized:
            if not self.tokens:
                raise PelotonError("Client is not authenticated.")
            headers["Authorization"] = f"Bearer {self.tokens.access_token}"
        if extra_headers:
            headers.update(extra_headers)

        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401 and authorized and not retrying:
                self.refresh_access_token()
                return self._raw_request(
                    method,
                    path,
                    body=body,
                    params=params,
                    base=base,
                    authorized=authorized,
                    retrying=True,
                    extra_headers=extra_headers,
                )
            raise PelotonError(f"Peloton request failed ({exc.code}): {body_text}") from exc
        except urllib.error.URLError as exc:
            raise PelotonError(f"Network error talking to Peloton: {exc}") from exc

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self._raw_request("GET", path, **kwargs)

    def post(self, path: str, body: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._raw_request("POST", path, body=body, **kwargs)

    def me(self) -> dict[str, Any]:
        if self.me_cache is None:
            cache_key = "me"
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.me_cache = cached
            else:
                self.me_cache = self.get("/api/me")
                self.cache.set(cache_key, self.me_cache)
        return self.me_cache

    def settings(self) -> dict[str, Any]:
        me = self.me()
        cache_key = f"settings-{me['id']}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        data = self.get(f"/api/user/{me['id']}/settings")
        self.cache.set(cache_key, data)
        return data

    def workouts(self, limit: int = 10, page: int = 0) -> list[dict[str, Any]]:
        me = self.me()
        cache_key = f"workouts-{me['id']}-{limit}-{page}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        response = self.get(
            f"/api/user/{me['id']}/workouts",
            params={
                "joins": "ride,ride.instructor",
                "limit": limit,
                "page": page,
                "sort_by": "-created",
            },
        )
        data = response.get("data", [])
        self.cache.set(cache_key, data)
        return data

    def latest_workout(self) -> dict[str, Any]:
        workouts = self.workouts(limit=1, page=0)
        if not workouts:
            raise PelotonError("No workouts found for this account.")
        return workouts[0]

    def workout(self, workout_id: str) -> dict[str, Any]:
        cache_key = f"workout-{workout_id}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        data = self.get(
            f"/api/workout/{workout_id}",
            params={"joins": "ride,ride.instructor"},
        )
        self.cache.set(cache_key, data)
        return data

    def ride_details(self, ride_id: str) -> dict[str, Any]:
        cache_key = f"ride-details-{ride_id}"
        cached = self.cache.get(cache_key, ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        data = self.get(f"/api/ride/{ride_id}/details")
        self.cache.set(cache_key, data)
        return data

    def bookmark_class(self, ride_id: str) -> dict[str, Any]:
        data = self.post(
            "/api/favorites/create",
            body={"ride_id": ride_id},
            extra_headers={"Peloton-Platform": "web"},
        )
        self.cache.invalidate_contains("classes-")
        self.cache.invalidate_contains(f"ride-details-{ride_id}")
        return data

    def unbookmark_class(self, ride_id: str) -> dict[str, Any]:
        last_error: PelotonError | None = None
        for attempt in range(3):
            try:
                data = self.post(
                    "/api/favorites/delete",
                    body={"ride_id": ride_id},
                    extra_headers={"Peloton-Platform": "web"},
                )
                self.cache.invalidate_contains("classes-")
                self.cache.invalidate_contains(f"ride-details-{ride_id}")
                return data
            except PelotonError as exc:
                last_error = exc
                if "404" not in str(exc) or attempt == 2:
                    raise
                time.sleep(1.0)
        if last_error:
            raise last_error
        return {}

    def performance_graph(self, workout_id: str, every_n: int = 5) -> dict[str, Any]:
        cache_key = f"performance-{workout_id}-{every_n}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        data = self.get(
            f"/api/workout/{workout_id}/performance_graph",
            params={"every_n": every_n},
        )
        self.cache.set(cache_key, data)
        return data

    def instructors(self) -> list[dict[str, Any]]:
        cache_key = "instructors"
        cached = self.cache.get(cache_key, ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        response = self.get("/api/instructor")
        data = response.get("data", response if isinstance(response, list) else [])
        self.cache.set(cache_key, data)
        return data

    def instructor(self, instructor_id: str) -> dict[str, Any]:
        cache_key = f"instructor-{instructor_id}"
        cached = self.cache.get(cache_key, ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        data = self.get(f"/api/instructor/{instructor_id}")
        self.cache.set(cache_key, data)
        return data

    def classes(self, discipline: str | None = None, limit: int = 10) -> dict[str, Any]:
        cache_key = f"classes-{discipline or 'all'}-{limit}"
        cached = self.cache.get(cache_key, ttl_seconds=60 * 60)
        if cached is not None:
            return cached
        params = {
            "limit": limit,
            "page": 0,
            "browse_category": discipline or "",
            "content_format": "audio,video",
            "sort_by": "original_air_time",
            "desc": "true",
        }
        data = self.get("/api/v2/ride/archived", params=params)
        self.cache.set(cache_key, data)
        return data

    def normalized_workout(
        self,
        workout_id: str,
        *,
        workout: dict[str, Any] | None = None,
        include_metrics: bool = True,
        every_n: int = 5,
    ) -> dict[str, Any]:
        raw_workout = workout or self.workout(workout_id)
        perf = self.performance_graph(workout_id, every_n=every_n) if include_metrics else None
        return normalize_workout(raw_workout, perf)

    def normalized_workouts(
        self,
        *,
        limit: int = 10,
        page: int = 0,
        include_metrics: bool = True,
        every_n: int = 5,
    ) -> list[dict[str, Any]]:
        workouts = self.workouts(limit=limit, page=page)
        return [
            self.normalized_workout(
                workout["id"],
                workout=workout,
                include_metrics=include_metrics,
                every_n=every_n,
            )
            for workout in workouts
        ]


def overall_summary_map(workout: dict[str, Any]) -> dict[str, Any]:
    return workout.get("overall_summary") or {}


def metric_map(perf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        metric["slug"]: metric
        for metric in perf.get("metrics", [])
        if isinstance(metric, dict) and metric.get("slug")
    }


def summary_map(perf: dict[str, Any]) -> dict[str, Any]:
    return {
        item["slug"]: item.get("value")
        for item in perf.get("summaries", [])
        if isinstance(item, dict) and item.get("slug")
    }


def first_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (int, float)):
            return value
        if value != "":
            return value
    return None


def normalize_workout(raw_workout: dict[str, Any], perf: dict[str, Any] | None = None) -> dict[str, Any]:
    ride = raw_workout.get("ride") or {}
    instructor = ride.get("instructor") or {}
    summary = overall_summary_map(raw_workout)
    perf_metrics = metric_map(perf or {})
    perf_summaries = summary_map(perf or {})

    total_work_j = first_value(
        raw_workout.get("total_work"),
        summary.get("total_work"),
        perf_summaries.get("total_output"),
    ) or 0
    calories = first_value(summary.get("calories"), perf_summaries.get("calories")) or 0
    distance = first_value(summary.get("distance"), perf_summaries.get("distance"))

    normalized = {
        "id": raw_workout.get("id"),
        "created_at": first_value(raw_workout.get("created_at"), raw_workout.get("created")),
        "start_time": raw_workout.get("start_time"),
        "end_time": raw_workout.get("end_time"),
        "status": raw_workout.get("status"),
        "discipline": first_value(raw_workout.get("fitness_discipline"), ride.get("fitness_discipline"), "unknown"),
        "title": first_value(ride.get("title"), raw_workout.get("title"), raw_workout.get("name"), "Untitled"),
        "description": ride.get("description"),
        "duration_seconds": first_value(
            ride.get("duration"),
            ride.get("pedaling_duration"),
            max((raw_workout.get("end_time") or 0) - (raw_workout.get("start_time") or 0), 0),
        )
        or 0,
        "instructor": first_value(instructor.get("name"), raw_workout.get("instructor_name"), "Unknown"),
        "device_type": raw_workout.get("device_type"),
        "leaderboard_rank": raw_workout.get("leaderboard_rank"),
        "leaderboard_total": raw_workout.get("total_leaderboard_users"),
        "calories": float(calories),
        "distance": float(distance) if distance is not None else None,
        "output_kj": joules_to_kj(total_work_j),
        "avg_power": first_value(summary.get("avg_power"), perf_metrics.get("output", {}).get("average_value")),
        "max_power": perf_metrics.get("output", {}).get("max_value"),
        "avg_cadence": first_value(summary.get("avg_cadence"), perf_metrics.get("cadence", {}).get("average_value")),
        "max_cadence": perf_metrics.get("cadence", {}).get("max_value"),
        "avg_resistance": first_value(summary.get("avg_resistance"), perf_metrics.get("resistance", {}).get("average_value")),
        "max_resistance": perf_metrics.get("resistance", {}).get("max_value"),
        "avg_speed": first_value(summary.get("avg_speed"), perf_metrics.get("speed", {}).get("average_value")),
        "max_speed": perf_metrics.get("speed", {}).get("max_value"),
        "avg_heart_rate": first_value(summary.get("avg_heart_rate"), perf_metrics.get("heart_rate", {}).get("average_value")),
        "max_heart_rate": perf_metrics.get("heart_rate", {}).get("max_value"),
        "raw_workout": raw_workout,
        "raw_metrics": perf,
    }
    return normalized


def discipline_counts(workouts: list[dict[str, Any]]) -> str:
    counts = Counter(
        workout.get("discipline") or workout.get("fitness_discipline") or "unknown"
        for workout in workouts
    )
    return ", ".join(f"{name}: {count}" for name, count in counts.most_common())


def workouts_in_window(workouts: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now().astimezone() - timedelta(days=days)
    results = []
    for workout in workouts:
        created_at = workout.get("created_at") or workout.get("created")
        if not created_at:
            continue
        dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc).astimezone()
        if dt >= cutoff:
            results.append(workout)
    return results


def workouts_between(
    workouts: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    results = []
    for workout in workouts:
        created_at = workout.get("created_at") or workout.get("created")
        if not created_at:
            continue
        dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc).astimezone()
        if start <= dt < end:
            results.append(workout)
    return results


def apply_filters(workouts: list[dict[str, Any]], filters: QueryFilters) -> list[dict[str, Any]]:
    results = workouts
    if filters.since or filters.until:
        bounded = []
        for workout in results:
            created_at = workout.get("created_at") or workout.get("created")
            if not created_at:
                continue
            dt = datetime.fromtimestamp(int(created_at), tz=timezone.utc).astimezone()
            if filters.since and dt < filters.since:
                continue
            if filters.until and dt > filters.until:
                continue
            bounded.append(workout)
        results = bounded
    if filters.discipline:
        results = [
            workout
            for workout in results
            if (workout.get("discipline") or workout.get("fitness_discipline") or "").lower()
            == filters.discipline
        ]
    if filters.instructor:
        def instructor_name(workout: dict[str, Any]) -> str:
            if "discipline" in workout:
                return (workout.get("instructor") or "").lower()
            ride = workout.get("ride") or {}
            return (
                (ride.get("instructor") or {}).get("name")
                or workout.get("instructor_name")
                or ""
            ).lower()

        results = [
            workout for workout in results if filters.instructor in instructor_name(workout)
        ]
    return results


def filters_label(filters: QueryFilters) -> str | None:
    parts: list[str] = []
    if filters.discipline:
        parts.append(f"discipline={filters.discipline}")
    if filters.instructor:
        parts.append(f"instructor~{filters.instructor}")
    if filters.since:
        parts.append(f"since={filters.since.strftime('%Y-%m-%d')}")
    if filters.until:
        parts.append(f"until={filters.until.strftime('%Y-%m-%d')}")
    if filters.title:
        parts.append(f"title~{filters.title}")
    if filters.class_type:
        parts.append(f"class_type~{filters.class_type}")
    if filters.duration is not None:
        parts.append(f"duration={filters.duration}")
    if filters.min_duration is not None:
        parts.append(f"min_duration={filters.min_duration}")
    if filters.max_duration is not None:
        parts.append(f"max_duration={filters.max_duration}")
    if filters.min_difficulty is not None:
        parts.append(f"min_difficulty={filters.min_difficulty:g}")
    if filters.max_difficulty is not None:
        parts.append(f"max_difficulty={filters.max_difficulty:g}")
    if filters.explicit is not None:
        parts.append(f"explicit={str(filters.explicit).lower()}")
    if filters.captions is not None:
        parts.append(f"captions={str(filters.captions).lower()}")
    if filters.available is not None:
        parts.append(f"available={str(filters.available).lower()}")
    if filters.bookmarked is not None:
        parts.append(f"bookmarked={str(filters.bookmarked).lower()}")
    if filters.song:
        parts.append(f"song~{filters.song}")
    if filters.artist:
        parts.append(f"artist~{filters.artist}")
    if filters.sort:
        parts.append(f"sort={filters.sort}")
    if filters.bookmark is not None:
        parts.append(f"bookmark={str(filters.bookmark).lower()}")
    if filters.playlist is not None:
        parts.append(f"playlist={str(filters.playlist).lower()}")
    return ", ".join(parts) if parts else None


def summarize_window(workouts: list[dict[str, Any]]) -> dict[str, Any]:
    total_seconds = 0
    total_calories = 0.0
    total_output = 0.0

    for workout in workouts:
        if "discipline" in workout:
            total_seconds += int(workout.get("duration_seconds") or 0)
            total_calories += float(workout.get("calories") or 0)
            total_output += float(workout.get("output_kj") or 0)
        else:
            ride = workout.get("ride") or {}
            summary = overall_summary_map(workout)
            total_seconds += int(
                ride.get("duration")
                or max((workout.get("end_time") or 0) - (workout.get("start_time") or 0), 0)
            )
            total_calories += float(summary.get("calories") or 0)
            total_output += joules_to_kj(summary.get("total_work") or workout.get("total_work") or 0)

    return {
        "count": len(workouts),
        "duration_seconds": total_seconds,
        "calories": total_calories,
        "output_kj": total_output,
        "disciplines": discipline_counts(workouts) if workouts else "-",
    }


def summarize_profile_window(
    profile: str,
    workouts: list[dict[str, Any]],
    days: int,
    filters: QueryFilters,
) -> dict[str, Any]:
    filtered = apply_filters(workouts_in_window(workouts, days), filters)
    totals = summarize_window(filtered)
    totals["profile"] = profile
    totals["workouts"] = filtered
    return totals


def render_profile(me: dict[str, Any]) -> str:
    lines = [
        "# Peloton Profile",
        "",
        f"- Name: {me.get('name') or '-'}",
        f"- Username: {me.get('username') or '-'}",
        f"- Location: {me.get('location') or '-'}",
        f"- Subscription status: {me.get('subscription_status') or '-'}",
        f"- Total workouts: {me.get('total_workouts') or 0}",
        f"- Cycling FTP: {me.get('cycling_workout_ftp') or '-'}",
    ]
    return "\n".join(lines)


def render_workouts(workouts: list[dict[str, Any]]) -> str:
    lines = ["# Recent Peloton Workouts", ""]
    if not workouts:
        lines.append("No workouts found.")
        return "\n".join(lines)

    for workout in workouts:
        summary = overall_summary_map(workout)
        if "discipline" in workout:
            lines.append(
                "- "
                f"{timestamp_to_local(workout.get('created_at'))} | "
                f"{workout.get('discipline') or 'unknown'} | "
                f"{truncate(workout.get('title') or 'Untitled', 50)} | "
                f"{workout.get('instructor') or '-'} | "
                f"{format_minutes(workout.get('duration_seconds'))} | "
                f"{format_number(workout.get('calories'))} cal | "
                f"{format_number(workout.get('output_kj'))} kJ"
            )
            continue

        ride = workout.get("ride") or {}
        lines.append(
            "- "
            f"{timestamp_to_local(workout.get('created_at') or workout.get('created'))} | "
            f"{workout.get('fitness_discipline') or 'unknown'} | "
            f"{truncate(ride.get('title') or workout.get('name') or 'Untitled', 50)} | "
            f"{((ride.get('instructor') or {}).get('name') or workout.get('instructor_name') or '-')} | "
            f"{format_minutes(ride.get('duration') or workout.get('end_time', 0) - workout.get('start_time', 0))} | "
            f"{format_number(summary.get('calories'))} cal | "
            f"{format_number(joules_to_kj(summary.get('total_work') or workout.get('total_work')))} kJ"
        )
    return "\n".join(lines)


def render_single_workout(workout: dict[str, Any]) -> str:
    if "discipline" in workout:
        lines = [
            "# Peloton Workout",
            "",
            f"- Title: {workout.get('title') or '-'}",
            f"- Discipline: {workout.get('discipline') or '-'}",
            f"- Instructor: {workout.get('instructor') or '-'}",
            f"- When: {timestamp_to_local(workout.get('created_at'))}",
            f"- Duration: {format_minutes(workout.get('duration_seconds'))}",
            f"- Calories: {format_number(workout.get('calories'))}",
            f"- Output: {format_number(workout.get('output_kj'))} kJ",
            f"- Distance: {format_number(workout.get('distance'), 2)}",
            f"- Avg cadence: {format_number(workout.get('avg_cadence'))} RPM",
            f"- Avg resistance: {format_number(workout.get('avg_resistance'))}%",
            f"- Avg power: {format_number(workout.get('avg_power'))} W",
            f"- Avg speed: {format_number(workout.get('avg_speed'), 1)}",
            f"- Avg heart rate: {format_number(workout.get('avg_heart_rate'))} bpm",
            f"- Rank: {workout.get('leaderboard_rank') or '-'} / {workout.get('leaderboard_total') or '-'}",
        ]
        return "\n".join(lines)

    ride = workout.get("ride") or {}
    instructor = (ride.get("instructor") or {}).get("name") or workout.get("instructor_name") or "-"
    summary = overall_summary_map(workout)
    lines = [
        "# Peloton Workout",
        "",
        f"- Title: {ride.get('title') or workout.get('name') or '-'}",
        f"- Discipline: {workout.get('fitness_discipline') or '-'}",
        f"- Instructor: {instructor}",
        f"- When: {timestamp_to_local(workout.get('created_at') or workout.get('created'))}",
        f"- Duration: {format_minutes(ride.get('duration') or workout.get('end_time', 0) - workout.get('start_time', 0))}",
        f"- Calories: {format_number(summary.get('calories'))}",
        f"- Output: {format_number(joules_to_kj(summary.get('total_work') or workout.get('total_work')))} kJ",
        f"- Avg cadence: {format_number(summary.get('avg_cadence'))} RPM",
        f"- Avg resistance: {format_number(summary.get('avg_resistance'))}%",
        f"- Avg power: {format_number(summary.get('avg_power'))} W",
        f"- Avg speed: {format_number(summary.get('avg_speed'), 1)}",
        f"- Rank: {workout.get('leaderboard_rank') or '-'} / {workout.get('total_leaderboard_users') or '-'}",
    ]
    return "\n".join(lines)


def render_metrics(perf: dict[str, Any]) -> str:
    metrics = metric_map(perf)
    summaries = summary_map(perf)
    lines = [
        "# Peloton Workout Metrics",
        "",
        f"- Output: {format_number(joules_to_kj(summaries.get('total_output')))} kJ",
        f"- Calories: {format_number(summaries.get('calories'))}",
        f"- Distance: {format_number(summaries.get('distance'), 2)}",
        f"- Avg power: {format_number(metrics.get('output', {}).get('average_value'))} W",
        f"- Max power: {format_number(metrics.get('output', {}).get('max_value'))} W",
        f"- Avg cadence: {format_number(metrics.get('cadence', {}).get('average_value'))} RPM",
        f"- Max cadence: {format_number(metrics.get('cadence', {}).get('max_value'))} RPM",
        f"- Avg resistance: {format_number(metrics.get('resistance', {}).get('average_value'))}%",
        f"- Max resistance: {format_number(metrics.get('resistance', {}).get('max_value'))}%",
        f"- Avg heart rate: {format_number(metrics.get('heart_rate', {}).get('average_value'))} bpm",
        f"- Max heart rate: {format_number(metrics.get('heart_rate', {}).get('max_value'))} bpm",
    ]
    return "\n".join(lines)


def render_normalized_metrics(workout: dict[str, Any]) -> str:
    lines = [
        "# Peloton Workout Metrics",
        "",
        f"- Output: {format_number(workout.get('output_kj'))} kJ",
        f"- Calories: {format_number(workout.get('calories'))}",
        f"- Distance: {format_number(workout.get('distance'), 2)}",
        f"- Avg power: {format_number(workout.get('avg_power'))} W",
        f"- Max power: {format_number(workout.get('max_power'))} W",
        f"- Avg cadence: {format_number(workout.get('avg_cadence'))} RPM",
        f"- Max cadence: {format_number(workout.get('max_cadence'))} RPM",
        f"- Avg resistance: {format_number(workout.get('avg_resistance'))}%",
        f"- Max resistance: {format_number(workout.get('max_resistance'))}%",
        f"- Avg heart rate: {format_number(workout.get('avg_heart_rate'))} bpm",
        f"- Max heart rate: {format_number(workout.get('max_heart_rate'))} bpm",
    ]
    return "\n".join(lines)


def render_summary(workouts: list[dict[str, Any]], days: int, filters: QueryFilters | None = None) -> str:
    window = workouts_in_window(workouts, days)
    totals = summarize_window(window)

    lines = [f"# Peloton {days}-Day Summary", ""]
    if not window:
        lines.append("No workouts found in this window.")
        return "\n".join(lines)

    label = filters_label(filters or QueryFilters())
    if label:
        lines.extend([f"- Filters: {label}", ""])

    lines.extend(
        [
            f"- Workouts: {totals['count']}",
            f"- Duration: {format_minutes(totals['duration_seconds'])}",
            f"- Calories: {format_number(totals['calories'])}",
            f"- Output: {format_number(totals['output_kj'])} kJ",
            f"- Disciplines: {totals['disciplines']}",
            "",
            "## Most Recent",
        ]
    )

    for workout in window[:5]:
        if "discipline" in workout:
            lines.append(
                "- "
                f"{timestamp_to_local(workout.get('created_at'))} | "
                f"{workout.get('discipline') or 'unknown'} | "
                f"{truncate(workout.get('title') or 'Untitled', 48)}"
            )
        else:
            ride = workout.get("ride") or {}
            lines.append(
                "- "
                f"{timestamp_to_local(workout.get('created_at') or workout.get('created'))} | "
                f"{workout.get('fitness_discipline') or 'unknown'} | "
                f"{truncate(ride.get('title') or 'Untitled', 48)}"
            )

    return "\n".join(lines)


def render_named_window_summary(
    workouts: list[dict[str, Any]],
    *,
    title: str,
    start: datetime,
    end: datetime,
    filters: QueryFilters | None = None,
) -> str:
    window = workouts_between(workouts, start=start, end=end)
    totals = summarize_window(window)

    lines = [f"# {title}", ""]
    if not window:
        lines.append("No workouts found in this window.")
        return "\n".join(lines)

    label = filters_label(filters or QueryFilters())
    if label:
        lines.extend([f"- Filters: {label}", ""])

    lines.extend(
        [
            f"- Workouts: {totals['count']}",
            f"- Duration: {format_minutes(totals['duration_seconds'])}",
            f"- Calories: {format_number(totals['calories'])}",
            f"- Output: {format_number(totals['output_kj'])} kJ",
            f"- Disciplines: {totals['disciplines']}",
            "",
            "## Workouts",
        ]
    )

    for workout in window[:10]:
        lines.append(
            "- "
            f"{timestamp_to_local(workout.get('created_at'))} | "
            f"{workout.get('discipline') or 'unknown'} | "
            f"{truncate(workout.get('title') or 'Untitled', 48)} | "
            f"{format_number(workout.get('calories'))} cal | "
            f"{format_number(workout.get('output_kj'))} kJ"
        )

    return "\n".join(lines)


def render_compare_summary(
    workouts: list[dict[str, Any]],
    recent_days: int,
    previous_days: int,
    filters: QueryFilters,
) -> str:
    now = datetime.now().astimezone()
    recent_start = now - timedelta(days=recent_days)
    previous_start = recent_start - timedelta(days=previous_days)

    recent = apply_filters(workouts_between(workouts, start=recent_start, end=now), filters)
    previous = apply_filters(
        workouts_between(workouts, start=previous_start, end=recent_start), filters
    )

    recent_totals = summarize_window(recent)
    previous_totals = summarize_window(previous)

    lines = [
        f"# Peloton Compare ({recent_days}d vs previous {previous_days}d)",
        "",
        f"- Recent workouts: {recent_totals['count']}",
        f"- Previous workouts: {previous_totals['count']}",
        f"- Duration: {format_minutes(recent_totals['duration_seconds'])} vs {format_minutes(previous_totals['duration_seconds'])} ({percent_change(recent_totals['duration_seconds'], previous_totals['duration_seconds'])})",
        f"- Calories: {format_number(recent_totals['calories'])} vs {format_number(previous_totals['calories'])} ({percent_change(recent_totals['calories'], previous_totals['calories'])})",
        f"- Output: {format_number(recent_totals['output_kj'])} kJ vs {format_number(previous_totals['output_kj'])} kJ ({percent_change(recent_totals['output_kj'], previous_totals['output_kj'])})",
        f"- Recent disciplines: {recent_totals['disciplines']}",
        f"- Previous disciplines: {previous_totals['disciplines']}",
    ]
    label = filters_label(filters)
    if label:
        lines.insert(2, f"- Filters: {label}")
    return "\n".join(lines)


def render_profile_compare_summary(
    profile_a: str,
    summary_a: dict[str, Any],
    profile_b: str,
    summary_b: dict[str, Any],
    days: int,
    filters: QueryFilters,
) -> str:
    label = filters_label(filters)
    lines = [f"# Peloton Profile Compare ({days}d)", ""]
    if label:
        lines.extend([f"- Filters: {label}", ""])

    lines.extend(
        [
            f"- {profile_a}: {summary_a['count']} workouts | {format_minutes(summary_a['duration_seconds'])} | {format_number(summary_a['calories'])} cal | {format_number(summary_a['output_kj'])} kJ",
            f"- {profile_b}: {summary_b['count']} workouts | {format_minutes(summary_b['duration_seconds'])} | {format_number(summary_b['calories'])} cal | {format_number(summary_b['output_kj'])} kJ",
            "",
            "## Delta",
            f"- Workouts: {summary_a['count'] - summary_b['count']:+d}",
            f"- Duration: {format_minutes(summary_a['duration_seconds'])} vs {format_minutes(summary_b['duration_seconds'])}",
            f"- Calories: {format_number(summary_a['calories'])} vs {format_number(summary_b['calories'])}",
            f"- Output: {format_number(summary_a['output_kj'])} kJ vs {format_number(summary_b['output_kj'])} kJ",
            f"- {profile_a} disciplines: {summary_a['disciplines']}",
            f"- {profile_b} disciplines: {summary_b['disciplines']}",
        ]
    )

    def recent_line(summary: dict[str, Any]) -> str:
        workouts = summary.get("workouts") or []
        if not workouts:
            return "No workouts"
        latest = workouts[0]
        return (
            f"{timestamp_to_local(latest.get('created_at'))} | "
            f"{latest.get('discipline') or 'unknown'} | "
            f"{truncate(latest.get('title') or 'Untitled', 40)}"
        )

    lines.extend(
        [
            "",
            "## Most Recent",
            f"- {profile_a}: {recent_line(summary_a)}",
            f"- {profile_b}: {recent_line(summary_b)}",
        ]
    )
    return "\n".join(lines)

def playlist_preview_lines(
    client: PelotonClient | None,
    ride_id: str | None,
    *,
    max_songs: int = 3,
) -> list[str]:
    if client is None or not ride_id:
        return []
    details = client.ride_details(ride_id)
    songs = ((details.get("playlist") or {}).get("songs")) or []
    lines: list[str] = []
    for song in songs[:max_songs]:
        title = song.get("title") or "Unknown"
        artists = ", ".join(
            artist.get("artist_name")
            for artist in (song.get("artists") or [])
            if artist.get("artist_name")
        )
        lines.append(f"   Playlist: {title}" + (f" - {artists}" if artists else ""))
    return lines


def render_classes(
    response: dict[str, Any],
    discipline: str | None,
    *,
    client: PelotonClient | None = None,
    filters: QueryFilters | None = None,
) -> str:
    rides = response.get("data", [])
    lines = [f"# Peloton Classes{f' ({discipline})' if discipline else ''}", ""]
    if not rides:
        lines.append("No classes returned.")
        return "\n".join(lines)

    instructors = {
        instructor.get("id"): instructor.get("name")
        for instructor in response.get("instructors", [])
        if isinstance(instructor, dict)
    }

    for ride in rides:
        instructor_name = instructors.get(ride.get("instructor_id")) or ((ride.get("instructor") or {}).get("name")) or "-"
        lines.append(
            "- "
            f"{timestamp_to_local(ride.get('original_air_time') or ride.get('scheduled_start_time'))} | "
            f"{truncate(ride.get('title') or 'Untitled', 48)} | "
            f"{instructor_name} | "
            f"{format_minutes(ride.get('duration'))}"
        )
        if filters and (filters.playlist or filters.song or filters.artist):
            lines.extend(playlist_preview_lines(client, ride.get("id")))
    return "\n".join(lines)


def filter_classes(response: dict[str, Any], filters: QueryFilters, client: PelotonClient | None = None) -> dict[str, Any]:
    instructors = {
        instructor.get("id"): instructor.get("name")
        for instructor in response.get("instructors", [])
        if isinstance(instructor, dict)
    }
    type_lookup: dict[str, str] = {}
    for item in response.get("class_types", []) + response.get("ride_types", []):
        if not isinstance(item, dict):
            continue
        name = (
            item.get("standalone_display_name")
            or item.get("display_name")
            or item.get("name")
            or ""
        )
        item_id = item.get("id")
        if item_id and name:
            type_lookup[item_id] = name.lower()

    filtered = []
    for ride in response.get("data", []):
        name = instructors.get(ride.get("instructor_id")) or ((ride.get("instructor") or {}).get("name")) or ""
        title = (ride.get("title") or "").lower()
        duration_minutes = int((ride.get("duration") or 0) / 60)
        difficulty = ride.get("difficulty_estimate")
        class_type_names = [
            type_lookup.get(type_id, "")
            for type_id in (ride.get("class_type_ids") or ride.get("ride_type_ids") or [])
        ]
        playlist_titles: list[str] = []
        playlist_artists: list[str] = []

        if (filters.song or filters.artist) and client is not None:
            details = client.ride_details(ride.get("id"))
            songs = ((details.get("playlist") or {}).get("songs")) or []
            for song in songs:
                if song.get("title"):
                    playlist_titles.append(song["title"].lower())
                for artist in song.get("artists") or []:
                    name_value = artist.get("artist_name")
                    if name_value:
                        playlist_artists.append(name_value.lower())

        if filters.instructor and filters.instructor not in name.lower():
            continue
        if filters.title and filters.title not in title:
            continue
        if filters.class_type and not (
            any(filters.class_type in item for item in class_type_names if item)
            or filters.class_type in title
        ):
            continue
        if filters.duration is not None and duration_minutes != filters.duration:
            continue
        if filters.min_duration is not None and duration_minutes < filters.min_duration:
            continue
        if filters.max_duration is not None and duration_minutes > filters.max_duration:
            continue
        if filters.min_difficulty is not None and (difficulty is None or float(difficulty) < filters.min_difficulty):
            continue
        if filters.max_difficulty is not None and (difficulty is None or float(difficulty) > filters.max_difficulty):
            continue
        if filters.explicit is not None and bool(ride.get("is_explicit")) != filters.explicit:
            continue
        if filters.captions is not None and bool(ride.get("has_closed_captions")) != filters.captions:
            continue
        if filters.available is not None and bool((ride.get("availability") or {}).get("is_available")) != filters.available:
            continue
        if filters.bookmarked is not None and bool(ride.get("is_favorite")) != filters.bookmarked:
            continue
        if filters.song and not any(filters.song in item for item in playlist_titles):
            continue
        if filters.artist and not any(filters.artist in item for item in playlist_artists):
            continue
        filtered.append(ride)

    sort_key = (filters.sort or "").lower()
    if sort_key:
        reverse = True
        if sort_key in {"new", "recent", "latest", "original_air_time", "scheduled_start_time"}:
            filtered.sort(key=lambda ride: (ride.get("original_air_time") or ride.get("scheduled_start_time") or 0), reverse=True)
        elif sort_key in {"oldest", "earliest"}:
            filtered.sort(key=lambda ride: (ride.get("original_air_time") or ride.get("scheduled_start_time") or 0))
        elif sort_key in {"difficulty", "hardest"}:
            filtered.sort(key=lambda ride: float(ride.get("difficulty_estimate") or 0), reverse=True)
        elif sort_key in {"easiest"}:
            filtered.sort(key=lambda ride: float(ride.get("difficulty_estimate") or 0))
        elif sort_key in {"duration", "longest"}:
            filtered.sort(key=lambda ride: int(ride.get("duration") or 0), reverse=True)
        elif sort_key in {"shortest"}:
            filtered.sort(key=lambda ride: int(ride.get("duration") or 0))
        elif sort_key in {"popular", "popularity"}:
            filtered.sort(key=lambda ride: int(ride.get("total_workouts") or ride.get("total_ratings") or 0), reverse=True)
        elif sort_key in {"rating", "best"}:
            filtered.sort(key=lambda ride: float(ride.get("overall_rating_avg") or 0), reverse=True)
        else:
            reverse = False
            if sort_key in {"title", "name"}:
                filtered.sort(key=lambda ride: (ride.get("title") or "").lower())

    updated = dict(response)
    updated["data"] = filtered
    return updated


def score_class_for_recommendation(ride: dict[str, Any], filters: QueryFilters) -> float:
    score = 0.0
    score += float(ride.get("overall_rating_avg") or 0) * 15
    score += min(math.log10((ride.get("total_workouts") or 0) + 1), 4.0) * 6
    score += min(math.log10((ride.get("total_ratings") or 0) + 1), 4.0) * 4
    score += float(ride.get("difficulty_estimate") or 0)
    score += (ride.get("original_air_time") or ride.get("scheduled_start_time") or 0) / 10_000_000_000

    duration_minutes = int((ride.get("duration") or 0) / 60)
    if filters.duration is not None:
        score -= abs(duration_minutes - filters.duration) * 4
    elif filters.min_duration is not None and duration_minutes < filters.min_duration:
        score -= 10
    elif filters.max_duration is not None and duration_minutes > filters.max_duration:
        score -= 10

    if filters.explicit is False and not ride.get("is_explicit"):
        score += 2
    if filters.captions is True and ride.get("has_closed_captions"):
        score += 2
    if (ride.get("availability") or {}).get("is_available"):
        score += 3

    return score


def recommend_classes(response: dict[str, Any], filters: QueryFilters, limit: int) -> list[dict[str, Any]]:
    rides = list(response.get("data", []))
    rides.sort(key=lambda ride: score_class_for_recommendation(ride, filters), reverse=True)
    return rides[:limit]


def render_recommendations(
    response: dict[str, Any],
    discipline: str | None,
    filters: QueryFilters,
    limit: int,
    *,
    client: PelotonClient | None = None,
) -> str:
    rides = recommend_classes(response, filters, limit)
    lines = [f"# Peloton Recommendations{f' ({discipline})' if discipline else ''}", ""]
    label = filters_label(filters)
    if label:
        lines.extend([f"- Filters: {label}", ""])

    if not rides:
        lines.append("No matching classes found.")
        return "\n".join(lines)

    instructors = {
        instructor.get("id"): instructor.get("name")
        for instructor in response.get("instructors", [])
        if isinstance(instructor, dict)
    }

    for idx, ride in enumerate(rides, start=1):
        instructor_name = instructors.get(ride.get("instructor_id")) or ((ride.get("instructor") or {}).get("name")) or "-"
        duration_minutes = int((ride.get("duration") or 0) / 60)
        reasons: list[str] = []
        if ride.get("overall_rating_avg"):
            reasons.append(f"rating {float(ride['overall_rating_avg']):.2f}")
        if ride.get("total_workouts"):
            reasons.append(f"{int(ride['total_workouts'])} taken")
        if ride.get("difficulty_estimate"):
            reasons.append(f"difficulty {float(ride['difficulty_estimate']):.1f}")
        if ride.get("has_closed_captions"):
            reasons.append("captions")
        if ride.get("is_explicit"):
            reasons.append("explicit")

        lines.append(
            f"{idx}. {ride.get('title') or 'Untitled'} | {instructor_name} | "
            f"{duration_minutes}m | {timestamp_to_local(ride.get('original_air_time') or ride.get('scheduled_start_time'))}"
        )
        if reasons:
            lines.append(f"   Why: {', '.join(reasons[:4])}")
        if filters.playlist or filters.song or filters.artist:
            lines.extend(playlist_preview_lines(client, ride.get("id")))

    if filters.bookmark:
        lines.extend(["", "- Recommended classes were bookmarked."])

    return "\n".join(lines)


def render_bookmark_result(action: str, ride_id: str) -> str:
    title = "Bookmarked Class" if action == "bookmark" else "Removed Bookmark"
    return "\n".join([f"# {title}", "", f"- Ride ID: {ride_id}"])


def render_instructors(instructors: list[dict[str, Any]]) -> str:
    lines = ["# Peloton Instructors", ""]
    if not instructors:
        lines.append("No instructors returned.")
        return "\n".join(lines)

    sorted_instructors = sorted(instructors, key=lambda item: (item.get("name") or "").lower())
    for instructor in sorted_instructors:
        lines.append(
            "- "
            f"{instructor.get('name') or '-'} | "
            f"{instructor.get('fitness_disciplines') or instructor.get('quote') or '-'} | "
            f"{instructor.get('id') or '-'}"
        )
    return "\n".join(lines)


def render_instructor(instructor: dict[str, Any]) -> str:
    disciplines = instructor.get("fitness_disciplines") or []
    if isinstance(disciplines, list):
        disciplines_text = ", ".join(disciplines) if disciplines else "-"
    else:
        disciplines_text = str(disciplines)

    lines = [
        "# Peloton Instructor",
        "",
        f"- Name: {instructor.get('name') or '-'}",
        f"- Disciplines: {disciplines_text}",
        f"- Bio: {instructor.get('bio') or '-'}",
        f"- Quote: {instructor.get('quote') or '-'}",
        f"- Instagram: {instructor.get('instagram_handle') or '-'}",
        f"- Twitter: {instructor.get('twitter_handle') or '-'}",
    ]
    return "\n".join(lines)


def usage() -> str:
    return """Usage: python3 scripts/peloton.py [--profile <name>] [--discipline <name>] [--instructor <name>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--title <text>] [--class-type <text>] [--duration <minutes>] [--min-duration <minutes>] [--max-duration <minutes>] [--min-difficulty <n>] [--max-difficulty <n>] [--explicit true|false] [--captions true|false] [--available true|false] [--bookmarked true|false] [--song <text>] [--artist <text>] [--sort <name>] [--bookmark true|false] [--playlist true|false] <command> [args] [--json]

Commands:
  --profile <name>
  --discipline <name>
  --instructor <name>
  --since YYYY-MM-DD
  --until YYYY-MM-DD
  --title <text>
  --class-type <text>
  --duration <minutes>
  --min-duration <minutes>
  --max-duration <minutes>
  --min-difficulty <n>
  --max-difficulty <n>
  --explicit true|false
  --captions true|false
  --available true|false
  --bookmarked true|false
  --song <text>
  --artist <text>
  --sort <name>
  --bookmark true|false
  --playlist true|false
  me
  settings
  today
  yesterday
  month
  workouts [limit]
  latest
  workout <workout_id>
  metrics <workout_id> [every_n]
  summary [days]
  weekly
  compare [recent_days] [previous_days]
  compare-profiles <profile_a> <profile_b> [days]
  classes [discipline] [limit]
  recommend [discipline] [limit]
  bookmark-class <ride_id>
  unbookmark-class <ride_id>
  instructors
  instructor <instructor_id>
"""


def main(argv: list[str]) -> int:
    profile_arg, json_output, filters, args = parse_args(argv)
    if not args:
        print(usage().strip())
        return 1

    command, *rest = args

    try:
        if command == "compare-profiles":
            if len(rest) < 2:
                raise PelotonError("compare-profiles requires <profile_a> <profile_b> [days]")
            profile_a = rest[0].strip().lower()
            profile_b = rest[1].strip().lower()
            days = int(rest[2]) if len(rest) > 2 else 7

            creds_a = load_credentials(profile_a)
            creds_b = load_credentials(profile_b)
            client_a = PelotonClient(creds_a["username"], creds_a["password"])
            client_b = PelotonClient(creds_b["username"], creds_b["password"])

            workouts_a = client_a.normalized_workouts(limit=50, include_metrics=True)
            workouts_b = client_b.normalized_workouts(limit=50, include_metrics=True)
            summary_a = summarize_profile_window(profile_a, workouts_a, days, filters)
            summary_b = summarize_profile_window(profile_b, workouts_b, days, filters)

            print(
                render_profile_compare_summary(profile_a, summary_a, profile_b, summary_b, days, filters)
                if not json_output
                else json.dumps(
                    {
                        "profile_a": summary_a,
                        "profile_b": summary_b,
                        "days": days,
                    },
                    indent=2,
                )
            )
            return 0

        profile = selected_profile(profile_arg)
        creds = load_credentials(profile)
        client = PelotonClient(creds["username"], creds["password"])

        if command == "me":
            data = client.me()
            print(json.dumps(data, indent=2) if json_output else render_profile(data))
            return 0

        if command == "settings":
            data = client.settings()
            print(json.dumps(data, indent=2) if json_output else json.dumps(data, indent=2))
            return 0

        if command == "workouts":
            limit = int(rest[0]) if rest else 10
            data = client.normalized_workouts(limit=limit, include_metrics=True)
            data = apply_filters(data, filters)
            print(json.dumps(data, indent=2) if json_output else render_workouts(data))
            return 0

        if command == "latest":
            latest = client.latest_workout()
            data = client.normalized_workout(latest["id"], workout=latest, include_metrics=True)
            print(json.dumps(data, indent=2) if json_output else render_single_workout(data))
            return 0

        if command == "workout":
            if not rest:
                raise PelotonError("workout requires <workout_id>")
            data = client.normalized_workout(rest[0], include_metrics=True)
            print(json.dumps(data, indent=2) if json_output else render_single_workout(data))
            return 0

        if command == "metrics":
            if not rest:
                raise PelotonError("metrics requires <workout_id>")
            every_n = int(rest[1]) if len(rest) > 1 else 5
            data = client.normalized_workout(rest[0], include_metrics=True, every_n=every_n)
            print(json.dumps(data, indent=2) if json_output else render_normalized_metrics(data))
            return 0

        if command == "summary":
            days = int(rest[0]) if rest else 7
            workouts = client.normalized_workouts(limit=25, include_metrics=True)
            filtered = apply_filters(workouts_in_window(workouts, days), filters)
            print(
                render_summary(filtered, days, filters) if not json_output else json.dumps(filtered, indent=2)
            )
            return 0

        if command == "weekly":
            workouts = client.normalized_workouts(limit=25, include_metrics=True)
            filtered = apply_filters(workouts_in_window(workouts, 7), filters)
            print(
                render_summary(filtered, 7, filters) if not json_output else json.dumps(filtered, indent=2)
            )
            return 0

        if command == "today":
            workouts = client.normalized_workouts(limit=25, include_metrics=True)
            now = datetime.now().astimezone()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window = apply_filters(workouts_between(workouts, start=start, end=now), filters)
            print(
                render_named_window_summary(window, title="Peloton Today", start=start, end=now, filters=filters)
                if not json_output
                else json.dumps(window, indent=2)
            )
            return 0

        if command == "yesterday":
            workouts = client.normalized_workouts(limit=25, include_metrics=True)
            now = datetime.now().astimezone()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = today_start - timedelta(days=1)
            end = today_start
            window = apply_filters(workouts_between(workouts, start=start, end=end), filters)
            print(
                render_named_window_summary(window, title="Peloton Yesterday", start=start, end=end, filters=filters)
                if not json_output
                else json.dumps(window, indent=2)
            )
            return 0

        if command == "month":
            workouts = client.normalized_workouts(limit=50, include_metrics=True)
            now = datetime.now().astimezone()
            start = now - timedelta(days=30)
            window = apply_filters(workouts_between(workouts, start=start, end=now), filters)
            print(
                render_named_window_summary(window, title="Peloton Last 30 Days", start=start, end=now, filters=filters)
                if not json_output
                else json.dumps(window, indent=2)
            )
            return 0

        if command == "compare":
            recent_days = int(rest[0]) if rest else 7
            previous_days = int(rest[1]) if len(rest) > 1 else recent_days
            workouts = client.normalized_workouts(limit=50, include_metrics=True)
            print(
                render_compare_summary(workouts, recent_days, previous_days, filters)
                if not json_output
                else json.dumps({"recent_days": recent_days, "previous_days": previous_days}, indent=2)
            )
            return 0

        if command == "classes":
            discipline = rest[0] if rest else filters.discipline
            limit = int(rest[1]) if len(rest) > 1 else 10
            data = client.classes(discipline=discipline, limit=limit)
            data = filter_classes(data, filters, client=client)
            print(
                json.dumps(data, indent=2)
                if json_output
                else render_classes(data, discipline, client=client, filters=filters)
            )
            return 0

        if command == "recommend":
            discipline = rest[0] if rest else filters.discipline
            limit = int(rest[1]) if len(rest) > 1 else 5
            pool_size = max(limit * 6, 30)
            data = client.classes(discipline=discipline, limit=pool_size)
            data = filter_classes(data, filters, client=client)
            recommendations = recommend_classes(data, filters, limit)
            if filters.bookmark:
                for ride in recommendations:
                    client.bookmark_class(ride.get("id"))
            print(
                json.dumps(recommendations, indent=2)
                if json_output
                else render_recommendations(data, discipline, filters, limit, client=client)
            )
            return 0

        if command == "bookmark-class":
            if not rest:
                raise PelotonError("bookmark-class requires <ride_id>")
            ride_id = rest[0]
            data = client.bookmark_class(ride_id)
            print(json.dumps(data, indent=2) if json_output else render_bookmark_result("bookmark", ride_id))
            return 0

        if command == "unbookmark-class":
            if not rest:
                raise PelotonError("unbookmark-class requires <ride_id>")
            ride_id = rest[0]
            data = client.unbookmark_class(ride_id)
            print(json.dumps(data, indent=2) if json_output else render_bookmark_result("unbookmark", ride_id))
            return 0

        if command == "instructors":
            data = client.instructors()
            print(json.dumps(data, indent=2) if json_output else render_instructors(data))
            return 0

        if command == "instructor":
            if not rest:
                raise PelotonError("instructor requires <instructor_id>")
            data = client.instructor(rest[0])
            print(json.dumps(data, indent=2) if json_output else render_instructor(data))
            return 0

        raise PelotonError(f"Unknown command: {command}")

    except PelotonError as exc:
        eprint(f"Error: {exc}")
        return 1
    except ValueError as exc:
        eprint(f"Error: invalid numeric argument ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
