---
name: peloton
description: Use this skill when the user asks for Peloton data, Peloton workout history, ride metrics, class discovery, instructor info, music on rides, class recommendations, bookmarks, or Peloton profile comparisons.
---

# Peloton Integration

Use the local CLI to fetch Peloton data directly from the unofficial Peloton API.

## Quick Reference

```bash
cd /path/to/peloton

# Profile / account
python3 scripts/peloton.py me
python3 scripts/peloton.py --profile primary me
python3 scripts/peloton.py --profile partner settings

# Workout history
python3 scripts/peloton.py weekly
python3 scripts/peloton.py --refresh weekly
python3 scripts/peloton.py --profile primary today
python3 scripts/peloton.py --profile partner yesterday
python3 scripts/peloton.py --profile primary month
python3 scripts/peloton.py --profile partner summary 14
python3 scripts/peloton.py --profile partner compare 7 7
python3 scripts/peloton.py compare-profiles primary partner 30
python3 scripts/peloton.py --profile primary workouts 10
python3 scripts/peloton.py --profile partner --discipline strength workouts 10
python3 scripts/peloton.py --profile partner --since 2026-03-01 --until 2026-03-31 month
python3 scripts/peloton.py --profile primary --instructor "Cody" classes cycling 10
python3 scripts/peloton.py --profile primary --duration 20 --min-difficulty 7 --explicit false classes cycling 15
python3 scripts/peloton.py --profile primary --class-type hiit classes cycling 20
python3 scripts/peloton.py --profile primary --title warm --captions true classes cycling 20
python3 scripts/peloton.py --profile primary --artist "Otis" classes cycling 10
python3 scripts/peloton.py --profile primary --song "handle" classes cycling 10
python3 scripts/peloton.py --profile primary --sort difficulty classes cycling 10
python3 scripts/peloton.py --profile primary --duration 20 --min-difficulty 7 recommend cycling 3
python3 scripts/peloton.py --profile primary --artist "Otis" recommend cycling 3
python3 scripts/peloton.py --profile partner latest
python3 scripts/peloton.py --profile primary workout <workout-id>
python3 scripts/peloton.py --profile partner metrics <workout-id>

# Classes / instructors
python3 scripts/peloton.py classes cycling 10
python3 scripts/peloton.py --profile partner instructors
python3 scripts/peloton.py instructor <instructor-id>

# Raw JSON when needed
python3 scripts/peloton.py me --json
python3 scripts/peloton.py --profile partner workout <workout-id> --json
```

## Credentials

The skill supports either a single default account or named profiles.

Single-account environment variables:
- `PELOTON_USERNAME`
- `PELOTON_PASSWORD`

Named-profile environment variables:
- `PELOTON_<PROFILE>_USERNAME`
- `PELOTON_<PROFILE>_PASSWORD`

Examples:
- `PELOTON_PRIMARY_USERNAME`
- `PELOTON_PRIMARY_PASSWORD`
- `PELOTON_PARTNER_USERNAME`
- `PELOTON_PARTNER_PASSWORD`

Profile selection:
- `--profile <name>`
- or `PELOTON_PROFILE=<name>`

Secrets file:
- `~/.openclaw/secrets/peloton.json`

Single-account JSON format:

```json
{
  "username": "name@example.com",
  "password": "super-secret-password"
}
```

Named-profile JSON format:

```json
{
  "primary": {
    "username": "primary@example.com",
    "password": "super-secret-password"
  },
  "partner": {
    "username": "partner@example.com",
    "password": "another-super-secret-password"
  }
}
```

Do not expose credentials or raw auth tokens.

## Command Guidance

- Choose a profile with `--profile <name>` when you manage more than one Peloton account.
- Use `--refresh` when you need fresh data and want to bypass the local cache for that run.
- Use `--discipline <name>` to focus summaries or workout lists on one modality.
- Use `--instructor <name>` for instructor-specific workout or class browsing.
- Use `--since YYYY-MM-DD` and `--until YYYY-MM-DD` to constrain results to a date range.
- For class discovery, combine filters like `--duration`, `--min-duration`, `--max-duration`, `--min-difficulty`, `--max-difficulty`, `--explicit`, `--captions`, `--available`, `--bookmarked`, `--title`, and `--class-type`.
- Music-aware class search is supported with `--song` and `--artist`, using Peloton playlist metadata from ride details.
- Sorting is supported for class discovery with values like `difficulty`, `duration`, `popular`, `rating`, `latest`, `oldest`, `title`, `easiest`, and `shortest`.
- `recommend [discipline] [limit]` turns the current class filters into a curated shortlist instead of a raw list.
- `weekly` is the default summary for a quick training snapshot.
- `today`, `yesterday`, and `month` are the fastest time-window summaries.
- `summary <days>` is best for rolling windows like 7, 14, or 30 days.
- `compare <recent_days> <previous_days>` compares the latest window against the immediately previous one.
- `compare-profiles <profile_a> <profile_b> [days]` compares two named Peloton profiles over the same time window.
- `workouts <limit>` is best when the user wants recent sessions.
- `workout <id>` and `metrics <id>` are best when you already have a workout id from `workouts` or `latest`.
- `classes <discipline> <limit>` is useful for browsing recent classes. Common disciplines include `cycling`, `running`, `walking`, `strength`, `yoga`, and `meditation`.
- Add `--json` when you need to inspect raw API fields before summarizing.

## Interpreting Peloton Data

- Peloton uses **workouts** for sessions the user completed.
- Peloton uses **rides** for classes, even for non-cycling disciplines.
- `performance_graph` contains both aggregate summaries and per-metric series.
- Output values are usually in kilojoules, cadence in RPM, power in watts, resistance in percent, and calories in kcal.

## Response Style

- For user-facing summaries, prefer concise bullets over dumping raw JSON.
- Lead with the time window, workout count, total duration, calories, and output.
- Mention discipline mix if the window includes more than one workout type.
- For a single workout, include class title, instructor, date, duration, calories, output, and standout averages or maxima.
- If the user asks broad fitness questions, Peloton is one input. Combine it with Oura or Tonal context when available.
