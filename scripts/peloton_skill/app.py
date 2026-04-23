from __future__ import annotations

import json
from datetime import datetime, timedelta

from .client import PelotonClient
from .common import PelotonError, eprint
from .config import load_credentials, parse_args, selected_profile
from .normalize import apply_filters, summarize_leaderboard, summarize_profile_window, workouts_between, workouts_in_window
from .render import (
    filter_classes,
    recommend_classes,
    render_bookmark_result,
    render_best_finishes,
    render_classes,
    render_compare_summary,
    render_friends_leaderboard,
    render_instructor,
    render_instructors,
    render_leaderboard,
    render_leaderboard_summary,
    render_leaderboard_trend,
    render_named_window_summary,
    render_normalized_metrics,
    render_profile,
    render_profile_leaderboard_compare_summary,
    render_profile_compare_summary,
    render_recommendations,
    render_single_workout,
    render_summary,
    render_workouts,
)


def enrich_sparse_workouts(
    client: PelotonClient,
    workouts: list[dict[str, object]],
    *,
    max_items: int = 5,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    enriched_count = 0
    for workout in workouts:
        needs_metrics = (
            enriched_count < max_items
            and (
                float(workout.get("calories") or 0) <= 0
                or (
                    workout.get("avg_power") is None
                    and workout.get("avg_cadence") is None
                    and workout.get("avg_heart_rate") is None
                )
            )
        )
        if needs_metrics:
            enriched.append(
                client.normalized_workout(str(workout.get("id")), include_metrics=True)
            )
            enriched_count += 1
        else:
            enriched.append(workout)
    return enriched


def enrich_leaderboard_workouts(
    client: PelotonClient,
    workouts: list[dict[str, object]],
    *,
    max_items: int = 25,
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    enriched_count = 0
    for workout in workouts:
        needs_leaderboard = (
            enriched_count < max_items
            and workout.get("leaderboard_rank") in (None, "", 0)
            and workout.get("leaderboard_total") in (None, "", 0)
            and ((workout.get("raw_workout") or {}).get("has_leaderboard_metrics") is True)
        )
        if needs_leaderboard:
            enriched.append(
                client.normalized_workout(str(workout.get("id")), include_metrics=False)
            )
            enriched_count += 1
        else:
            enriched.append(workout)
    return enriched


def usage() -> str:
    return """Usage: python3 scripts/peloton.py [--profile <name>] [--refresh] [--full-metrics] [--discipline <name>] [--instructor <name>] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--title <text>] [--class-type <text>] [--duration <minutes>] [--min-duration <minutes>] [--max-duration <minutes>] [--min-difficulty <n>] [--max-difficulty <n>] [--explicit true|false] [--captions true|false] [--available true|false] [--bookmarked true|false] [--song <text>] [--artist <text>] [--sort <name>] [--bookmark true|false] [--playlist true|false] <command> [args] [--json]

Commands:
  --profile <name>
  --refresh
  --full-metrics
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
  leaderboard [workout_id]
  best-finishes [days] [limit]
  metrics <workout_id> [every_n]
  leaderboard-summary [days]
  leaderboard-trend [days]
  summary [days]
  weekly
  compare [recent_days] [previous_days]
  compare-profiles <profile_a> <profile_b> [days]
  household-leaderboard <profile_a> <profile_b> [days]
  friends-leaderboard [days] [friend_limit]
  classes [discipline] [limit]
  recommend [discipline] [limit]
  bookmark-recommendation <index> [discipline]
  bookmark-class <ride_id>
  unbookmark-class <ride_id>
  instructors
  instructor <instructor_id>
"""


def discovery_pool_size(limit: int, filters: QueryFilters) -> int:
    if filters.song or filters.artist or filters.playlist:
        return max(limit * 8, 60)
    return limit


def main(argv: list[str]) -> int:
    if not argv or any(arg in {"--help", "-h", "help"} for arg in argv):
        print(usage().strip())
        return 0

    profile_arg, json_output, refresh, full_metrics, filters, args = parse_args(argv)
    if not args:
        print(usage().strip())
        return 0

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
            client_a = PelotonClient(creds_a["username"], creds_a["password"], refresh_cache=refresh)
            client_b = PelotonClient(creds_b["username"], creds_b["password"], refresh_cache=refresh)
            workouts_a = client_a.normalized_workouts(limit=50, include_metrics=full_metrics)
            workouts_b = client_b.normalized_workouts(limit=50, include_metrics=full_metrics)
            summary_a = summarize_profile_window(profile_a, workouts_a, days, filters)
            summary_b = summarize_profile_window(profile_b, workouts_b, days, filters)
            print(
                render_profile_compare_summary(profile_a, summary_a, profile_b, summary_b, days, filters)
                if not json_output
                else json.dumps({"profile_a": summary_a, "profile_b": summary_b, "days": days}, indent=2)
            )
            return 0
        if command == "household-leaderboard":
            if len(rest) < 2:
                raise PelotonError("household-leaderboard requires <profile_a> <profile_b> [days]")
            profile_a = rest[0].strip().lower()
            profile_b = rest[1].strip().lower()
            days = int(rest[2]) if len(rest) > 2 else 30
            creds_a = load_credentials(profile_a)
            creds_b = load_credentials(profile_b)
            client_a = PelotonClient(creds_a["username"], creds_a["password"], refresh_cache=refresh)
            client_b = PelotonClient(creds_b["username"], creds_b["password"], refresh_cache=refresh)
            workouts_a = client_a.normalized_workouts(limit=50, include_metrics=False)
            workouts_b = client_b.normalized_workouts(limit=50, include_metrics=False)
            filtered_a = apply_filters(workouts_in_window(workouts_a, days), filters)
            filtered_b = apply_filters(workouts_in_window(workouts_b, days), filters)
            filtered_a = enrich_leaderboard_workouts(client_a, filtered_a)
            filtered_b = enrich_leaderboard_workouts(client_b, filtered_b)
            leaderboard_a = summarize_leaderboard(filtered_a)
            leaderboard_b = summarize_leaderboard(filtered_b)
            print(
                render_profile_leaderboard_compare_summary(
                    profile_a,
                    leaderboard_a,
                    profile_b,
                    leaderboard_b,
                    days,
                    filters,
                )
                if not json_output
                else json.dumps({"profile_a": leaderboard_a, "profile_b": leaderboard_b, "days": days}, indent=2)
            )
            return 0

        profile = selected_profile(profile_arg)
        creds = load_credentials(profile)
        client = PelotonClient(creds["username"], creds["password"], refresh_cache=refresh)

        if command == "me":
            data = client.me()
            print(json.dumps(data, indent=2) if json_output else render_profile(data))
            return 0
        if command == "settings":
            data = client.settings()
            print(json.dumps(data, indent=2))
            return 0
        if command == "workouts":
            limit = int(rest[0]) if rest else 10
            include_metrics = full_metrics or limit <= 10
            data = client.normalized_workouts(limit=limit, include_metrics=include_metrics)
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
        if command == "leaderboard":
            if rest:
                data = client.normalized_workout(rest[0], include_metrics=False)
            else:
                latest = client.latest_workout()
                data = client.normalized_workout(latest["id"], include_metrics=False)
            print(json.dumps(data, indent=2) if json_output else render_leaderboard(data))
            return 0
        if command == "metrics":
            if not rest:
                raise PelotonError("metrics requires <workout_id>")
            every_n = int(rest[1]) if len(rest) > 1 else 5
            data = client.normalized_workout(rest[0], include_metrics=True, every_n=every_n)
            print(json.dumps(data, indent=2) if json_output else render_normalized_metrics(data))
            return 0
        if command == "leaderboard-summary":
            days = int(rest[0]) if rest else 30
            workouts = client.normalized_workouts(limit=50, include_metrics=False)
            filtered = apply_filters(workouts_in_window(workouts, days), filters)
            filtered = enrich_leaderboard_workouts(client, filtered)
            print(
                render_leaderboard_summary(filtered, days, filters)
                if not json_output
                else json.dumps(filtered, indent=2)
            )
            return 0
        if command == "best-finishes":
            days = int(rest[0]) if rest else 90
            limit = int(rest[1]) if len(rest) > 1 else 10
            workouts = client.normalized_workouts(limit=50, include_metrics=False)
            filtered = apply_filters(workouts_in_window(workouts, days), filters)
            filtered = enrich_leaderboard_workouts(client, filtered)
            print(
                render_best_finishes(filtered, days, limit, filters)
                if not json_output
                else json.dumps(filtered, indent=2)
            )
            return 0
        if command == "leaderboard-trend":
            days = int(rest[0]) if rest else 90
            workouts = client.normalized_workouts(limit=50, include_metrics=False)
            filtered = apply_filters(workouts_in_window(workouts, days), filters)
            filtered = enrich_leaderboard_workouts(client, filtered)
            print(
                render_leaderboard_trend(filtered, days, filters)
                if not json_output
                else json.dumps(filtered, indent=2)
            )
            return 0
        if command == "summary":
            days = int(rest[0]) if rest else 7
            workouts = client.normalized_workouts(limit=25, include_metrics=full_metrics)
            filtered = apply_filters(workouts_in_window(workouts, days), filters)
            if not full_metrics:
                filtered = enrich_sparse_workouts(client, filtered)
            print(render_summary(filtered, days, filters) if not json_output else json.dumps(filtered, indent=2))
            return 0
        if command == "weekly":
            workouts = client.normalized_workouts(limit=25, include_metrics=full_metrics)
            filtered = apply_filters(workouts_in_window(workouts, 7), filters)
            if not full_metrics:
                filtered = enrich_sparse_workouts(client, filtered)
            print(render_summary(filtered, 7, filters) if not json_output else json.dumps(filtered, indent=2))
            return 0
        if command == "today":
            workouts = client.normalized_workouts(limit=25, include_metrics=full_metrics)
            now = datetime.now().astimezone()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            window = apply_filters(workouts_between(workouts, start=start, end=now), filters)
            if not full_metrics:
                window = enrich_sparse_workouts(client, window)
            print(render_named_window_summary(window, title="Peloton Today", filters=filters) if not json_output else json.dumps(window, indent=2))
            return 0
        if command == "yesterday":
            workouts = client.normalized_workouts(limit=25, include_metrics=full_metrics)
            now = datetime.now().astimezone()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start = today_start - timedelta(days=1)
            window = apply_filters(workouts_between(workouts, start=start, end=today_start), filters)
            if not full_metrics:
                window = enrich_sparse_workouts(client, window)
            print(render_named_window_summary(window, title="Peloton Yesterday", filters=filters) if not json_output else json.dumps(window, indent=2))
            return 0
        if command == "month":
            workouts = client.normalized_workouts(limit=50, include_metrics=full_metrics)
            now = datetime.now().astimezone()
            start = now - timedelta(days=30)
            window = apply_filters(workouts_between(workouts, start=start, end=now), filters)
            if not full_metrics:
                window = enrich_sparse_workouts(client, window)
            print(render_named_window_summary(window, title="Peloton Last 30 Days", filters=filters) if not json_output else json.dumps(window, indent=2))
            return 0
        if command == "compare":
            recent_days = int(rest[0]) if rest else 7
            previous_days = int(rest[1]) if len(rest) > 1 else recent_days
            workouts = client.normalized_workouts(limit=50, include_metrics=full_metrics)
            print(render_compare_summary(workouts, recent_days, previous_days, filters) if not json_output else json.dumps({"recent_days": recent_days, "previous_days": previous_days}, indent=2))
            return 0
        if command == "friends-leaderboard":
            days = int(rest[0]) if rest else 30
            friend_limit = int(rest[1]) if len(rest) > 1 else 5
            following = client.following(limit=friend_limit, page=0)
            rows: list[dict[str, object]] = []
            for friend in following:
                user_id = friend.get("id")
                if not user_id:
                    continue
                workouts = client.normalized_user_workouts(str(user_id), limit=10, include_metrics=False)
                filtered = apply_filters(workouts_in_window(workouts, days), filters)
                filtered = enrich_leaderboard_workouts(client, filtered, max_items=10)
                summary = summarize_leaderboard(filtered)
                if summary["ranked_count"] <= 0:
                    continue
                ranked = summary.get("ranked_workouts") or []
                best = ranked[0] if ranked else None
                rows.append(
                    {
                        "name": friend.get("username") or friend.get("name") or str(user_id),
                        "count": summary["count"],
                        "ranked_count": summary["ranked_count"],
                        "average_percentile": summary["average_percentile"],
                        "best_rank": summary["best_rank"],
                        "best_line": (
                            f"{best.get('title') or 'Untitled'} | "
                            f"#{int(best.get('leaderboard_rank'))} / {int(best.get('leaderboard_total'))} | "
                            f"top {float(best.get('leaderboard_top_percent') or 0):.1f}%"
                            if best
                            else "No ranked workouts"
                        ),
                    }
                )
            rows.sort(key=lambda item: float(item.get("average_percentile") or -1), reverse=True)
            print(
                render_friends_leaderboard(rows, days, friend_limit)
                if not json_output
                else json.dumps(rows, indent=2)
            )
            return 0
        if command == "classes":
            discipline = rest[0] if rest else filters.discipline
            limit = int(rest[1]) if len(rest) > 1 else 10
            pool_size = discovery_pool_size(limit, filters)
            data = client.classes(discipline=discipline, limit=pool_size)
            data = filter_classes(data, filters, client=client)
            data["data"] = list(data.get("data", []))[:limit]
            print(json.dumps(data, indent=2) if json_output else render_classes(data, discipline, client=client, filters=filters))
            return 0
        if command == "recommend":
            discipline = rest[0] if rest else filters.discipline
            limit = int(rest[1]) if len(rest) > 1 else 5
            pool_size = max(discovery_pool_size(limit, filters), 30)
            data = client.classes(discipline=discipline, limit=pool_size)
            data = filter_classes(data, filters, client=client)
            recommendations = recommend_classes(data, filters, limit)
            if filters.bookmark:
                for ride in recommendations:
                    client.bookmark_class(ride.get("id"))
            print(json.dumps(recommendations, indent=2) if json_output else render_recommendations(data, discipline, filters, limit, client=client))
            return 0
        if command == "bookmark-recommendation":
            if not rest:
                raise PelotonError("bookmark-recommendation requires <index> [discipline]")
            index = int(rest[0])
            if index <= 0:
                raise PelotonError("bookmark-recommendation index must be 1 or greater")
            discipline = rest[1] if len(rest) > 1 else filters.discipline
            pool_size = max(discovery_pool_size(index, filters), 30)
            data = client.classes(discipline=discipline, limit=pool_size)
            data = filter_classes(data, filters, client=client)
            recommendations = recommend_classes(data, filters, index)
            if len(recommendations) < index:
                raise PelotonError(f"Only found {len(recommendations)} recommendation(s) for the current filters.")
            ride = recommendations[index - 1]
            ride_id = ride.get("id")
            if not ride_id:
                raise PelotonError("Selected recommendation is missing a ride id.")
            client.bookmark_class(str(ride_id))
            print(
                json.dumps(ride, indent=2)
                if json_output
                else render_bookmark_result("bookmark", str(ride_id), ride.get("title"))
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
