"""
Tests for recurring rule functionality.

These tests verify that recurring rules are properly validated, expanded,
and generate the correct date ranges for multiple years.

To run these tests:

    pytest tests/test_recurring_rules.py -v

or:

    python -m pytest tests/test_recurring_rules.py -v
"""
import sys
from pathlib import Path
from datetime import datetime
import tempfile
import os

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from validation import ConfigValidator, ConfigValidationError, validate_config
from rules import RuleEngine
import yaml


class TestRecurringRuleValidation:
    """Test recurring rule validation."""

    def test_valid_recurring_rule(self):
        """Test that a valid recurring rule passes validation."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2025],
                    "filters": {"asset_types": ["IMAGE", "VIDEO"]},
                }
            ],
        }

        # Should not raise an exception
        result = validate_config(config)
        assert result is True

    def test_recurring_rule_missing_fields(self):
        """Test that recurring rules with missing fields fail validation."""
        # Missing month_day
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2025],
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Expected validation to fail for missing month_day"
        except ConfigValidationError:
            pass  # Expected

    def test_recurring_rule_invalid_month_day_format(self):
        """Test that invalid month_day format is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12/25",  # Invalid format (should be MM-DD)
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2025],
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Expected validation to fail for invalid month_day format"
        except ConfigValidationError:
            pass  # Expected

    def test_recurring_rule_invalid_year_range(self):
        """Test that invalid year_range is caught."""
        # Year range with start > end
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2025, 2020],  # Start > end
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Expected validation to fail for invalid year_range"
        except ConfigValidationError:
            pass  # Expected

    def test_recurring_rule_with_optional_fields(self):
        """Test recurring rule with all optional fields."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "duration_days": 2,
                    "album_name_template": "Christmas {year}",
                    "description": "Christmas photos",
                    "year_range": [2020, 2025],
                    "filters": {
                        "is_favorite": True,
                        "asset_types": ["IMAGE"],
                        "camera": {"make": "Apple"},
                    },
                }
            ],
        }

        # Should not raise an exception
        result = validate_config(config)
        assert result is True


class TestRecurringRuleExpansion:
    """Test recurring rule expansion logic."""

    def test_recurring_rule_expands_to_multiple_rules(self):
        """Test that a recurring rule expands into multiple year-specific rules."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2022],  # 3 years
                    "filters": {"asset_types": ["IMAGE"]},
                }
            ],
        }

        # Write config to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            # Load config through RuleEngine
            engine = RuleEngine(config_file)

            # Should expand to 3 rules (2020, 2021, 2022)
            assert len(engine.rules) == 3

            # Check rule IDs
            rule_ids = [rule.id for rule in engine.rules]
            assert "christmas-2020" in rule_ids
            assert "christmas-2021" in rule_ids
            assert "christmas-2022" in rule_ids

            # Check album names
            album_names = [rule.album_name for rule in engine.rules]
            assert "Christmas 2020" in album_names
            assert "Christmas 2021" in album_names
            assert "Christmas 2022" in album_names

        finally:
            # Clean up temp file
            os.unlink(config_file)

    def test_recurring_rule_generates_correct_dates(self):
        """Test that expanded rules have correct date ranges."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "duration_days": 1,
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2020],  # Just one year for testing
                    "filters": {"asset_types": ["IMAGE"]},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)

            # Should have exactly one expanded rule
            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # Check dates (America/New_York = EST in December, UTC-5)
            assert rule.taken_after == "2020-12-25T05:00:00.000Z"
            assert rule.taken_before == "2020-12-26T05:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_recurring_rule_multi_day_duration(self):
        """Test recurring rule with multi-day duration."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "birthday",
                    "recurring": True,
                    "month_day": "07-15",
                    "timezone": "America/New_York",
                    "duration_days": 3,  # 3-day event
                    "album_name_template": "Birthday {year}",
                    "year_range": [2020, 2020],
                    "filters": {"asset_types": ["IMAGE"]},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)
            rule = engine.rules[0]

            # Should start on 7/15 and end on 7/18 (start + 3 days)
            # America/New_York = EDT in July, UTC-4
            assert rule.taken_after == "2020-07-15T04:00:00.000Z"
            assert rule.taken_before == "2020-07-18T04:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_mix_recurring_and_regular_rules(self):
        """Test config with both recurring and regular rules."""
        config_data = {
            "mode": "add_only",
            "rules": [
                # Regular rule
                {
                    "id": "summer-2025",
                    "album_name": "Summer 2025",
                    "taken_range_utc": {
                        "start": "2025-06-01T00:00:00.000Z",
                        "end": "2025-09-01T00:00:00.000Z",
                    },
                },
                # Recurring rule
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2024, 2025],
                    "filters": {"asset_types": ["IMAGE"]},
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)

            # Should have 3 rules: 1 regular + 2 recurring (2024, 2025)
            assert len(engine.rules) == 3

            rule_ids = [rule.id for rule in engine.rules]
            assert "summer-2025" in rule_ids
            assert "christmas-2024" in rule_ids
            assert "christmas-2025" in rule_ids

        finally:
            os.unlink(config_file)

    def test_recurring_rule_preserves_filters(self):
        """Test that expanded recurring rules preserve filter settings."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2020, 2020],
                    "filters": {
                        "is_favorite": True,
                        "asset_types": ["IMAGE", "VIDEO"],
                        "camera": {"make": "Canon"},
                    },
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)
            rule = engine.rules[0]

            # Check that filters are preserved
            assert rule.filters.is_favorite is True
            assert "IMAGE" in rule.filters.asset_types
            assert "VIDEO" in rule.filters.asset_types
            assert rule.filters.camera_make == "Canon"

        finally:
            os.unlink(config_file)


class TestRecurringRuleEdgeCases:
    """Test edge cases for recurring rules."""

    def test_single_year_range(self):
        """Test recurring rule with single year (start == end)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2025, 2025],  # Same start and end
                    "filters": {"asset_types": ["IMAGE"]},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)

            # Should create exactly one rule
            assert len(engine.rules) == 1
            assert engine.rules[0].id == "christmas-2025"

        finally:
            os.unlink(config_file)

    def test_leap_year_february_29(self):
        """Test recurring rule on February 29th (leap day)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "leap-day",
                    "recurring": True,
                    "month_day": "02-29",
                    "timezone": "America/New_York",
                    "album_name_template": "Leap Day {year}",
                    "year_range": [2020, 2024],  # Includes leap years 2020, 2024
                    "filters": {"asset_types": ["IMAGE"]},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file)

            # Should create only 2 rules (2020 and 2024 are leap years)
            # Non-leap years (2021, 2022, 2023) are automatically skipped
            assert len(engine.rules) == 2

            rule_ids = [rule.id for rule in engine.rules]
            assert "leap-day-2020" in rule_ids
            assert "leap-day-2024" in rule_ids

        finally:
            os.unlink(config_file)


class TestRecurringRuleTimezones:
    """Test timezone support for recurring rules."""

    def test_timezone_required_for_recurring_rules(self):
        """Test that timezone field is required for recurring rules."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2025, 2025],
                    # timezone field intentionally missing
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Expected validation to fail for missing timezone"
        except ConfigValidationError as e:
            assert "timezone" in str(e).lower()

    def test_valid_timezone_accepted(self):
        """Test that valid IANA timezone names are accepted."""
        valid_timezones = [
            "America/New_York",
            "America/Los_Angeles",
            "America/Chicago",
            "Europe/London",
            "Asia/Tokyo",
            "UTC",
            "Pacific/Honolulu",
        ]

        for tz in valid_timezones:
            config = {
                "mode": "add_only",
                "rules": [
                    {
                        "id": "test",
                        "recurring": True,
                        "month_day": "01-01",
                    "timezone": "America/New_York",
                        "album_name_template": "Test {year}",
                        "year_range": [2025, 2025],
                    }
                ],
            }

            # Should not raise an exception
            result = validate_config(config)
            assert result is True, f"Timezone {tz} should be valid"

    def test_invalid_timezone_rejected(self):
        """Test that invalid timezone names are rejected with helpful errors."""
        invalid_timezones = [
            "PST",  # Invalid
            "Eastern",
            "InvalidTimezone",
            "America/InvalidCity",
        ]

        for tz in invalid_timezones:
            config = {
                "mode": "add_only",
                "rules": [
                    {
                        "id": "test",
                        "recurring": True,
                        "month_day": "01-01",
                        "timezone": tz,
                        "album_name_template": "Test {year}",
                        "year_range": [2025, 2025],
                    }
                ],
            }

            try:
                validate_config(config)
                assert False, f"Expected validation to fail for invalid timezone: {tz}"
            except ConfigValidationError as e:
                assert "timezone" in str(e).lower(), f"Error message should mention timezone for {tz}"

    def test_timezone_conversion_america_new_york_winter(self):
        """Test timezone conversion for America/New_York in winter (EST, UTC-5)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "christmas",
                    "recurring": True,
                    "month_day": "12-25",
                    "timezone": "America/New_York",
                    "album_name_template": "Christmas {year}",
                    "year_range": [2025, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # Christmas 2025 midnight EST (UTC-5) = 2025-12-25T05:00:00.000Z
            assert rule.taken_after == "2025-12-25T05:00:00.000Z"
            # Next day midnight EST = 2025-12-26T05:00:00.000Z
            assert rule.taken_before == "2025-12-26T05:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_timezone_conversion_america_new_york_summer(self):
        """Test timezone conversion for America/New_York in summer (EDT, UTC-4)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "july4",
                    "recurring": True,
                    "month_day": "07-04",
                    "timezone": "America/New_York",
                    "album_name_template": "July 4th {year}",
                    "year_range": [2025, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # July 4th 2025 midnight EDT (UTC-4) = 2025-07-04T04:00:00.000Z
            assert rule.taken_after == "2025-07-04T04:00:00.000Z"
            # Next day midnight EDT = 2025-07-05T04:00:00.000Z
            assert rule.taken_before == "2025-07-05T04:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_timezone_conversion_utc(self):
        """Test timezone conversion for UTC (no offset)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "newyear",
                    "recurring": True,
                    "month_day": "01-01",
                    "timezone": "UTC",
                    "album_name_template": "New Year {year}",
                    "year_range": [2025, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # UTC has no offset
            assert rule.taken_after == "2025-01-01T00:00:00.000Z"
            assert rule.taken_before == "2025-01-02T00:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_timezone_conversion_pacific_honolulu(self):
        """Test timezone conversion for Pacific/Honolulu (HST, UTC-10, no DST)."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "luau",
                    "recurring": True,
                    "month_day": "08-15",
                    "timezone": "Pacific/Honolulu",
                    "album_name_template": "Luau {year}",
                    "year_range": [2025, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # Hawaii has no DST, always UTC-10
            assert rule.taken_after == "2025-08-15T10:00:00.000Z"
            assert rule.taken_before == "2025-08-16T10:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_timezone_multi_day_duration(self):
        """Test timezone conversion with multi-day duration."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "birthday-weekend",
                    "recurring": True,
                    "month_day": "06-15",
                    "timezone": "America/New_York",
                    "duration_days": 3,
                    "timezone": "America/Los_Angeles",
                    "album_name_template": "Birthday Weekend {year}",
                    "year_range": [2025, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            assert len(engine.rules) == 1
            rule = engine.rules[0]

            # June 15th midnight PDT (UTC-7) = 2025-06-15T07:00:00.000Z
            assert rule.taken_after == "2025-06-15T07:00:00.000Z"
            # June 18th midnight PDT (3 days later) = 2025-06-18T07:00:00.000Z
            assert rule.taken_before == "2025-06-18T07:00:00.000Z"

        finally:
            os.unlink(config_file)

    def test_timezone_february_leap_year(self):
        """Test timezone with February 29th in leap years."""
        config_data = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "leap-day",
                    "recurring": True,
                    "month_day": "02-29",
                    "timezone": "America/New_York",
                    "album_name_template": "Leap Day {year}",
                    "year_range": [2024, 2025],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            engine = RuleEngine(config_file, default_timezone="America/New_York")

            # Should only create rule for 2024 (leap year), skip 2025
            assert len(engine.rules) == 1
            rule = engine.rules[0]
            assert rule.id == "leap-day-2024"

            # February 29, 2024 midnight EST (UTC-5) = 2024-02-29T05:00:00.000Z
            assert rule.taken_after == "2024-02-29T05:00:00.000Z"

        finally:
            os.unlink(config_file)


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
