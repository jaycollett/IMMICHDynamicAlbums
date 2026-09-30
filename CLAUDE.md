# CLAUDE.md

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

## Non-obvious semantics

- **Conditions**: `conditions:` block supports nested AND/OR. `filters:` uses implicit AND. Cannot mix both.
- **People filter**: Immich API uses AND logic for multiple people. Use OR conditions for "any of these people".

## API Permissions Required

asset.read, album.read, album.create, album.update, albumAsset.create, albumAsset.delete (sync mode only), user.read (if sharing enabled)
