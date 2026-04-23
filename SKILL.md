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
python3 scripts/peloton.py --full-metrics workouts 20
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
python3 scripts/peloton.py --profile primary --class-type hiit --instructor "Bradley" bookmark-recommendation 1 cycling
python3 scripts/peloton.py --profile partner latest
python3 scripts/peloton.py --profile primary workout <workout-id>
python3 scripts/peloton.py --profile primary leaderboard
python3 scripts/peloton.py --profile partner leaderboard <workout-id>
python3 scripts/peloton.py --profile primary leaderboard-summary 30
python3 scripts/peloton.py --profile primary best-finishes 90 10
python3 scripts/peloton.py --profile primary leaderboard-trend 90
python3 scripts/peloton.py household-leaderboard primary partner 30
python3 scripts/peloton.py --profile primary friends-leaderboard 30 5
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

## Bot Defaults

For OpenClaw bots, the best setup is to keep one shared Peloton skill and give each bot its own default profile.

Recommended pattern:
- one bot runs with `PELOTON_PROFILE=primary`
- another bot runs with `PELOTON_PROFILE=partner`
- both bots can still use the same shared `~/.openclaw/secrets/peloton.json`

That lets each bot naturally use the correct Peloton account without needing `--profile` on every call.

Example secrets file:

```json
{
  "primary": {
    "username": "primary@example.com",
    "password": "primary-password"
  },
  "partner": {
    "username": "partner@example.com",
    "password": "partner-password"
  }
}
```

Example bot environment:

```bash
# Primary bot
export PELOTON_PROFILE="primary"

# Partner bot
export PELOTON_PROFILE="partner"
```

If a bot has `PELOTON_PROFILE` set, treat that as the default Peloton account for normal queries.
Only switch to another profile when the user explicitly asks for the other person's data or names another profile directly.

If you want stronger separation, each bot can also use its own secrets file via `PELOTON_SECRETS_PATH`, but for most household setups a shared secrets file plus per-bot `PELOTON_PROFILE` is the simplest approach.

If no default top-level `username` / `password` exists in the secrets file, the CLI can fall back to a named profile automatically when there is an obvious default such as `primary`.

If `PELOTON_PROFILE=<name>` is set, the loader can still read that named profile from the shared `~/.openclaw/secrets/peloton.json`; a separate `peloton-<name>.json` file is optional.

## Command Guidance

- Choose a profile with `--profile <name>` when you manage more than one Peloton account.
- In an OpenClaw bot context, prefer the bot's configured `PELOTON_PROFILE` by default.
- Only override the default profile when the user explicitly asks for another person's Peloton data.
- Use `--refresh` when you need fresh data and want to bypass the local cache for that run.
- Use `--full-metrics` when you want the heavier mode that hydrates every returned workout with full performance metrics.
- Use `--discipline <name>` to focus summaries or workout lists on one modality.
- Use `--instructor <name>` for instructor-specific workout or class browsing.
- Use `--since YYYY-MM-DD` and `--until YYYY-MM-DD` to constrain results to a date range.
- For class discovery, combine filters like `--duration`, `--min-duration`, `--max-duration`, `--min-difficulty`, `--max-difficulty`, `--explicit`, `--captions`, `--available`, `--bookmarked`, `--title`, and `--class-type`.
- Music-aware class search is supported with `--song` and `--artist`, using Peloton playlist metadata from ride details.
- Sorting is supported for class discovery with values like `difficulty`, `duration`, `popular`, `rating`, `latest`, `oldest`, `title`, `easiest`, and `shortest`.
- `recommend [discipline] [limit]` turns the current class filters into a curated shortlist instead of a raw list.
- `bookmark-recommendation <index> [discipline]` bookmarks an item directly from the current filtered recommendation shortlist.
- `weekly` is the default summary for a quick training snapshot.
- `today`, `yesterday`, and `month` are the fastest time-window summaries.
- `summary <days>` is best for rolling windows like 7, 14, or 30 days.
- `leaderboard [workout_id]` shows rank, finish percentile, and field size for one workout. If no workout id is given, it uses the latest workout.
- `leaderboard-summary [days]` shows recent leaderboard trends like best finish, median beat rate, and top-10% / top-25% finishes.
- `best-finishes [days] [limit]` lists your strongest leaderboard finishes in the selected window.
- `leaderboard-trend [days]` buckets recent ranked workouts into weekly trend lines.
- `household-leaderboard <profile_a> <profile_b> [days]` compares two Peloton profiles by recent leaderboard finish quality.
- `friends-leaderboard [days] [friend_limit]` compares followed users by recent ranked Peloton finishes when follow data is available.
- `compare <recent_days> <previous_days>` compares the latest window against the immediately previous one.
- `compare-profiles <profile_a> <profile_b> [days]` compares two named Peloton profiles over the same time window.
- `workouts <limit>` is best when the user wants recent sessions.
- `workout <id>` and `metrics <id>` are best when you already have a workout id from `workouts` or `latest`.
- `classes <discipline> <limit>` is useful for browsing recent classes. Common disciplines include `cycling`, `running`, `walking`, `strength`, `yoga`, and `meditation`.
- `classes` and `recommend` output ride ids. Preserve and reuse those ids for follow-up actions like `bookmark-class`.
- Add `--json` when you need to inspect raw API fields before summarizing.

## Bookmarking Guidance

- When a user asks to bookmark a class, prefer using the exact `ride_id` from a current `classes` or `recommend` result.
- Do not ask the user for a Peloton link or ride id if the current shortlist already identifies a single intended class.
- If the user refers to "the first one", "the Bradley one", or another clear shortlist item, use `bookmark-recommendation <index> [discipline]` or the exact `bookmark-class <ride_id>` call instead of asking them to look it up manually.
- The bookmark write path requires the `Peloton-Platform: web` header, which the CLI already sends.

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
