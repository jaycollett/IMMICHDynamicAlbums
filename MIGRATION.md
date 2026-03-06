# Migration Guide

## Schema Migrations

The database uses an automatic migration system. Migrations run on startup.

### Adding a New Migration

1. Increment `CURRENT_VERSION` in `src/database.py`
2. Create `_migration_vX()` method
3. Add to migrations list in `_run_migrations()`

Example:
```python
def _migration_v2(self):
    """Add new feature X."""
    cursor = self.conn.cursor()
    cursor.execute("ALTER TABLE analyzed_assets ADD COLUMN new_field TEXT")
    self.conn.commit()
```

### Testing Migrations

```python
from src.database import Database

db = Database("test.db")
cursor = db.conn.cursor()
cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
print(f"Schema version: {cursor.fetchone()[0]}")
db.close()
```

## Adding New Database Tables

1. Create migration function in `src/database.py`
2. Consider using WITHOUT ROWID if primary key is text-based
3. Add appropriate indexes (covering indexes where possible)
4. Run `ANALYZE` at end of migration
5. Add methods to interact with the new table

## Adding a New Date Filter Type

If you need to add support for a new date filter (e.g., `fileCreatedAfter`/`fileCreatedBefore`):

1. Update `Rule.__init__()` in `src/rules.py` to parse the new config
2. Update `Rule.execute()` to pass new parameters to API client
3. Update `ImmichClient.search_assets()` to accept and use new parameters
4. Update `config.yaml.example` with example usage
