# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Workflow

**Important**: When working on this project, use agents and skills appropriately. Focus primarily on organizing and managing agents' work for development tasks rather than doing all the work directly. This includes:

- Using the **Explore** agent for codebase understanding and analysis
- Using the **Plan** agent for designing implementation approaches before coding
- Using the **python-project-engineer** agent for Python feature and test implementation
- Using the **test-ci-enforcer** agent for test coverage and CI pipeline work
- Using the **code-review-refactor-coach** agent for code reviews and refactoring
- Running multiple agents in parallel when tasks are independent
- Coordinating agent work and synthesizing their results

## Testing Requirements

**CRITICAL - MUST FOLLOW**: Before creating any release or deploying changes:

1. **Always create unit tests** for any new features or significant changes
2. **All tests must pass** before committing and creating a release
3. **Run the full test suite** using: `python -m pytest tests/ -v`
4. **Update existing tests** if you change functionality they cover
5. **Never skip testing** - untested code should not be released

Test locations:
- `tests/test_album_sharing.py` - Album sharing functionality
- `tests/test_recurring_rules.py` - Recurring rule expansion and timezone handling
- `tests/test_validation_and_filtering.py` - Config validation and filtering logic
- `tests/test_conditions.py` - AND/OR conditional logic and tree evaluation

## Project Overview

IMMICHDynamicAlbums is a Docker-based Python application that automatically creates and manages albums in Immich (photo management system) based on predefined rules. The application periodically scans for new images and applies album logic, creating or updating albums to include matching assets.

## Architecture

### Core Components

The application follows a modular architecture:

1. **Immich API Client** (`src/immich_client.py`)
   - Handles all communication with Immich REST API
   - Implements pagination for asset searches
   - Filters out non-image assets automatically
   - Includes rate limiting and chunked operations for bulk updates

2. **Database Layer** (`src/database.py`)
   - SQLite database with schema migration system
   - Optimized for handling hundreds of thousands of assets
   - Uses WITHOUT ROWID tables for text primary keys
   - Implements WAL mode, covering indexes, and bulk operations
   - Tracks analyzed assets, album memberships, and sync run history

3. **Rule Engine** (`src/rules.py`)
   - Parses YAML configuration files
   - Executes rules to find matching assets
   - Supports both "add_only" and "sync" modes
   - Handles album creation and membership management

4. **Main Application** (`src/main.py`)
   - Entry point with CLI argument parsing
   - Continuous sync loop with configurable sleep interval
   - Supports dry-run mode for testing
   - Comprehensive logging and error handling

### Data Flow

1. Application loads rules from `config.yaml`
2. Database migrations run automatically on startup
3. For each rule:
   - Query Immich API for matching image assets
   - Find or create the target album
   - Compare desired state with database-tracked state
   - Add/remove assets as needed based on sync mode
   - Record operations in database
4. Sleep for configured interval and repeat

### Database Schema

**analyzed_assets**: Tracks all assets that have been processed
- Uses WITHOUT ROWID for faster text primary key lookups
- Indexes on asset_type and last_analyzed for efficient queries

**album_memberships**: Records which assets belong to which albums via which rules
- Composite primary key (rule_id, album_id, asset_id) with WITHOUT ROWID
- Covering indexes for album and asset lookups

**sync_runs**: History of sync operations with statistics
- Tracks success/failure, asset counts, and timing

**schema_version**: Manages database migrations
- Simple version tracking with timestamp

## Development Commands

### Local Development

```bash
# Set up environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Set environment variables
export IMMICH_API_KEY=your-key-here
export IMMICH_BASE_URL=https://immich.example.com/api

# Run once in dry-run mode
python src/main.py --config config.yaml --dry-run --once

# Run continuously
python src/main.py --config config.yaml
```

### Docker

```bash
# Build and run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Run once
docker-compose run --rm immich-dynamic-albums python src/main.py --once

# Dry run
docker-compose run --rm immich-dynamic-albums python src/main.py --dry-run --once

# Stop
docker-compose down
```

### Testing Database Migrations

To test database migrations in isolation:

```python
from src.database import Database

# Create test database
db = Database("test.db")

# Check version
cursor = db.conn.cursor()
cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
print(f"Schema version: {cursor.fetchone()[0]}")

db.close()
```

## Configuration

### Environment Variables (.env)

- `IMMICH_API_KEY`: Required. API key from Immich with appropriate permissions
- `IMMICH_BASE_URL`: Required. Base API URL (must end with `/api`)
- `SLEEP_INTERVAL_SECONDS`: Optional. Seconds between sync runs (default: 3600)
- `LOG_LEVEL`: Optional. Logging level (default: INFO)
- `DEFAULT_TIMEZONE`: Optional. Default IANA timezone for recurring rules (default: America/New_York)
- `SHARE_WITH_ALL_USERS`: Optional. Share albums with all users (default: false). Overrides `SHARE_USER_IDS` if both are set.
- `SHARE_USER_IDS`: Optional. Share albums with specific users (comma-separated email addresses). Example: "user1@example.com,user2@example.com". Per-rule `share_with` overrides this.

### Rules Configuration (config.yaml)

#### Regular Rules

Rules use date ranges to filter assets:

- `taken_range_utc`: Filter by EXIF date (when photo was taken)
- `created_range_utc`: Filter by upload date (when added to Immich)

All timestamps must be ISO 8601 format with UTC timezone (trailing `Z`).

#### Recurring Rules

Recurring rules automatically generate year-specific rules for annual events (holidays, birthdays, etc.):

**Required fields:**
- `recurring: true` - Marks this as a recurring rule
- `month_day` - Date in "MM-DD" format (e.g., "12-25")
- `timezone` - IANA timezone name (e.g., "America/New_York") **NEW**
- `album_name_template` - Album name with `{year}` placeholder
- `year_range` - [start_year, end_year] array (inclusive)

**Optional fields:**
- `duration_days` - Number of days to include (default: 1)
- `description` - Album description
- `filters` - Same filters as regular rules (asset_types, is_favorite, camera, tags)

**Example:**
```yaml
- id: "christmas"
  recurring: true
  month_day: "12-25"
  timezone: "America/New_York"
  duration_days: 1
  album_name_template: "Christmas {year}"
  year_range: [2000, 2030]
  filters:
    asset_types: [IMAGE, VIDEO]
```

This expands to 31 individual rules at runtime (christmas-2000, christmas-2001, ..., christmas-2030).

**Timezone Handling:**

Timezone support ensures photos are matched to the correct local calendar day. Photos taken on Christmas Day at 11 PM EST (UTC-5) are stored in IMMICH as 4 AM UTC on December 26. Without timezone support, this photo wouldn't match a "Christmas" rule.

- **Default timezone:** Set via `DEFAULT_TIMEZONE` environment variable (defaults to "America/New_York")
- **Per-rule override:** Specify timezone in each recurring rule
- **DST handling:** Automatic - zoneinfo applies correct offset (EST vs EDT, PST vs PDT, etc.)
- **Common timezones:**
  - `America/New_York` - Eastern (EST/EDT, UTC-5/-4)
  - `America/Chicago` - Central (CST/CDT, UTC-6/-5)
  - `America/Denver` - Mountain (MST/MDT, UTC-7/-6)
  - `America/Los_Angeles` - Pacific (PST/PDT, UTC-8/-7)
  - `America/Phoenix` - Arizona (MST, no DST, UTC-7)
  - `Pacific/Honolulu` - Hawaii (HST, no DST, UTC-10)
  - `UTC` - Universal time (no offset)

**Example timezone conversion:**
- Christmas 2025 midnight EST → `2025-12-25T05:00:00.000Z` (UTC)
- July 4th 2025 midnight EDT → `2025-07-04T04:00:00.000Z` (UTC, DST active)

**Implementation:** See `src/rules.py:_expand_recurring_rule()`, `src/rules.py:_create_local_midnight_utc()`, and `src/validation.py:_validate_timezone()`

#### Sync Modes

- `add_only`: Safer, only adds new matching assets (recommended)
- `sync`: Full sync, adds new and removes non-matching assets

#### AND/OR Conditional Logic

The application supports Home Assistant-style AND/OR conditional logic for expressing complex filtering requirements. This allows you to create albums with conditions like "photos with ANY family member" or "favorites from iPhone OR videos with people".

**Basic Concepts:**

- **`filters:` (implicit AND)** - The traditional format where all filters must match (backward compatible)
- **`conditions:` (explicit AND/OR)** - The new format that allows explicit AND/OR logic with unlimited nesting
- You cannot use both `filters:` and `conditions:` in the same rule

**IMPORTANT - People Filter Behavior:**

The Immich API uses **AND logic** for people filters. When you specify multiple people in `filters.people.include`, it returns photos with **ALL** of those people (not any of them):

```yaml
# This uses AND logic (single efficient API call):
filters:
  people:
    include: ["Person1", "Person2", "Person3"]
# Returns: Photos with Person1 AND Person2 AND Person3 (all three in the same photo)
```

For "any of these people" logic (OR), you must use the explicit `conditions` syntax:

```yaml
# OR logic - photos with ANY of these people (requires multiple API calls):
conditions:
  or:
    - people: {include: ["Person1"]}
    - people: {include: ["Person2"]}
    - people: {include: ["Person3"]}
# Returns: Photos with Person1 OR Person2 OR Person3
```

**Syntax:**

```yaml
conditions:
  and:
    - filter1
    - filter2
  or:
    - filter3
    - filter4
```

**Supported Filters:**

All filters from the `filters:` section are supported as leaf conditions:
- `is_favorite: true/false`
- `asset_types: [IMAGE, VIDEO, ...]`
- `camera: {make: "Apple", model: "iPhone 15"}`
- `people: {include: ["PersonName"]}`
- `tags: {include: [...], exclude: [...]}`

**Examples:**

*Simple OR - Multiple People:*
```yaml
conditions:
  or:
    - people: {include: ["Jay"]}
    - people: {include: ["Alice"]}
    - people: {include: ["Bob"]}
```
Matches photos containing ANY of the specified people.

*Simple AND - Favorites from Camera:*
```yaml
conditions:
  and:
    - is_favorite: true
    - camera: {make: "Apple"}
```
Matches photos that are favorites AND taken with an Apple device.

*Nested Conditions - Complex Logic:*
```yaml
conditions:
  and:
    - or:
        - people: {include: ["Jay"]}
        - people: {include: ["Alice"]}
    - or:
        - camera: {make: "Apple"}
        - is_favorite: true
```
Matches photos with (Jay OR Alice) AND (Apple camera OR favorite).

**Performance Considerations:**

- OR conditions require multiple API calls (one per branch), with results merged
- AND conditions can often be combined into a single API call
- Example: Simple OR with 3 people = 3 API calls (~2-3 seconds)
- Complex nested conditions may take longer but are automatically optimized

**Backward Compatibility:**

Rules using the old `filters:` format continue to work unchanged. Internally, they are converted to an AND condition tree. You can migrate to the new format when you need OR logic or more complex conditions.

**Implementation:**

- Condition parsing and tree evaluation: `src/conditions.py`
- Validation: `src/validation.py`
- Tests: `tests/test_conditions.py`

#### Album Sharing

By default, albums created by this application are private to the API key owner. You can configure sharing at two levels:

**Global Default (Environment Variables):**
- `SHARE_WITH_ALL_USERS=true` - Share all albums with every user on the Immich instance
- `SHARE_USER_IDS="email1@example.com,email2@example.com"` - Share all albums with specific users (comma-separated email addresses)
- If both are set, `SHARE_WITH_ALL_USERS` takes precedence

**Per-Rule Override (config.yaml):**
- Add `share_with` field to any rule to override the global default
- Values:
  - `share_with: ALL` - Share this album with all users
  - `share_with: ["user1@example.com", "user2@example.com"]` - Share with specific users
  - `share_with: []` - Keep this album private (even if global sharing is enabled)
  - Omit field - Use global default
- Priority: per-rule > `SHARE_USER_IDS` > `SHARE_WITH_ALL_USERS`

**Example:**
```yaml
rules:
  - id: "family-vacation"
    album_name: "Family Vacation 2025"
    share_with:
      - "dad@example.com"
      - "mom@example.com"
    taken_range_utc:
      start: "2025-07-01T00:00:00.000Z"
      end: "2025-07-15T00:00:00.000Z"
```

**Key Features:**
- **Email-based sharing:** Specify users by email address (automatically resolved to user IDs)
- **Continuous sync:** Sharing is checked and updated on ALL albums every sync run
- **Retroactive updates:** Changing `SHARE_WITH_ALL_USERS` or `SHARE_USER_IDS` updates existing albums on next sync
- **Owner exclusion:** The API key owner is always excluded from the share list automatically
- **Viewer access:** Shared users have read-only access; owner retains full editor privileges

**Use Cases:**
- Family photo servers where all members should see automatically organized albums
- Per-album access control (e.g., vacation photos with family, work photos private)
- Shared Immich instances with selective sharing

**Important Notes:**
- Requires `user.read` permission on the API key to list all users
- User email lookup happens once per sync run (cached)
- If a specified email isn't found, it's treated as a user ID and tried again
- If getting the user list fails, the application logs a warning and continues without sharing
- Dry-run mode skips all sharing operations

**Implementation:**
- Email resolution: `src/rules.py:UserResolver` class
- Sharing update: `src/immich_client.py:update_album_sharing()`
- Per-rule logic: `src/rules.py:_resolve_share_user_ids()`
- Main flow: `src/main.py:run_sync()`

## Important Implementation Details

### Database Optimization

The database is optimized for hundreds of thousands of assets:

1. **WITHOUT ROWID tables**: Used for tables with text primary keys (analyzed_assets, album_memberships) for 20-30% performance improvement
2. **Covering indexes**: Indexes that include all needed columns to satisfy queries without table lookups
3. **WAL mode**: Write-Ahead Logging for better concurrency and performance
4. **Bulk operations**: Uses `executemany()` for batch inserts/deletes
5. **PRAGMA optimizations**: 64MB cache, memory temp storage, mmap I/O

### API Rate Limiting

The Immich client includes automatic delays:
- 100ms delay between paginated requests
- 100ms delay between chunked add/remove operations
- Processes assets in chunks of 500 per API call

### Asset Filtering

Only IMAGE type assets are processed. Videos and other media types are automatically filtered out in the search results.

### Schema Migrations

To add a new migration:

1. Increment `CURRENT_VERSION` in `src/database.py`
2. Create `_migration_vX()` method
3. Add to migrations list in `_run_migrations()`
4. Migrations run automatically on startup

Example:
```python
def _migration_v2(self):
    """Add new feature X."""
    cursor = self.conn.cursor()
    cursor.execute("ALTER TABLE analyzed_assets ADD COLUMN new_field TEXT")
    self.conn.commit()
```

### Error Handling

- Sync runs continue even if individual rules fail
- Errors are logged with full stack traces
- Sync run status is recorded in database
- Application continues running after errors (unless fatal)

## File Organization

- **src/**: All Python source code
- **data/**: SQLite database (created at runtime, in .gitignore)
- **config.yaml**: User's rule configuration (in .gitignore)
- **config.yaml.example**: Template for configuration
- **.env**: Environment variables (in .gitignore)
- **.env.example**: Template for environment setup

## Common Tasks

### Adding a New Date Filter Type

If you need to add support for `fileCreatedAfter`/`fileCreatedBefore`:

1. Update `Rule.__init__()` in `src/rules.py` to parse the new config
2. Update `Rule.execute()` to pass new parameters to API client
3. Update `ImmichClient.search_assets()` to accept and use new parameters
4. Update `config.yaml.example` with example usage

### Adding New Database Tables

1. Create migration function in `src/database.py`
2. Consider using WITHOUT ROWID if primary key is text-based
3. Add appropriate indexes (covering indexes where possible)
4. Run `ANALYZE` at end of migration
5. Add methods to interact with the new table

### Optimizing Performance

For large deployments:
- Increase chunk sizes in API client (currently 500)
- Adjust `SLEEP_INTERVAL_SECONDS` to reduce API load
- Monitor database file size and run `db.optimize()` periodically
- Consider increasing SQLite cache size in `_connect()` method

## CI/CD Workflows

### GitHub Actions Setup

The project uses GitHub Actions for automated releases:

**Release Workflow** (`.github/workflows/release.yml`)
- Triggered on: GitHub release published
- Validates semantic versioning (without 'v' prefix)
- Lints Dockerfile with hadolint
- Builds and publishes to GitHub Container Registry (GHCR)
- Creates multi-tags: version-specific + latest

### Release Process

**Important**: Tags must use semantic versioning WITHOUT 'v' prefix (e.g., `0.0.1`, not `v0.0.1`)

1. Tag a version: `git tag 0.0.1 && git push origin 0.0.1`
2. Create GitHub release from tag
3. Workflow automatically builds and publishes to GHCR

### Development Commands

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/ -v --cov=src

# Code quality checks
black --check src/ tests/
isort --check-only src/ tests/
flake8 src/ tests/

# Lint Dockerfile
docker run --rm -i hadolint/hadolint < Dockerfile
```

## Dependencies

- **requests**: HTTP client for Immich API
- **pyyaml**: Configuration file parsing
- **python-dateutil**: Date/time utilities (for future enhancements)

**Development Dependencies** (requirements-dev.txt):
- **pytest**: Testing framework
- **pytest-cov**: Coverage reporting
- **black**: Code formatting
- **flake8**: Linting
- **isort**: Import sorting
- **mypy**: Type checking (optional)

## License

Apache License 2.0

## API Permissions Required

The Immich API key must have these permissions:
- `asset.read` (search assets)
- `album.read` (list albums)
- `album.create` (create albums)
- `album.update` (update album sharing - **NEW**)
- `albumAsset.create` (add assets to albums)
- `albumAsset.delete` (only for "sync" mode)
- `user.read` (required if using any sharing features: `SHARE_WITH_ALL_USERS`, `SHARE_USER_IDS`, or per-rule `share_with`)
