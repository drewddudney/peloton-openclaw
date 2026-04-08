from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from .common import QueryFilters, joules_to_kj


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

    return {
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
        ) or 0,
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


def discipline_counts(workouts: list[dict[str, Any]]) -> str:
    counts = Counter(workout.get("discipline") or workout.get("fitness_discipline") or "unknown" for workout in workouts)
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


def workouts_between(workouts: list[dict[str, Any]], *, start: datetime, end: datetime) -> list[dict[str, Any]]:
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
            if (workout.get("discipline") or workout.get("fitness_discipline") or "").lower() == filters.discipline
        ]
    if filters.instructor:
        def instructor_name(workout: dict[str, Any]) -> str:
            if "discipline" in workout:
                return (workout.get("instructor") or "").lower()
            ride = workout.get("ride") or {}
            return (((ride.get("instructor") or {}).get("name")) or workout.get("instructor_name") or "").lower()

        results = [workout for workout in results if filters.instructor in instructor_name(workout)]
    return results


def summarize_window(workouts: list[dict[str, Any]]) -> dict[str, Any]:
    total_seconds = 0
    total_calories = 0.0
    total_output = 0.0

    for workout in workouts:
        if "discipline" in workout:
            total_seconds += int(workout.get("duration_seconds") or 0)
            total_calories += float(workout.get("calories") or 0)
            total_output += float(workout.get("output_kj") or 0)
            continue
        ride = workout.get("ride") or {}
        summary = overall_summary_map(workout)
        total_seconds += int(ride.get("duration") or max((workout.get("end_time") or 0) - (workout.get("start_time") or 0), 0))
        total_calories += float(summary.get("calories") or 0)
        total_output += joules_to_kj(summary.get("total_work") or workout.get("total_work") or 0)

    return {
        "count": len(workouts),
        "duration_seconds": total_seconds,
        "calories": total_calories,
        "output_kj": total_output,
        "disciplines": discipline_counts(workouts) if workouts else "-",
    }


def summarize_profile_window(profile: str, workouts: list[dict[str, Any]], days: int, filters: QueryFilters) -> dict[str, Any]:
    filtered = apply_filters(workouts_in_window(workouts, days), filters)
    totals = summarize_window(filtered)
    totals["profile"] = profile
    totals["workouts"] = filtered
    return totals
