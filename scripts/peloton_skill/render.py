from __future__ import annotations

from datetime import timedelta
import math
from typing import Any

from .client import PelotonClient
from .common import QueryFilters, format_minutes, format_number, joules_to_kj, percent_change, timestamp_to_local, truncate
from .normalize import (
    apply_filters,
    discipline_counts,
    leaderboard_percentile,
    leaderboard_top_percent,
    leaderboard_trend_buckets,
    overall_summary_map,
    summarize_leaderboard,
    summarize_profile_window,
    summarize_window,
    workouts_between,
    workouts_in_window,
)


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


def render_profile(me: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Peloton Profile",
            "",
            f"- Name: {me.get('name') or '-'}",
            f"- Username: {me.get('username') or '-'}",
            f"- Location: {me.get('location') or '-'}",
            f"- Subscription status: {me.get('subscription_status') or '-'}",
            f"- Total workouts: {me.get('total_workouts') or 0}",
            f"- Cycling FTP: {me.get('cycling_workout_ftp') or '-'}",
        ]
    )


def render_workouts(workouts: list[dict[str, Any]]) -> str:
    lines = ["# Recent Peloton Workouts", ""]
    if not workouts:
        lines.append("No workouts found.")
        return "\n".join(lines)
    for workout in workouts:
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
    return "\n".join(lines)


def render_single_workout(workout: dict[str, Any]) -> str:
    rank = workout.get("leaderboard_rank")
    total = workout.get("leaderboard_total")
    percentile = leaderboard_percentile(rank, total)
    top_percent = leaderboard_top_percent(rank, total)
    return "\n".join(
        [
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
            f"- Beat: {format_number(percentile, 1)}% of riders" if percentile is not None else "- Beat: -",
            f"- Finish: top {format_number(top_percent, 1)}%" if top_percent is not None else "- Finish: -",
        ]
    )


def render_normalized_metrics(workout: dict[str, Any]) -> str:
    return "\n".join(
        [
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
    )


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
        lines.append(
            "- "
            f"{timestamp_to_local(workout.get('created_at'))} | "
            f"{workout.get('discipline') or 'unknown'} | "
            f"{truncate(workout.get('title') or 'Untitled', 48)}"
        )
    return "\n".join(lines)


def render_named_window_summary(workouts: list[dict[str, Any]], *, title: str, filters: QueryFilters | None = None) -> str:
    totals = summarize_window(workouts)
    lines = [f"# {title}", ""]
    if not workouts:
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
    for workout in workouts[:10]:
        lines.append(
            "- "
            f"{timestamp_to_local(workout.get('created_at'))} | "
            f"{workout.get('discipline') or 'unknown'} | "
            f"{truncate(workout.get('title') or 'Untitled', 48)} | "
            f"{format_number(workout.get('calories'))} cal | "
            f"{format_number(workout.get('output_kj'))} kJ"
        )
    return "\n".join(lines)


def render_compare_summary(workouts: list[dict[str, Any]], recent_days: int, previous_days: int, filters: QueryFilters) -> str:
    from datetime import datetime, timedelta

    now = datetime.now().astimezone()
    recent_start = now - timedelta(days=recent_days)
    previous_start = recent_start - timedelta(days=previous_days)
    recent = apply_filters(workouts_between(workouts, start=recent_start, end=now), filters)
    previous = apply_filters(workouts_between(workouts, start=previous_start, end=recent_start), filters)
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


def render_leaderboard(workout: dict[str, Any]) -> str:
    rank = workout.get("leaderboard_rank")
    total = workout.get("leaderboard_total")
    percentile = leaderboard_percentile(rank, total)
    top_percent = leaderboard_top_percent(rank, total)
    return "\n".join(
        [
            "# Peloton Leaderboard",
            "",
            f"- Title: {workout.get('title') or '-'}",
            f"- Discipline: {workout.get('discipline') or '-'}",
            f"- Instructor: {workout.get('instructor') or '-'}",
            f"- When: {timestamp_to_local(workout.get('created_at'))}",
            f"- Rank: {rank or '-'} / {total or '-'}",
            f"- Beat: {format_number(percentile, 1)}% of riders" if percentile is not None else "- Beat: -",
            f"- Finish: top {format_number(top_percent, 1)}%" if top_percent is not None else "- Finish: -",
            f"- Output: {format_number(workout.get('output_kj'))} kJ",
            f"- Calories: {format_number(workout.get('calories'))}",
        ]
    )


def render_leaderboard_summary(workouts: list[dict[str, Any]], days: int, filters: QueryFilters | None = None) -> str:
    window = workouts_in_window(workouts, days)
    totals = summarize_leaderboard(window)
    lines = [f"# Peloton Leaderboard Summary ({days}d)", ""]
    if not window:
        lines.append("No workouts found in this window.")
        return "\n".join(lines)
    label = filters_label(filters or QueryFilters())
    if label:
        lines.extend([f"- Filters: {label}", ""])
    lines.extend(
        [
            f"- Workouts: {totals['count']}",
            f"- Ranked workouts: {totals['ranked_count']}",
        ]
    )
    if totals["ranked_count"] <= 0:
        lines.append("- No leaderboard data found in this window.")
        return "\n".join(lines)

    best_workout = (totals.get("ranked_workouts") or [{}])[0]
    best_top_percent = best_workout.get("leaderboard_top_percent")
    lines.extend(
        [
            f"- Best rank: #{int(totals['best_rank'])}" if totals["best_rank"] is not None else "- Best rank: -",
            f"- Best finish: top {format_number(best_top_percent, 1)}%" if best_top_percent is not None else "- Best finish: -",
            f"- Median beat rate: {format_number(totals['median_percentile'], 1)}%",
            f"- Average beat rate: {format_number(totals['average_percentile'], 1)}%",
            f"- Top 10% finishes: {totals['top_10_finishes']}",
            f"- Top 25% finishes: {totals['top_25_finishes']}",
            "",
            "## Best Recent Finishes",
        ]
    )
    for workout in totals["ranked_workouts"][:5]:
        rank = workout.get("leaderboard_rank")
        total = workout.get("leaderboard_total")
        top_percent = workout.get("leaderboard_top_percent")
        lines.append(
            "- "
            f"{timestamp_to_local(workout.get('created_at'))} | "
            f"{truncate(workout.get('title') or 'Untitled', 40)} | "
            f"#{int(rank)} / {int(total)} | "
            f"top {format_number(top_percent, 1)}%"
        )
    return "\n".join(lines)


def render_best_finishes(workouts: list[dict[str, Any]], days: int, limit: int, filters: QueryFilters | None = None) -> str:
    window = workouts_in_window(workouts, days)
    totals = summarize_leaderboard(window)
    lines = [f"# Peloton Best Finishes ({days}d)", ""]
    if not window:
        lines.append("No workouts found in this window.")
        return "\n".join(lines)
    label = filters_label(filters or QueryFilters())
    if label:
        lines.extend([f"- Filters: {label}", ""])
    if totals["ranked_count"] <= 0:
        lines.append("No leaderboard data found in this window.")
        return "\n".join(lines)
    for idx, workout in enumerate(totals["ranked_workouts"][:limit], start=1):
        lines.append(
            f"{idx}. {timestamp_to_local(workout.get('created_at'))} | "
            f"{truncate(workout.get('title') or 'Untitled', 38)} | "
            f"#{int(workout.get('leaderboard_rank'))} / {int(workout.get('leaderboard_total'))} | "
            f"top {format_number(workout.get('leaderboard_top_percent'), 1)}%"
        )
    return "\n".join(lines)


def render_leaderboard_trend(workouts: list[dict[str, Any]], days: int, filters: QueryFilters | None = None) -> str:
    window = workouts_in_window(workouts, days)
    totals = summarize_leaderboard(window)
    lines = [f"# Peloton Leaderboard Trend ({days}d)", ""]
    if not window:
        lines.append("No workouts found in this window.")
        return "\n".join(lines)
    label = filters_label(filters or QueryFilters())
    if label:
        lines.extend([f"- Filters: {label}", ""])
    lines.extend(
        [
            f"- Ranked workouts: {totals['ranked_count']} / {totals['count']}",
            f"- Average beat rate: {format_number(totals['average_percentile'], 1)}%",
            f"- Median beat rate: {format_number(totals['median_percentile'], 1)}%",
            "",
            "## Weekly Buckets",
        ]
    )
    buckets = leaderboard_trend_buckets(window, days)
    if not buckets:
        lines.append("- No leaderboard data found in this window.")
        return "\n".join(lines)
    for bucket in buckets:
        lines.append(
            "- "
            f"{bucket['start'].strftime('%Y-%m-%d')} to {(bucket['end'] - timedelta(days=1)).strftime('%Y-%m-%d')} | "
            f"ranked {bucket['ranked_count']} | "
            f"avg beat {format_number(bucket['average_percentile'], 1)}% | "
            f"top 25% {bucket['top_25_finishes']}"
        )
    return "\n".join(lines)


def render_friends_leaderboard(rows: list[dict[str, Any]], days: int, limit: int) -> str:
    lines = [f"# Peloton Friends Leaderboard ({days}d)", ""]
    if not rows:
        lines.append("No friend leaderboard data found.")
        return "\n".join(lines)
    for idx, row in enumerate(rows[:limit], start=1):
        lines.append(
            f"{idx}. {row['name']} | "
            f"{row['ranked_count']} ranked / {row['count']} workouts | "
            f"avg beat {format_number(row['average_percentile'], 1)}% | "
            f"best #{int(row['best_rank']) if row['best_rank'] is not None else '-'}"
        )
        lines.append(f"   Best: {row['best_line']}")
    return "\n".join(lines)


def render_profile_compare_summary(profile_a: str, summary_a: dict[str, Any], profile_b: str, summary_b: dict[str, Any], days: int, filters: QueryFilters) -> str:
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
            "",
            "## Most Recent",
            f"- {profile_a}: {recent_line(summary_a)}",
            f"- {profile_b}: {recent_line(summary_b)}",
        ]
    )
    return "\n".join(lines)


def render_profile_leaderboard_compare_summary(
    profile_a: str,
    leaderboard_a: dict[str, Any],
    profile_b: str,
    leaderboard_b: dict[str, Any],
    days: int,
    filters: QueryFilters,
) -> str:
    label = filters_label(filters)
    lines = [f"# Peloton Leaderboard Compare ({days}d)", ""]
    if label:
        lines.extend([f"- Filters: {label}", ""])
    lines.extend(
        [
            f"- {profile_a}: {leaderboard_a['ranked_count']} ranked / {leaderboard_a['count']} workouts | best #{int(leaderboard_a['best_rank']) if leaderboard_a['best_rank'] is not None else '-'} | avg beat {format_number(leaderboard_a['average_percentile'], 1)}%",
            f"- {profile_b}: {leaderboard_b['ranked_count']} ranked / {leaderboard_b['count']} workouts | best #{int(leaderboard_b['best_rank']) if leaderboard_b['best_rank'] is not None else '-'} | avg beat {format_number(leaderboard_b['average_percentile'], 1)}%",
            "",
            "## Finish Quality",
            f"- Average beat rate: {format_number(leaderboard_a['average_percentile'], 1)}% vs {format_number(leaderboard_b['average_percentile'], 1)}%",
            f"- Median beat rate: {format_number(leaderboard_a['median_percentile'], 1)}% vs {format_number(leaderboard_b['median_percentile'], 1)}%",
            f"- Top 10% finishes: {leaderboard_a['top_10_finishes']} vs {leaderboard_b['top_10_finishes']}",
            f"- Top 25% finishes: {leaderboard_a['top_25_finishes']} vs {leaderboard_b['top_25_finishes']}",
            "",
            "## Best Recent Finish",
            f"- {profile_a}: {leaderboard_recent_line(leaderboard_a)}",
            f"- {profile_b}: {leaderboard_recent_line(leaderboard_b)}",
        ]
    )
    return "\n".join(lines)


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


def leaderboard_recent_line(summary: dict[str, Any]) -> str:
    workouts = summary.get("ranked_workouts") or []
    if not workouts:
        return "No ranked workouts"
    latest = workouts[0]
    return (
        f"{timestamp_to_local(latest.get('created_at'))} | "
        f"{truncate(latest.get('title') or 'Untitled', 36)} | "
        f"#{int(latest.get('leaderboard_rank'))} / {int(latest.get('leaderboard_total'))} | "
        f"top {format_number(latest.get('leaderboard_top_percent'), 1)}%"
    )


def playlist_preview_lines(client: PelotonClient | None, ride_id: str | None, *, max_songs: int = 3) -> list[str]:
    if client is None or not ride_id:
        return []
    details = client.ride_details(ride_id)
    songs = ((details.get("playlist") or {}).get("songs")) or []
    lines: list[str] = []
    for song in songs[:max_songs]:
        title = song.get("title") or "Unknown"
        artists = ", ".join(artist.get("artist_name") for artist in (song.get("artists") or []) if artist.get("artist_name"))
        lines.append(f"   Playlist: {title}" + (f" - {artists}" if artists else ""))
    return lines


def render_classes(response: dict[str, Any], discipline: str | None, *, client: PelotonClient | None = None, filters: QueryFilters | None = None) -> str:
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
        lines.append(f"   Ride ID: {ride.get('id') or '-'}")
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
        name = item.get("standalone_display_name") or item.get("display_name") or item.get("name") or ""
        item_id = item.get("id")
        if item_id and name:
            type_lookup[item_id] = name.lower()

    filtered = []
    for ride in response.get("data", []):
        name = instructors.get(ride.get("instructor_id")) or ((ride.get("instructor") or {}).get("name")) or ""
        title = (ride.get("title") or "").lower()
        duration_minutes = int((ride.get("duration") or 0) / 60)
        difficulty = ride.get("difficulty_estimate")
        class_type_names = [type_lookup.get(type_id, "") for type_id in (ride.get("class_type_ids") or ride.get("ride_type_ids") or [])]
        playlist_titles: list[str] = []
        playlist_artists: list[str] = []
        playlist_present = None
        if (filters.playlist is not None or filters.song or filters.artist) and client is not None:
            details = client.ride_details(ride.get("id"))
            songs = ((details.get("playlist") or {}).get("songs")) or []
            playlist_present = bool(songs)
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
        if filters.class_type and not (any(filters.class_type in item for item in class_type_names if item) or filters.class_type in title):
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
        if filters.playlist is not None:
            if playlist_present is None:
                playlist_present = False
            if playlist_present != filters.playlist:
                continue
        if filters.song and not any(filters.song in item for item in playlist_titles):
            continue
        if filters.artist and not any(filters.artist in item for item in playlist_artists):
            continue
        filtered.append(ride)

    sort_key = (filters.sort or "").lower()
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
    elif sort_key in {"title", "name"}:
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


def render_recommendations(response: dict[str, Any], discipline: str | None, filters: QueryFilters, limit: int, *, client: PelotonClient | None = None) -> str:
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
            f"{idx}. {ride.get('title') or 'Untitled'} | {instructor_name} | {duration_minutes}m | {timestamp_to_local(ride.get('original_air_time') or ride.get('scheduled_start_time'))}"
        )
        lines.append(f"   Ride ID: {ride.get('id') or '-'}")
        if reasons:
            lines.append(f"   Why: {', '.join(reasons[:4])}")
        if filters.playlist or filters.song or filters.artist:
            lines.extend(playlist_preview_lines(client, ride.get("id")))
    if filters.bookmark:
        lines.extend(["", "- Recommended classes were bookmarked."])
    else:
        lines.extend(["", "- Tip: use `bookmark-class <ride_id>` or `bookmark-recommendation <index> [discipline]` from this shortlist."])
    return "\n".join(lines)


def render_bookmark_result(action: str, ride_id: str, title_text: str | None = None) -> str:
    title = "Bookmarked Class" if action == "bookmark" else "Removed Bookmark"
    lines = [f"# {title}", "", f"- Ride ID: {ride_id}"]
    if title_text:
        lines.append(f"- Title: {title_text}")
    return "\n".join(lines)


def render_instructors(instructors: list[dict[str, Any]]) -> str:
    lines = ["# Peloton Instructors", ""]
    if not instructors:
        lines.append("No instructors returned.")
        return "\n".join(lines)
    for instructor in sorted(instructors, key=lambda item: (item.get("name") or "").lower()):
        lines.append(
            "- "
            f"{instructor.get('name') or '-'} | "
            f"{instructor.get('fitness_disciplines') or instructor.get('quote') or '-'} | "
            f"{instructor.get('id') or '-'}"
        )
    return "\n".join(lines)


def render_instructor(instructor: dict[str, Any]) -> str:
    disciplines = instructor.get("fitness_disciplines") or []
    disciplines_text = ", ".join(disciplines) if isinstance(disciplines, list) and disciplines else str(disciplines or "-")
    return "\n".join(
        [
            "# Peloton Instructor",
            "",
            f"- Name: {instructor.get('name') or '-'}",
            f"- Disciplines: {disciplines_text}",
            f"- Bio: {instructor.get('bio') or '-'}",
            f"- Quote: {instructor.get('quote') or '-'}",
            f"- Instagram: {instructor.get('instagram_handle') or '-'}",
            f"- Twitter: {instructor.get('twitter_handle') or '-'}",
        ]
    )


__all__ = [
    "apply_filters",
    "filter_classes",
    "filters_label",
    "recommend_classes",
    "render_bookmark_result",
    "render_classes",
    "render_compare_summary",
    "render_best_finishes",
    "render_friends_leaderboard",
    "render_instructor",
    "render_instructors",
    "render_leaderboard",
    "render_leaderboard_summary",
    "render_leaderboard_trend",
    "render_named_window_summary",
    "render_normalized_metrics",
    "render_profile",
    "render_profile_leaderboard_compare_summary",
    "render_profile_compare_summary",
    "render_recommendations",
    "render_single_workout",
    "render_summary",
    "render_workouts",
    "summarize_profile_window",
    "workouts_between",
    "workouts_in_window",
]
