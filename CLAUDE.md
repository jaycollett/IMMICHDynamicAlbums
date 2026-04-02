# CLAUDE.md

Do not make any changes until you have 95% confidence in what you need to build. Ask me follow-up questions until you reach that confidence.

## Project Overview

Docker-based Python app that auto-creates/manages Immich photo albums based on YAML rules. Periodically scans for new images and applies album logic with add_only or sync modes.

## Commands

```bash
# Dev
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/main.py --config config.yaml --dry-run --once

# Test
python -m pytest tests/ -v

# Docker
docker-compose up -d
docker-compose run --rm immich-dynamic-albums python src/main.py --dry-run --once
```

## Key Rules

- **Always create/update tests** before releasing. All tests must pass.
- Tags use semver WITHOUT 'v' prefix (e.g., `0.0.1`)
- Release workflow triggers on GitHub release published, builds and pushes to GHCR

## Environment Variables

- `IMMICH_API_KEY` (required), `IMMICH_BASE_URL` (required, must end with `/api`)
- `SLEEP_INTERVAL_SECONDS`, `LOG_LEVEL`, `DEFAULT_TIMEZONE` (default: America/New_York)
- `SHARE_WITH_ALL_USERS`, `SHARE_USER_IDS` (comma-separated emails)

## Architecture

- `src/immich_client.py` - Immich API client with pagination and rate limiting (100ms delays, 500-asset chunks)
- `src/database.py` - SQLite with schema migrations (WITHOUT ROWID, WAL mode, covering indexes)
- `src/rules.py` - YAML rule parsing, recurring rule expansion with timezone support
- `src/conditions.py` - AND/OR conditional logic for complex filtering
- `src/main.py` - Entry point, CLI args, continuous sync loop

## Config Highlights

- **Recurring rules**: `recurring: true` with `month_day`, `timezone`, `year_range`, `album_name_template`
- **Conditions**: `conditions:` block supports nested AND/OR. `filters:` uses implicit AND. Cannot mix both.
- **People filter**: Immich API uses AND logic for multiple people. Use OR conditions for "any of these people".
- **Sharing**: Per-rule `share_with` overrides global. Priority: per-rule > SHARE_USER_IDS > SHARE_WITH_ALL_USERS.
- **Sync modes**: `add_only` (safer) vs `sync` (adds and removes)

## API Permissions Required

asset.read, album.read, album.create, album.update, albumAsset.create, albumAsset.delete (sync mode only), user.read (if sharing enabled)
