from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .common import PelotonError, QueryFilters, env_key_part, parse_bool_arg


def parse_args(argv: list[str]) -> tuple[str | None, bool, bool, bool, QueryFilters, list[str]]:
    profile = None
    json_output = False
    refresh = False
    full_metrics = False
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
        if arg == "--refresh":
            refresh = True
            i += 1
            continue
        if arg == "--full-metrics":
            full_metrics = True
            i += 1
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
    return profile, json_output, refresh, full_metrics, filters, args


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

    base = Path.home() / ".openclaw" / "secrets"
    profile = os.environ.get("PELOTON_PROFILE")
    if profile:
        profile_path = base / f"peloton-{profile}.json"
        if profile_path.exists():
            return profile_path
    return base / "peloton.json"


def selected_profile(explicit_profile: str | None) -> str:
    profile = explicit_profile or os.environ.get("PELOTON_PROFILE", "").strip().lower()
    return profile or ""


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

    available_profiles = [
        key for key, value in data.items()
        if isinstance(key, str) and isinstance(value, dict) and value.get("username") and value.get("password")
    ]

    if profile:
        profile_data = data.get(profile)
        if not isinstance(profile_data, dict):
            suffix = ""
            if available_profiles:
                suffix = f" Available profiles: {', '.join(sorted(available_profiles))}."
            raise PelotonError(
                f"Secrets file {path} must contain a top-level '{profile}' object."
                f"{suffix} Use --profile <name> or set PELOTON_PROFILE=<name>."
            )
        username = profile_data.get("username")
        password = profile_data.get("password")
    else:
        username = data.get("username")
        password = data.get("password")
        if (not username or not password) and available_profiles:
            fallback_profile = None
            for candidate in ("primary", "default"):
                if candidate in available_profiles:
                    fallback_profile = candidate
                    break
            if fallback_profile is None and len(available_profiles) == 1:
                fallback_profile = available_profiles[0]
            if fallback_profile:
                profile_data = data.get(fallback_profile) or {}
                username = profile_data.get("username")
                password = profile_data.get("password")

    if not username or not password:
        if profile:
            raise PelotonError(f"Secrets file {path} must contain {profile}.username and {profile}.password.")
        if available_profiles:
            raise PelotonError(
                f"Secrets file {path} does not contain username/password for the default profile. "
                f"Available profiles: {', '.join(sorted(available_profiles))}. "
                f"Use --profile <name> or set PELOTON_PROFILE=<name>."
            )
        raise PelotonError(
            f"Secrets file {path} must contain username and password for the default profile."
        )

    return {"username": username, "password": password}
