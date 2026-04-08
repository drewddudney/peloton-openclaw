from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .cache import CACHE_TTL_SECONDS, FileCache
from .common import PelotonError, env_key_part
from .normalize import normalize_workout

API_BASE = "https://api.onepeloton.com"
AUTH_BASE = "https://auth.onepeloton.com"
TOKEN_URL = f"{AUTH_BASE}/oauth/token"
CLIENT_ID = "mgsmWCD0A8Qn6uz6mmqI6qeBNHH9IPwS"
DEFAULT_TIMEOUT = 20


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None


class PelotonClient:
    def __init__(
        self,
        username: str,
        password: str,
        *,
        refresh_cache: bool = False,
        min_request_interval: float = 0.35,
    ):
        self.username = username
        self.password = password
        self.refresh_cache = refresh_cache
        self.min_request_interval = min_request_interval
        self._last_network_at = 0.0
        self.tokens: Tokens | None = None
        self.me_cache: dict[str, Any] | None = None
        self.cache = FileCache(env_key_part(username))
        self.authenticate()

    def _sleep_if_needed(self) -> None:
        if self.min_request_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_network_at
        remaining = self.min_request_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _cache_get(self, key: str, *, ttl_seconds: int = CACHE_TTL_SECONDS) -> Any | None:
        if self.refresh_cache:
            return None
        return self.cache.get(key, ttl_seconds=ttl_seconds)

    def authenticate(self) -> None:
        payload = {
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "scope": "offline_access openid",
            "username": self.username,
            "password": self.password,
        }
        response = self._raw_request("POST", TOKEN_URL, body=payload, authorized=False, base=None)
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
        response = self._raw_request("POST", TOKEN_URL, body=payload, authorized=False, base=None)
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
        url = path if base is None else f"{base}{path}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
            url = f"{url}?{query}"

        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if authorized:
            if not self.tokens:
                raise PelotonError("Client is not authenticated.")
            headers["Authorization"] = f"Bearer {self.tokens.access_token}"
        if extra_headers:
            headers.update(extra_headers)

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        self._sleep_if_needed()
        try:
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                self._last_network_at = time.monotonic()
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            self._last_network_at = time.monotonic()
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
            cached = self._cache_get("me")
            if cached is not None:
                self.me_cache = cached
            else:
                self.me_cache = self.get("/api/me")
                self.cache.set("me", self.me_cache)
        return self.me_cache

    def settings(self) -> dict[str, Any]:
        me = self.me()
        cache_key = f"settings-{me['id']}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self.get(f"/api/user/{me['id']}/settings")
        self.cache.set(cache_key, data)
        return data

    def workouts(self, limit: int = 10, page: int = 0) -> list[dict[str, Any]]:
        me = self.me()
        cache_key = f"workouts-{me['id']}-{limit}-{page}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        response = self.get(
            f"/api/user/{me['id']}/workouts",
            params={"joins": "ride,ride.instructor", "limit": limit, "page": page, "sort_by": "-created"},
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
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self.get(f"/api/workout/{workout_id}", params={"joins": "ride,ride.instructor"})
        self.cache.set(cache_key, data)
        return data

    def ride_details(self, ride_id: str) -> dict[str, Any]:
        cache_key = f"ride-details-{ride_id}"
        cached = self._cache_get(cache_key, ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        data = self.get(f"/api/ride/{ride_id}/details")
        self.cache.set(cache_key, data)
        return data

    def bookmark_class(self, ride_id: str) -> dict[str, Any]:
        data = self.post("/api/favorites/create", body={"ride_id": ride_id}, extra_headers={"Peloton-Platform": "web"})
        self.cache.invalidate_contains("classes-")
        self.cache.invalidate_contains(f"ride-details-{ride_id}")
        return data

    def unbookmark_class(self, ride_id: str) -> dict[str, Any]:
        last_error: PelotonError | None = None
        for attempt in range(3):
            try:
                data = self.post("/api/favorites/delete", body={"ride_id": ride_id}, extra_headers={"Peloton-Platform": "web"})
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
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        data = self.get(f"/api/workout/{workout_id}/performance_graph", params={"every_n": every_n})
        self.cache.set(cache_key, data)
        return data

    def instructors(self) -> list[dict[str, Any]]:
        cached = self._cache_get("instructors", ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        response = self.get("/api/instructor")
        data = response.get("data", response if isinstance(response, list) else [])
        self.cache.set("instructors", data)
        return data

    def instructor(self, instructor_id: str) -> dict[str, Any]:
        cache_key = f"instructor-{instructor_id}"
        cached = self._cache_get(cache_key, ttl_seconds=24 * 60 * 60)
        if cached is not None:
            return cached
        data = self.get(f"/api/instructor/{instructor_id}")
        self.cache.set(cache_key, data)
        return data

    def classes(self, discipline: str | None = None, limit: int = 10) -> dict[str, Any]:
        cache_key = f"classes-{discipline or 'all'}-{limit}"
        cached = self._cache_get(cache_key, ttl_seconds=60 * 60)
        if cached is not None:
            return cached
        data = self.get(
            "/api/v2/ride/archived",
            params={
                "limit": limit,
                "page": 0,
                "browse_category": discipline or "",
                "content_format": "audio,video",
                "sort_by": "original_air_time",
                "desc": "true",
            },
        )
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
        include_metrics: bool = False,
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
