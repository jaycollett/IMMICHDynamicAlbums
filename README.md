# Immich Dynamic Albums

[![Release](https://img.shields.io/github/v/release/jaycollett/IMMICHDynamicAlbums)](https://github.com/jaycollett/IMMICHDynamicAlbums/releases/latest)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-blue)](https://github.com/jaycollett/IMMICHDynamicAlbums/pkgs/container/immichdynamicalbums)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

A powerful Docker-based Python application that automatically creates and manages albums in [Immich](https://immich.app/) based on intelligent rules. Perfect for organizing photos by holidays, birthdays, events, people, and more—without manual effort.

## ✨ Key Features

### 🎯 Smart Album Organization
- **🔁 Recurring Rules**: Automatically create albums for annual events (birthdays, holidays) across multiple years
- **🎲 Fuzzy Matching** _(NEW in v0.5.0)_: Automatically includes related photos taken nearby in time (60 min) and location (100m)
- **👥 People Filtering**: Create albums based on who's in the photos with powerful AND/OR logic
- **🧠 Advanced Conditions**: Complex filtering with nested AND/OR logic for precise control
- **🌍 Timezone-Aware**: Recurring rules respect local timezones for accurate date matching

### 🔐 Sharing & Permissions
- **👨‍👩‍👧‍👦 Album Sharing**: Automatically share albums with all users or specific people
- **🎛️ Per-Rule Control**: Override global sharing settings on individual rules
- **📧 Email-Based**: Share with users by email address (auto-resolved to IDs)

### 🛠️ Robust & Reliable
- **🔄 Two Sync Modes**: `add_only` (safe) or `sync` (full synchronization)
- **💾 SQLite Database**: Tracks assets, memberships, and match types with automatic migrations
- **🐳 Docker-Ready**: Easy deployment with Docker and docker-compose
- **🧪 Dry-Run Mode**: Test rules without making changes
- **⚡ Performance**: Parallel processing, rate limiting, and optimized database queries

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
  - [Fuzzy Matching](#fuzzy-matching-new)
  - [Recurring Rules](#recurring-rules)
  - [AND/OR Conditions](#andor-conditions)
  - [People Filtering](#people-filtering)
  - [Album Sharing](#album-sharing)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- An [Immich](https://immich.app/) instance with API access
- Immich API key with permissions:
  - `asset.read` - Search assets
  - `album.read` - List albums
  - `album.create` - Create albums
  - `album.update` - Update album sharing _(for sharing features)_
  - `albumAsset.create` - Add assets to albums
  - `albumAsset.delete` - Remove assets _(only for `sync` mode)_
  - `user.read` - List users _(only for sharing features)_

### 1. Create an Immich API Key

1. Log into your Immich instance
2. Go to **Account Settings → API Keys**
3. Create a new API key with the required permissions
4. Save the API key securely

### 2. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/jaycollett/IMMICHDynamicAlbums.git
cd IMMICHDynamicAlbums

# Copy example configuration files
cp .env.example .env
cp config.yaml.example config.yaml

# Edit .env with your Immich details
nano .env
```

Edit `.env`:
```bash
IMMICH_API_KEY=your-api-key-here
IMMICH_BASE_URL=https://your-immich-instance.com/api
SLEEP_INTERVAL_SECONDS=3600  # Check every hour
LOG_LEVEL=INFO
DEFAULT_TIMEZONE=America/New_York  # Your local timezone

# Optional: Enable fuzzy matching globally
ALLOW_FUZZY_MATCH=false

# Optional: Share albums with all users
SHARE_WITH_ALL_USERS=false

# Optional: Share albums with specific users (comma-separated emails)
SHARE_USER_IDS=user1@example.com,user2@example.com
```

### 3. Configure Your Rules

Edit `config.yaml`:

```yaml
mode: "add_only"  # or "sync"

rules:
  # Simple date-based album
  - id: "summer-vacation-2025"
    album_name: "Summer Vacation 2025"
    description: "Family vacation photos"
    taken_range_utc:
      start: "2025-07-01T00:00:00.000Z"
      end: "2025-07-15T00:00:00.000Z"

  # Recurring birthday with fuzzy matching
  - id: "birthday"
    recurring: true
    fuzzy_match: true  # Include nearby photos!
    month_day: "12-06"
    timezone: "America/New_York"
    duration_days: 1
    album_name_template: "Birthday Party {year}"
    year_range: [2000, 2030]
    conditions:
      or:
        - people: {include: ["Mom"]}
        - people: {include: ["Dad"]}
        - people: {include: ["Sister"]}
```

### 4. Deploy with Docker

```bash
# Pull and start the container
docker compose pull
docker compose up -d

# View logs
docker compose logs -f

# Stop the container
docker compose down
```

---

## 🎨 Features

### 🎲 Fuzzy Matching _(NEW in v0.5.0)_

**Automatically include related photos** that don't exactly match your rules but were taken nearby in time and location.

**Perfect for:**
- 🎂 **Birthday parties**: Captures untagged friends and guests
- 🎄 **Holiday gatherings**: Includes everyone at the event
- 🏖️ **Vacations**: Finds related photos from the same location

**How it works:**
- Finds photos within **60 minutes** of exact matches
- Within **100 meters** GPS distance (if GPS data available)
- Gracefully handles missing GPS/timestamps
- Database tracks exact vs fuzzy matches separately

**Configuration:**

```yaml
# Enable globally for all rules
# .env file:
ALLOW_FUZZY_MATCH=true

# Or enable per-rule:
rules:
  - id: "party"
    fuzzy_match: true  # Enable for this rule
    album_name: "Party 2025"
    # ...

  - id: "work-event"
    fuzzy_match: false  # Explicitly disable
    album_name: "Work Conference"
    # ...
```

**Priority:** Per-rule `fuzzy_match` overrides global `ALLOW_FUZZY_MATCH`

---

### 🔁 Recurring Rules

Define **one rule** that automatically creates albums for **multiple years**. Perfect for birthdays, holidays, and annual events.

**Example: Christmas albums for 25 years**

```yaml
rules:
  - id: "christmas"
    recurring: true
    month_day: "12-25"
    timezone: "America/New_York"  # Respects local calendar day
    duration_days: 1
    album_name_template: "Christmas {year}"
    year_range: [2000, 2025]
    filters:
      asset_types: [IMAGE, VIDEO]
```

This automatically creates:
- Christmas 2000
- Christmas 2001
- ...
- Christmas 2025

**Required fields:**
- `recurring: true`
- `month_day`: Format "MM-DD" (e.g., "12-25")
- `timezone`: IANA timezone (e.g., "America/New_York", "Europe/London")
- `album_name_template`: Use `{year}` placeholder
- `year_range`: [start_year, end_year] inclusive

**Optional fields:**
- `duration_days`: Number of days (default: 1)
- `description`: Album description
- `filters` or `conditions`: Same as regular rules

**Timezone support:**
Photos are matched to the **local calendar day**, not UTC. A photo taken at 11 PM EST on Christmas is matched to Christmas (not December 26 UTC).

**Common timezones:**
- `America/New_York` - Eastern (EST/EDT)
- `America/Chicago` - Central (CST/CDT)
- `America/Denver` - Mountain (MST/MDT)
- `America/Los_Angeles` - Pacific (PST/PDT)
- `America/Phoenix` - Arizona (no DST)
- `Europe/London` - UK (GMT/BST)
- `UTC` - Universal time

---

### 🧠 AND/OR Conditions

Create **complex filtering logic** with unlimited nesting. Perfect for "photos with ANY family member" or "favorites from iPhone OR videos with people".

**Key difference from filters:**
- **`filters:`** _(old format)_: Implicit AND logic, all conditions must match
- **`conditions:`** _(new format)_: Explicit AND/OR with unlimited nesting

**Simple OR - Photos with ANY family member:**

```yaml
rules:
  - id: "family-photos"
    album_name: "Family 2025"
    conditions:
      or:
        - people: {include: ["Mom"]}
        - people: {include: ["Dad"]}
        - people: {include: ["Sister"]}
        - people: {include: ["Brother"]}
```

**Simple AND - Favorites from iPhone:**

```yaml
rules:
  - id: "iphone-favorites"
    album_name: "iPhone Favorites"
    conditions:
      and:
        - is_favorite: true
        - camera: {make: "Apple"}
```

**Complex nested logic:**

```yaml
rules:
  - id: "complex-album"
    album_name: "Vacation Photos"
    conditions:
      and:
        # Must be IMAGE or VIDEO
        - asset_types: [IMAGE, VIDEO]
        # AND (Mom OR Dad)
        - or:
            - people: {include: ["Mom"]}
            - people: {include: ["Dad"]}
        # AND (Favorite OR from iPhone)
        - or:
            - is_favorite: true
            - camera: {make: "Apple"}
```

**Supported filters in conditions:**
- `is_favorite: true/false`
- `asset_types: [IMAGE, VIDEO, ...]`
- `camera: {make: "Apple", model: "iPhone 15"}`
- `people: {include: ["Name"]}`
- `tags: {include: [...], exclude: [...]}`

**Cannot mix:** You cannot use both `filters:` and `conditions:` in the same rule.

---

### 👥 People Filtering

Filter photos based on **who's in them** using Immich's face recognition.

**Important: Immich API People Behavior**

The Immich API uses **AND logic** for multiple people in `filters.people.include`:

```yaml
# ❌ This finds photos with ALL three people (AND logic)
filters:
  people:
    include: ["Mom", "Dad", "Sister"]
# Returns: Photos with Mom AND Dad AND Sister (all three together)
```

**For "ANY of these people" (OR logic), use conditions:**

```yaml
# ✅ This finds photos with ANY of the three people (OR logic)
conditions:
  or:
    - people: {include: ["Mom"]}
    - people: {include: ["Dad"]}
    - people: {include: ["Sister"]}
# Returns: Photos with Mom OR Dad OR Sister
```

**Birthday example with fuzzy matching:**

```yaml
rules:
  - id: "ethan-birthday"
    recurring: true
    fuzzy_match: true  # Include untagged party guests!
    month_day: "12-06"
    timezone: "America/New_York"
    album_name_template: "Bob's Birthday {year}"
    year_range: [2000, 2030]
    conditions:
      and:
        - asset_types: [IMAGE, VIDEO]
        - or:
            - people: {include: ["Bob"]}
            - people: {include: ["Mom"]}
            - people: {include: ["Dad"]}
```

This creates albums with:
- **Exact matches**: Photos with Bob, Mom, or Dad tagged
- **Fuzzy matches**: Untagged photos from the same party (within 60 min/100m)

---

### 👨‍👩‍👧‍👦 Album Sharing

Automatically share albums with other Immich users.

**Global sharing (all albums):**

```bash
# .env file

# Share with ALL users
SHARE_WITH_ALL_USERS=true

# OR share with specific users (comma-separated emails)
SHARE_USER_IDS=dad@example.com,mom@example.com,sister@example.com
```

**Per-rule sharing (overrides global):**

```yaml
rules:
  # Share with family
  - id: "family-vacation"
    album_name: "Vacation 2025"
    share_with:
      - dad@example.com
      - mom@example.com
    # ...

  # Share with everyone
  - id: "holiday-party"
    album_name: "Holiday Party"
    share_with: ALL
    # ...

  # Keep private (even if global sharing enabled)
  - id: "personal"
    album_name: "Personal Photos"
    share_with: []
    # ...

  # Use global default (omit share_with)
  - id: "trip"
    album_name: "Road Trip"
    # Uses SHARE_WITH_ALL_USERS or SHARE_USER_IDS from .env
```

**Features:**
- **Retroactive updates**: Changing sharing settings updates existing albums
- **Continuous sync**: Sharing checked/updated on every sync run
- **Owner excluded**: API key owner is automatically excluded from share list
- **Viewer access**: Shared users have read-only access
- **Email-based**: Specify users by email (auto-resolved to IDs)

**Priority:** `per-rule share_with` > `SHARE_USER_IDS` > `SHARE_WITH_ALL_USERS`

---

## ⚙️ Configuration

### Environment Variables (.env)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IMMICH_API_KEY` | **Yes** | - | Your Immich API key |
| `IMMICH_BASE_URL` | **Yes** | - | Immich API URL (must end with `/api`) |
| `SLEEP_INTERVAL_SECONDS` | No | `3600` | Seconds between sync runs (3600 = 1 hour) |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DEFAULT_TIMEZONE` | No | `America/New_York` | Default IANA timezone for recurring rules |
| `ALLOW_FUZZY_MATCH` | No | `false` | Enable fuzzy matching globally |
| `SHARE_WITH_ALL_USERS` | No | `false` | Share all albums with all users |
| `SHARE_USER_IDS` | No | - | Comma-separated emails to share with |

### Rule Configuration (config.yaml)

#### Mode

```yaml
mode: "add_only"  # or "sync"
```

- **`add_only`** _(recommended)_: Only adds new matching assets. Safe, never removes.
- **`sync`**: Full sync - adds new matches AND removes assets that no longer match.

#### Rule Structure

Every rule must have:
- `id`: Unique identifier (alphanumeric, hyphens, underscores)
- `album_name`: Name of the album in Immich

Optional fields:
- `description`: Album description
- `fuzzy_match`: `true` or `false` to enable/disable fuzzy matching
- `share_with`: Share settings (overrides global)
- Date filters: `taken_range_utc` or `created_range_utc`
- Filters: `filters:` _(old format, implicit AND)_
- Conditions: `conditions:` _(new format, explicit AND/OR)_

**Cannot use both `filters:` and `conditions:` in the same rule.**

---

## 📚 Usage Examples

### Example 1: Simple Event Album

```yaml
rules:
  - id: "graduation"
    album_name: "Graduation 2025"
    description: "College graduation ceremony"
    taken_range_utc:
      start: "2025-05-15T00:00:00.000Z"
      end: "2025-05-16T00:00:00.000Z"
    filters:
      asset_types: [IMAGE, VIDEO]
```

### Example 2: Recurring Holiday

```yaml
rules:
  - id: "thanksgiving"
    recurring: true
    month_day: "11-24"  # 4th Thursday (approximate)
    timezone: "America/New_York"
    duration_days: 1
    album_name_template: "Thanksgiving {year}"
    year_range: [2000, 2030]
    filters:
      asset_types: [IMAGE, VIDEO]
```

### Example 3: Birthday with Fuzzy Matching

```yaml
rules:
  - id: "birthday-party"
    recurring: true
    fuzzy_match: true  # Capture untagged guests!
    month_day: "07-15"
    timezone: "America/Chicago"
    duration_days: 1
    album_name_template: "Sarah's Birthday {year}"
    year_range: [2010, 2030]
    share_with:
      - family@example.com
      - friends@example.com
    conditions:
      or:
        - people: {include: ["Sarah"]}
        - people: {include: ["Mom"]}
        - people: {include: ["Dad"]}
```

### Example 4: Complex Filtering

```yaml
rules:
  - id: "best-vacation-photos"
    album_name: "Best Vacation Shots"
    description: "Favorite photos from Hawaii trip"
    taken_range_utc:
      start: "2025-08-01T00:00:00.000Z"
      end: "2025-08-15T00:00:00.000Z"
    conditions:
      and:
        - asset_types: [IMAGE]
        # Favorites OR from iPhone
        - or:
            - is_favorite: true
            - camera: {make: "Apple"}
        # With family members
        - or:
            - people: {include: ["Mom"]}
            - people: {include: ["Dad"]}
            - people: {include: ["Sister"]}
```

### Example 5: Celebration Date Override

Sometimes celebrations happen on different days than actual dates. You can have both!

```yaml
rules:
  # Actual birthday (recurring)
  - id: "birthday"
    recurring: true
    fuzzy_match: true
    month_day: "12-06"
    timezone: "America/New_York"
    album_name_template: "Birthday {year}"
    year_range: [2000, 2030]
    conditions:
      or:
        - people: {include: ["Child"]}

  # Party was on a different day
  - id: "birthday-party-2025"
    fuzzy_match: true
    album_name: "Birthday 2025"  # Same album name!
    taken_range_utc:
      start: "2025-12-14T05:00:00.000Z"
      end: "2025-12-15T05:00:00.000Z"
    conditions:
      or:
        - people: {include: ["Child"]}
```

Both rules add to the same album because they share the `album_name`!

---

## 🗑️ Utility Scripts

The repository includes helpful one-off utility scripts in the `util_scripts/` folder for library maintenance tasks.

### Garbage Image Detection

Identify potentially unwanted "garbage" images - accidental captures, blurry photos, pocket shots, etc.

**Quick start:**
```bash
# Install optional dependencies
pip install -r requirements-optional.txt

# Test with conservative settings
python util_scripts/find_garbage_images.py --limit 100 --dry-run

# Create album with flagged images
python util_scripts/find_garbage_images.py
```

**Features:**
- Blur detection using computer vision (OpenCV)
- Darkness detection (pocket shots)
- Low contrast detection (blank images)
- Optional resolution filtering
- Configurable thresholds

**See full documentation:** [util_scripts/GARBAGE_DETECTION.md](util_scripts/GARBAGE_DETECTION.md)

---

## 🐳 Usage

### Docker Compose (Recommended)

#### Continuous Mode (Default)
```bash
docker compose up -d
docker compose logs -f
```

#### One-Time Run
```bash
docker compose run --rm immich-dynamic-albums python src/main.py --once
```

#### Dry-Run Mode (Test without changes)
```bash
docker compose run --rm immich-dynamic-albums python src/main.py --dry-run --once
```

### Local Development (Without Docker)

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export IMMICH_API_KEY=your-api-key
export IMMICH_BASE_URL=https://your-immich.com/api
export DEFAULT_TIMEZONE=America/New_York

# Run
python src/main.py --config config.yaml --once
```

### Command-Line Options

```bash
python src/main.py [OPTIONS]

Options:
  --config PATH    Path to config file (default: config.yaml)
  --dry-run       Test mode - no changes made
  --once          Run once and exit (don't loop)
  --db-path PATH  Database path (default: data/immich_albums.db)
```

---

## 🛠️ Development

### Project Structure

```
IMMICHDynamicAlbums/
├── src/
│   ├── main.py            # Application entry point
│   ├── immich_client.py   # Immich API client
│   ├── database.py        # SQLite with migrations
│   ├── rules.py           # Rule engine
│   ├── fuzzy_matcher.py   # Fuzzy matching logic
│   ├── conditions.py      # AND/OR condition trees
│   └── validation.py      # Config validation
├── tests/                 # Unit tests
├── data/                  # Database (created at runtime)
├── config.yaml.example    # Example configuration
├── .env.example           # Example environment
├── requirements.txt       # Dependencies
├── requirements-dev.txt   # Dev dependencies
├── Dockerfile            # Docker image
├── docker-compose.yml    # Docker Compose
└── README.md            # This file
```

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/ -v --cov=src

# Check code quality
black --check src/ tests/
isort --check-only src/ tests/
flake8 src/ tests/

# Lint Dockerfile
docker run --rm -i hadolint/hadolint < Dockerfile
```

### Database Schema

The application uses SQLite with automatic migrations:

**Tables:**
- `analyzed_assets`: Tracks processed assets
- `album_memberships`: Tracks asset-album relationships with `match_type` ('exact' or 'fuzzy')
- `sync_runs`: History of sync operations
- `schema_version`: Migration tracking

**Adding migrations:**

1. Increment `CURRENT_VERSION` in `src/database.py`
2. Add `_migration_vX()` method
3. Add to migrations list in `_run_migrations()`

Migrations run automatically on startup.

---

## 🐛 Troubleshooting

### Application Not Syncing

**Check logs:**
```bash
docker compose logs -f
```

**Common issues:**
- ❌ API key doesn't have required permissions
- ❌ `IMMICH_BASE_URL` doesn't end with `/api`
- ❌ Firewall/network blocking API access

**Test with dry-run:**
```bash
docker compose run --rm immich-dynamic-albums python src/main.py --dry-run --once
```

### Assets Not Added to Albums

**Verify:**
- ✅ Assets match date ranges (check timestamps in Immich)
- ✅ Timestamps are ISO 8601 with UTC (`Z` suffix)
- ✅ Photos have correct taken/created dates
- ✅ People are tagged correctly in Immich
- ✅ Rule logic is correct (test with conditions)

**Check database:**
```bash
docker compose exec immich-dynamic-albums ls -lh data/
sqlite3 data/immich_albums.db "SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 5;"
```

### Fuzzy Matching Not Working

**Verify:**
- ✅ `fuzzy_match: true` in rule OR `ALLOW_FUZZY_MATCH=true` in .env
- ✅ Exact matches exist first (fuzzy finds photos near exact matches)
- ✅ Photos have timestamps (check EXIF data)
- ✅ GPS data available for location matching (optional)

**Check logs for:**
```
Running fuzzy matching for rule <rule-id> (X exact matches)
Fuzzy matching found Y related assets
```

### People Filtering Issues

**Common mistakes:**

❌ **Using filters for OR logic:**
```yaml
# This uses AND logic (all three people must be present)
filters:
  people:
    include: ["Mom", "Dad", "Sister"]
```

✅ **Use conditions for OR logic:**
```yaml
# This uses OR logic (any one person)
conditions:
  or:
    - people: {include: ["Mom"]}
    - people: {include: ["Dad"]}
    - people: {include: ["Sister"]}
```

**Verify:**
- ✅ People names exactly match Immich (case-sensitive)
- ✅ Face recognition enabled in Immich
- ✅ Photos have faces tagged

### Sharing Not Working

**Verify:**
- ✅ API key has `user.read` and `album.update` permissions
- ✅ Email addresses exactly match Immich users
- ✅ Shared users exist in Immich
- ✅ Not in dry-run mode (sharing skipped in dry-run)

**Check logs:**
```
Fetched X users from Immich
Updating sharing for 'Album Name': Y user(s)
```

### Database Errors

**Issues:**
- ❌ `data/` directory not writable
- ❌ Database locked by another process
- ❌ Corrupted database

**Fix:**
```bash
# Check permissions
ls -la data/

# Stop all containers
docker compose down

# Remove database (WARNING: loses history)
rm data/immich_albums.db

# Restart
docker compose up -d
```

### Performance Issues

**For large libraries (100k+ photos):**

1. **Increase sleep interval:**
   ```bash
   SLEEP_INTERVAL_SECONDS=7200  # 2 hours
   ```

2. **Limit year ranges:**
   ```yaml
   year_range: [2020, 2025]  # Instead of [1990, 2030]
   ```

3. **Disable fuzzy matching for large albums:**
   ```yaml
   fuzzy_match: false
   ```

4. **Use specific date ranges:**
   Instead of broad filters, use precise date ranges when possible.

---

## 🚀 CI/CD

### GitHub Actions Workflow

**`.github/workflows/release.yml`** runs automatically on release:

1. ✅ Validates semantic version (must be `X.Y.Z` without `v` prefix)
2. ✅ Lints Dockerfile with hadolint
3. ✅ Builds Docker image
4. ✅ Publishes to GitHub Container Registry (GHCR)
5. ✅ Tags as both version-specific and `latest`

### Creating a Release

```bash
# Commit your changes
git add .
git commit -m "Description"
git push

# Create version tag (no 'v' prefix!)
git tag 0.5.0
git push origin 0.5.0

# Create GitHub release from tag
gh release create 0.5.0 --title "v0.5.0" --notes "Release notes"
```

The workflow automatically builds and pushes:
- `ghcr.io/jaycollett/immichdynamicalbums:0.5.0`
- `ghcr.io/jaycollett/immichdynamicalbums:latest`

---

## 📄 License

**Apache License 2.0** - See [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Check code quality: `black src/ tests/`
6. Commit: `git commit -m "Add amazing feature"`
7. Push: `git push origin feature/amazing-feature`
8. Open a Pull Request

All PRs automatically run tests and code quality checks.

---

## 🙏 Acknowledgments

Built for the [Immich](https://immich.app/) photo management platform.

---

## 📬 Support

- 🐛 **Issues**: [GitHub Issues](https://github.com/jaycollett/IMMICHDynamicAlbums/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/jaycollett/IMMICHDynamicAlbums/discussions)
- 📖 **Documentation**: See `CLAUDE.md` for development guidelines

---

**Made with ❤️ for automated photo organization**
