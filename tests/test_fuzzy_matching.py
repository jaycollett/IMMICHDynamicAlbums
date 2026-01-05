"""
Unit tests for fuzzy matching functionality.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from fuzzy_matcher import FuzzyMatcher, AssetMetadata
from database import Database


class TestFuzzyMatcher:
    """Tests for the FuzzyMatcher class."""

    def test_haversine_distance(self):
        """Test haversine distance calculation with known coordinates."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        # Test: New York to Los Angeles (approximately 3944 km)
        ny_lat, ny_lon = 40.7128, -74.0060
        la_lat, la_lon = 34.0522, -118.2437

        distance = fuzzy_matcher._haversine_distance(ny_lat, ny_lon, la_lat, la_lon)

        # Should be approximately 3,944,000 meters (3944 km)
        assert 3_900_000 < distance < 4_000_000

    def test_haversine_distance_close_points(self):
        """Test haversine distance for nearby points (within 100 meters)."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        # Two points very close together (approximately 50 meters apart)
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 40.7132, -74.0060  # Slightly north

        distance = fuzzy_matcher._haversine_distance(lat1, lon1, lat2, lon2)

        # Should be less than 100 meters
        assert distance < 100

    def test_calculate_time_boundaries(self):
        """Test time window expansion logic."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client, time_window_minutes=60)

        # Create test metadata
        exact_metadata = [
            AssetMetadata("asset1", datetime(2025, 6, 15, 14, 30), None, None),
            AssetMetadata("asset2", datetime(2025, 6, 15, 16, 45), None, None),
        ]

        # Empty date filters (no clamping)
        start, end = fuzzy_matcher._calculate_time_boundaries(exact_metadata, {})

        # Should expand by 60 minutes on each side
        expected_start = datetime(2025, 6, 15, 13, 30)  # 14:30 - 60min
        expected_end = datetime(2025, 6, 15, 17, 45)    # 16:45 + 60min

        assert start == expected_start
        assert end == expected_end

    def test_calculate_time_boundaries_single_asset(self):
        """Test time window expansion with single asset."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client, time_window_minutes=30)

        exact_metadata = [
            AssetMetadata("asset1", datetime(2025, 12, 25, 12, 0), None, None),
        ]

        # Empty date filters (no clamping)
        start, end = fuzzy_matcher._calculate_time_boundaries(exact_metadata, {})

        expected_start = datetime(2025, 12, 25, 11, 30)  # 12:00 - 30min
        expected_end = datetime(2025, 12, 25, 12, 30)    # 12:00 + 30min

        assert start == expected_start
        assert end == expected_end

    def test_calculate_time_boundaries_no_timestamps(self):
        """Test time window calculation with no valid timestamps."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        # All metadata has None timestamp
        exact_metadata = [
            AssetMetadata("asset1", None, 40.7, -74.0),
            AssetMetadata("asset2", None, 40.8, -74.1),
        ]

        with pytest.raises(ValueError, match="No valid timestamps"):
            fuzzy_matcher._calculate_time_boundaries(exact_metadata, {})

    def test_calculate_time_boundaries_clamped_to_rule_boundary(self):
        """Test that expanded time window is clamped to rule's date boundaries."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client, time_window_minutes=240)  # 4 hours

        # Photo taken at 11 PM on Dec 14
        exact_metadata = [
            AssetMetadata("asset1", datetime(2025, 12, 14, 23, 0), None, None),
        ]

        # Rule covers Dec 14 (midnight to midnight)
        rule_date_filters = {
            "taken_after": "2025-12-14T05:00:00.000Z",  # Dec 14 midnight EST
            "taken_before": "2025-12-15T05:00:00.000Z"  # Dec 15 midnight EST
        }

        start, end = fuzzy_matcher._calculate_time_boundaries(exact_metadata, rule_date_filters)

        # Without clamping: 11 PM - 4 hours = 7 PM Dec 14, 11 PM + 4 hours = 3 AM Dec 15
        # With clamping: Should not extend before rule start or after rule end
        rule_start = datetime(2025, 12, 14, 5, 0, 0)
        rule_end = datetime(2025, 12, 15, 5, 0, 0)

        # Start should be clamped to rule start if it would go earlier
        assert start >= rule_start
        # End should be clamped to rule end if it would go later
        assert end <= rule_end

    @patch('fuzzy_matcher.ThreadPoolExecutor')
    def test_fetch_asset_metadata_success(self, mock_executor_class):
        """Test successful metadata fetching."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        # Mock asset data
        mock_client.get_asset_metadata.return_value = {
            'id': 'asset1',
            'exifInfo': {
                'dateTimeOriginal': '2025-06-15T14:30:00.000Z',
                'latitude': 40.7128,
                'longitude': -74.0060
            }
        }

        # Mock ThreadPoolExecutor
        mock_executor = MagicMock()
        mock_executor_class.return_value.__enter__.return_value = mock_executor

        mock_future = Mock()
        mock_future.result.return_value = AssetMetadata(
            'asset1',
            datetime(2025, 6, 15, 14, 30),
            40.7128,
            -74.0060
        )
        mock_executor.submit.return_value = mock_future

        result = fuzzy_matcher._fetch_asset_metadata({'asset1'})

        assert len(result) == 1
        assert result[0].asset_id == 'asset1'
        assert result[0].latitude == 40.7128

    def test_extract_metadata_with_exif(self):
        """Test metadata extraction from asset with EXIF data."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        asset = {
            'id': 'asset1',
            'exifInfo': {
                'dateTimeOriginal': '2025-06-15T14:30:00.000Z',
                'latitude': 40.7128,
                'longitude': -74.0060
            },
            'fileCreatedAt': '2025-06-15T14:35:00.000Z'
        }

        metadata = fuzzy_matcher._extract_metadata(asset)

        assert metadata is not None
        assert metadata.asset_id == 'asset1'
        assert metadata.timestamp.year == 2025
        assert metadata.timestamp.month == 6
        assert metadata.latitude == 40.7128
        assert metadata.longitude == -74.0060

    def test_extract_metadata_fallback_to_file_created(self):
        """Test metadata extraction falls back to fileCreatedAt when no EXIF."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        asset = {
            'id': 'asset2',
            'exifInfo': {},  # No EXIF data
            'fileCreatedAt': '2025-06-15T14:35:00.000Z'
        }

        metadata = fuzzy_matcher._extract_metadata(asset)

        assert metadata is not None
        assert metadata.asset_id == 'asset2'
        assert metadata.timestamp.year == 2025
        # Should use fileCreatedAt
        assert metadata.timestamp.minute == 35

    def test_extract_metadata_no_gps(self):
        """Test metadata extraction with no GPS coordinates."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        asset = {
            'id': 'asset3',
            'exifInfo': {
                'dateTimeOriginal': '2025-06-15T14:30:00.000Z'
                # No latitude/longitude
            }
        }

        metadata = fuzzy_matcher._extract_metadata(asset)

        assert metadata is not None
        assert metadata.asset_id == 'asset3'
        assert metadata.latitude is None
        assert metadata.longitude is None

    def test_find_related_assets_empty_exact_matches(self):
        """Test fuzzy matching with no exact matches."""
        mock_client = Mock()
        fuzzy_matcher = FuzzyMatcher(mock_client)

        result = fuzzy_matcher.find_related_assets(set(), {})

        assert result == set()


class TestDatabaseMigration:
    """Tests for database migration v2."""

    def test_migration_v2_adds_match_type_column(self, tmp_path):
        """Test that migration v2 adds match_type column."""
        # Create a temporary database
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Check that match_type column exists
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(album_memberships)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert 'match_type' in columns
        assert columns['match_type'] == 'TEXT'

        db.close()

    def test_migration_v2_default_value(self, tmp_path):
        """Test that existing records get default match_type='exact'."""
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Insert a record with old schema (no match_type specified)
        cursor = db.conn.cursor()
        cursor.execute("""
            INSERT INTO album_memberships
            (rule_id, album_id, album_name, asset_id, added_at)
            VALUES ('test_rule', 'test_album', 'Test Album', 'asset1', '2025-01-01T00:00:00')
        """)
        db.conn.commit()

        # Query the record
        cursor.execute("""
            SELECT match_type FROM album_memberships
            WHERE asset_id = 'asset1'
        """)
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == 'exact'  # Default value

        db.close()

    def test_record_album_membership_with_match_type(self, tmp_path):
        """Test recording album membership with match_type parameter."""
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Record exact matches
        db.record_album_membership('rule1', 'album1', 'Album 1', {'asset1', 'asset2'}, match_type='exact')

        # Record fuzzy matches
        db.record_album_membership('rule1', 'album1', 'Album 1', {'asset3', 'asset4'}, match_type='fuzzy')

        # Query the records
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT asset_id, match_type FROM album_memberships
            WHERE rule_id = 'rule1' AND album_id = 'album1'
            ORDER BY asset_id
        """)
        rows = cursor.fetchall()

        assert len(rows) == 4
        assert rows[0][1] == 'exact'  # asset1
        assert rows[1][1] == 'exact'  # asset2
        assert rows[2][1] == 'fuzzy'  # asset3
        assert rows[3][1] == 'fuzzy'  # asset4

        db.close()

    def test_get_album_assets_for_rule_returns_dict(self, tmp_path):
        """Test that get_album_assets_for_rule returns Dict[str, str]."""
        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Record some assets
        db.record_album_membership('rule1', 'album1', 'Album 1', {'asset1'}, match_type='exact')
        db.record_album_membership('rule1', 'album1', 'Album 1', {'asset2'}, match_type='fuzzy')

        # Get assets
        assets = db.get_album_assets_for_rule('rule1', 'album1')

        assert isinstance(assets, dict)
        assert assets['asset1'] == 'exact'
        assert assets['asset2'] == 'fuzzy'

        db.close()


class TestValidation:
    """Tests for fuzzy_match validation."""

    def test_fuzzy_match_validation_valid_true(self):
        """Test validation accepts fuzzy_match: true."""
        from validation import ConfigValidator

        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test",
                    "album_name": "Test Album",
                    "fuzzy_match": True,
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.000Z"
                    }
                }
            ]
        }

        validator = ConfigValidator(config)
        is_valid = validator.validate()

        assert is_valid is True
        assert len(validator.errors) == 0

    def test_fuzzy_match_validation_valid_false(self):
        """Test validation accepts fuzzy_match: false."""
        from validation import ConfigValidator

        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test",
                    "album_name": "Test Album",
                    "fuzzy_match": False,
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.000Z"
                    }
                }
            ]
        }

        validator = ConfigValidator(config)
        is_valid = validator.validate()

        assert is_valid is True
        assert len(validator.errors) == 0

    def test_fuzzy_match_validation_invalid_string(self):
        """Test validation rejects fuzzy_match as string."""
        from validation import ConfigValidator

        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test",
                    "album_name": "Test Album",
                    "fuzzy_match": "yes",  # Invalid: string instead of boolean
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.000Z"
                    }
                }
            ]
        }

        validator = ConfigValidator(config)
        is_valid = validator.validate()

        assert is_valid is False
        assert len(validator.errors) > 0
        assert any("fuzzy_match" in error and "boolean" in error for error in validator.errors)
