# Peloton Skill

Peloton CLI + skill for querying the unofficial Peloton API.

It supports:

- workout history and summaries
- profile and workout metrics
- class discovery with rich filters
- music-aware class search by song or artist
- class recommendations
- bookmarking and unbookmarking classes
- multi-profile setups
- optional cache bypass with `--refresh`
- optional full workout hydration with `--full-metrics`

## Features

- Single-account or named-profile auth
- Normalized workout data across Peloton's uneven endpoints
- Time-window commands: `today`, `yesterday`, `weekly`, `month`, `summary`
- Filters for discipline, instructor, dates, and workout/class attributes
- Class filters for duration, difficulty, captions, explicitness, title, class type, popularity, and sort order
- Music-aware search using playlist metadata from ride details
- `recommend` command for curated class shortlists
- `bookmark-recommendation` command for bookmarking directly from a shortlist
- Bookmark / unbookmark class actions
- Lightweight local cache
- Short delay between uncached API requests to avoid hammering Peloton

## Setup

### Option 1: Single account

Set environment variables:

```bash
export PELOTON_USERNAME="you@example.com"
export PELOTON_PASSWORD="your-password"
```

Or create `~/.openclaw/secrets/peloton.json`:

```json
{
  "username": "you@example.com",
  "password": "your-password"
}
```

If the file only contains named profiles and no top-level default account, the CLI can fall back to an obvious default such as `primary`, but `--profile <name>` or `PELOTON_PROFILE=<name>` is still the clearest setup.

When `PELOTON_PROFILE=<name>` is set, the loader will still use the shared `~/.openclaw/secrets/peloton.json` file if it exists; a separate `peloton-<name>.json` file is optional, not required.

### Option 2: Named profiles

Set environment variables:

```bash
export PELOTON_PRIMARY_USERNAME="you@example.com"
export PELOTON_PRIMARY_PASSWORD="your-password"
export PELOTON_PARTNER_USERNAME="partner@example.com"
export PELOTON_PARTNER_PASSWORD="partner-password"
```

Or create `~/.openclaw/secrets/peloton.json`:

```json
{
  "primary": {
    "username": "you@example.com",
    "password": "your-password"
  },
  "partner": {
    "username": "partner@example.com",
    "password": "partner-password"
  }
}
```

## Usage

Run from the repo root:

```bash
python3 scripts/peloton.py weekly
python3 scripts/peloton.py --refresh weekly
python3 scripts/peloton.py --full-metrics workouts 20
python3 scripts/peloton.py --profile primary today
python3 scripts/peloton.py --profile partner workouts 10
python3 scripts/peloton.py --profile primary latest
python3 scripts/peloton.py --profile primary metrics <workout_id>
```

### Class discovery

```bash
python3 scripts/peloton.py classes cycling 10
python3 scripts/peloton.py --duration 20 --min-difficulty 7 classes cycling 15
python3 scripts/peloton.py --class-type hiit classes cycling 20
python3 scripts/peloton.py --artist "Otis" classes cycling 10
python3 scripts/peloton.py --song "handle" classes cycling 10
python3 scripts/peloton.py --sort difficulty classes cycling 10
```

### Recommendations

```bash
python3 scripts/peloton.py --duration 20 --min-difficulty 7 recommend cycling 3
python3 scripts/peloton.py --artist "Otis" --playlist true recommend cycling 1
python3 scripts/peloton.py --bookmarked true recommend cycling 3
python3 scripts/peloton.py --artist "Otis" --bookmark true recommend cycling 1
python3 scripts/peloton.py --class-type hiit --instructor "Bradley" bookmark-recommendation 1 cycling
```

### Bookmarking

```bash
python3 scripts/peloton.py bookmark-class <ride_id>
python3 scripts/peloton.py bookmark-recommendation <index> [discipline]
python3 scripts/peloton.py unbookmark-class <ride_id>
```

## Notes

- This project uses the unofficial Peloton API and may break if Peloton changes its backend.
- Some write endpoints require the `Peloton-Platform: web` header.
- `classes` and `recommend` output ride ids so follow-up actions can use the exact class record.
- If you already have a clear recommendation shortlist, use `bookmark-recommendation` instead of asking a user to paste a Peloton link.
- The CLI caches certain responses under `~/.openclaw/cache/peloton/`.
- Use `--refresh` when you explicitly want to bypass cached responses.
- Use `--full-metrics` when you want the heavier mode that hydrates every workout in the returned set with performance metrics.
- This project is not affiliated with Peloton.
