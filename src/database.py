"""
SQLite database for tracking analyzed assets and their album memberships.
"""
import logging
import sqlite3
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set


logger = logging.getLogger(__name__)


class Database:
    """SQLite database for tracking asset analysis and album memberships."""

    # Current schema version
    CURRENT_VERSION = 2

    def __init__(self, db_path: str = "data/immich_albums.db"):
        """
        Initialize the database.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.conn = None
        self._connect()
        self._run_migrations()

    def _connect(self):
        """Connect to the database."""
        logger.info(f"Connecting to database: {self.db_path}")
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Optimize SQLite for performance with large datasets
        cursor = self.conn.cursor()

        # Enable Write-Ahead Logging for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")

        # Increase cache size to 64MB for better performance
        cursor.execute("PRAGMA cache_size=-64000")

        # Use memory for temporary tables and indexes
        cursor.execute("PRAGMA temp_store=MEMORY")

        # Optimize for speed over durability (safe for this use case)
        cursor.execute("PRAGMA synchronous=NORMAL")

        # Enable memory-mapped I/O (256MB)
        cursor.execute("PRAGMA mmap_size=268435456")

        logger.debug("SQLite optimizations applied")

    def _get_schema_version(self) -> int:
        """
        Get the current schema version.

        Returns:
            Current schema version, or 0 if not initialized
        """
        cursor = self.conn.cursor()

        # Check if schema_version table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_version'
        """)

        if not cursor.fetchone():
            return 0

        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        return row["version"] if row else 0

    def _set_schema_version(self, version: int):
        """
        Set the schema version.

        Args:
            version: Schema version to set
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO schema_version (version, applied_at)
            VALUES (?, ?)
        """, (version, now))

        self.conn.commit()
        logger.info(f"Schema version set to {version}")

    def _migration_v1(self):
        """Initial schema migration with optimizations for large datasets."""
        logger.info("Applying migration v1: Initial schema (optimized for 100k+ assets)")
        cursor = self.conn.cursor()

        # Create schema_version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL
            )
        """)

        # Table to track analyzed assets
        # Use WITHOUT ROWID for faster lookups on text primary key
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyzed_assets (
                asset_id TEXT PRIMARY KEY,
                first_seen TIMESTAMP NOT NULL,
                last_analyzed TIMESTAMP NOT NULL,
                asset_type TEXT NOT NULL DEFAULT 'IMAGE',
                taken_date TEXT
            ) WITHOUT ROWID
        """)

        # Index for filtering by asset type (if we want to query by type)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyzed_assets_type
            ON analyzed_assets(asset_type)
        """)

        # Index for time-based queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyzed_assets_last_analyzed
            ON analyzed_assets(last_analyzed)
        """)

        # Table to track album memberships
        # Optimized for lookups by rule+album and by asset
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS album_memberships (
                rule_id TEXT NOT NULL,
                album_id TEXT NOT NULL,
                album_name TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                added_at TIMESTAMP NOT NULL,
                PRIMARY KEY(rule_id, album_id, asset_id)
            ) WITHOUT ROWID
        """)

        # Covering index for finding assets by album
        # This allows queries to be satisfied entirely from the index
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_album_memberships_album_assets
            ON album_memberships(album_id, asset_id)
        """)

        # Index for finding all albums an asset belongs to
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_album_memberships_asset
            ON album_memberships(asset_id)
        """)

        # Table to track sync runs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                status TEXT NOT NULL,
                rules_processed INTEGER DEFAULT 0,
                assets_added INTEGER DEFAULT 0,
                assets_removed INTEGER DEFAULT 0,
                error_message TEXT
            )
        """)

        # Index for querying recent sync runs
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_sync_runs_started
            ON sync_runs(started_at DESC)
        """)

        self.conn.commit()

        # Run ANALYZE to help query planner optimize queries
        logger.debug("Running ANALYZE to optimize query planning")
        cursor.execute("ANALYZE")

    def _migration_v2(self):
        """Add match_type column for fuzzy matching support."""
        logger.info("Applying migration v2: Add match_type column for fuzzy matching")
        cursor = self.conn.cursor()

        # Add match_type column with default 'exact' for existing records
        cursor.execute("""
            ALTER TABLE album_memberships
            ADD COLUMN match_type TEXT NOT NULL DEFAULT 'exact'
        """)

        # Add index for querying by match type
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_album_memberships_match_type
            ON album_memberships(match_type)
        """)

        self.conn.commit()

        # Run ANALYZE to update query planner statistics
        cursor.execute("ANALYZE")
        logger.info("Migration v2 complete: match_type column added")

    def _run_migrations(self):
        """Run database migrations."""
        current_version = self._get_schema_version()
        logger.info(f"Current database schema version: {current_version}")

        # Define migrations in order
        migrations: List[tuple[int, Callable]] = [
            (1, self._migration_v1),
            (2, self._migration_v2),
            # Add future migrations here:
            # (3, self._migration_v3),
        ]

        # Apply migrations that haven't been applied yet
        for version, migration_func in migrations:
            if current_version < version:
                logger.info(f"Applying migration to version {version}")
                try:
                    migration_func()
                    self._set_schema_version(version)
                    logger.info(f"Successfully migrated to version {version}")
                except Exception as e:
                    logger.error(f"Migration to version {version} failed: {str(e)}")
                    self.conn.rollback()
                    raise

        if current_version < self.CURRENT_VERSION:
            logger.info(f"Database migrations complete. Now at version {self.CURRENT_VERSION}")
        else:
            logger.info("Database schema is up to date")

    def record_analyzed_asset(
        self,
        asset_id: str,
        asset_type: str = "IMAGE",
        taken_date: Optional[str] = None
    ):
        """
        Record that an asset has been analyzed.

        Args:
            asset_id: ID of the asset
            asset_type: Type of the asset (IMAGE, VIDEO, etc.)
            taken_date: ISO timestamp when asset was taken
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO analyzed_assets (asset_id, first_seen, last_analyzed, asset_type, taken_date)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                last_analyzed = ?,
                asset_type = ?,
                taken_date = ?
        """, (asset_id, now, now, asset_type, taken_date, now, asset_type, taken_date))

        self.conn.commit()

    def record_album_membership(
        self,
        rule_id: str,
        album_id: str,
        album_name: str,
        asset_ids: Set[str],
        match_type: str = 'exact'
    ):
        """
        Record assets that have been added to an album.
        Optimized for bulk inserts using executemany.

        Args:
            rule_id: ID of the rule that triggered this
            album_id: ID of the album
            album_name: Name of the album
            asset_ids: Set of asset IDs added to the album
            match_type: Type of match ('exact' or 'fuzzy')
        """
        if not asset_ids:
            return

        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        # Use executemany for better performance with large batches
        values = [(rule_id, album_id, album_name, asset_id, now, match_type) for asset_id in asset_ids]
        cursor.executemany("""
            INSERT OR IGNORE INTO album_memberships
            (rule_id, album_id, album_name, asset_id, added_at, match_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, values)

        self.conn.commit()
        logger.debug(f"Recorded {len(asset_ids)} album memberships for rule {rule_id} (match_type={match_type})")

    def get_album_assets_for_rule(self, rule_id: str, album_id: str) -> Dict[str, str]:
        """
        Get all assets that were added to an album by a specific rule.

        Args:
            rule_id: ID of the rule
            album_id: ID of the album

        Returns:
            Dict mapping asset_id → match_type ('exact' or 'fuzzy')
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT asset_id, match_type FROM album_memberships
            WHERE rule_id = ? AND album_id = ?
        """, (rule_id, album_id))

        return {row["asset_id"]: row["match_type"] for row in cursor.fetchall()}

    def remove_album_memberships(
        self,
        rule_id: str,
        album_id: str,
        asset_ids: Set[str]
    ):
        """
        Remove album membership records.
        Optimized for bulk deletes.

        Args:
            rule_id: ID of the rule
            album_id: ID of the album
            asset_ids: Set of asset IDs to remove
        """
        if not asset_ids:
            return

        cursor = self.conn.cursor()

        # Use executemany for better performance with large batches
        values = [(rule_id, album_id, asset_id) for asset_id in asset_ids]
        cursor.executemany("""
            DELETE FROM album_memberships
            WHERE rule_id = ? AND album_id = ? AND asset_id = ?
        """, values)

        self.conn.commit()
        logger.debug(f"Removed {len(asset_ids)} album membership records")

    def start_sync_run(self) -> int:
        """
        Record the start of a sync run.

        Returns:
            ID of the sync run
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO sync_runs (started_at, status)
            VALUES (?, 'running')
        """, (now,))

        self.conn.commit()
        return cursor.lastrowid

    def complete_sync_run(
        self,
        sync_run_id: int,
        status: str,
        rules_processed: int = 0,
        assets_added: int = 0,
        assets_removed: int = 0,
        error_message: Optional[str] = None
    ):
        """
        Mark a sync run as completed.

        Args:
            sync_run_id: ID of the sync run
            status: Status (success, error)
            rules_processed: Number of rules processed
            assets_added: Number of assets added
            assets_removed: Number of assets removed
            error_message: Optional error message if failed
        """
        cursor = self.conn.cursor()
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            UPDATE sync_runs SET
                completed_at = ?,
                status = ?,
                rules_processed = ?,
                assets_added = ?,
                assets_removed = ?,
                error_message = ?
            WHERE id = ?
        """, (now, status, rules_processed, assets_added, assets_removed, error_message, sync_run_id))

        self.conn.commit()

    def get_last_sync_run(self) -> Optional[Dict]:
        """
        Get the most recent sync run.

        Returns:
            Dict with sync run information, or None if no runs exist
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM sync_runs
            ORDER BY started_at DESC
            LIMIT 1
        """)

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def optimize(self):
        """
        Optimize the database for better performance.
        Should be run periodically (e.g., after large batches of operations).
        """
        cursor = self.conn.cursor()
        logger.info("Optimizing database...")

        # Update query planner statistics
        cursor.execute("ANALYZE")

        # Check if VACUUM is needed (only if database has grown significantly)
        cursor.execute("PRAGMA page_count")
        page_count = cursor.fetchone()[0]

        cursor.execute("PRAGMA freelist_count")
        freelist_count = cursor.fetchone()[0]

        # If more than 10% of pages are free, run VACUUM
        if freelist_count > page_count * 0.1:
            logger.info(f"Running VACUUM (freelist: {freelist_count}/{page_count} pages)")
            cursor.execute("VACUUM")
        else:
            logger.debug(f"VACUUM not needed (freelist: {freelist_count}/{page_count} pages)")

        logger.info("Database optimization complete")

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
