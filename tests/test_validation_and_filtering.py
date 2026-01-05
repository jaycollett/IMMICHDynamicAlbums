"""
Basic tests demonstrating validation and filtering functionality.

These tests show how the validation system works and how to use the new
filter features. To run these tests:

    pytest tests/test_validation_and_filtering.py

or:

    python -m pytest tests/test_validation_and_filtering.py -v
"""
import sys
from pathlib import Path

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from validation import (
    ConfigValidator,
    ConfigValidationError,
    DateFormatError,
    DuplicateRuleError,
    validate_config,
)
from rules import RuleFilters


class TestConfigValidation:
    """Test configuration validation."""

    def test_valid_basic_config(self):
        """Test that a basic valid config passes validation."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-rule",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                }
            ],
        }

        # Should not raise an exception
        result = validate_config(config)
        assert result is True

    def test_valid_config_with_filters(self):
        """Test that a config with new filters passes validation."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "favorites",
                    "album_name": "My Favorites",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "is_favorite": True,
                        "asset_types": ["IMAGE", "VIDEO"],
                        "camera": {"make": "Apple", "model": "iPhone 15 Pro"},
                        "tags": {"include": ["family"], "exclude": ["screenshot"]},
                    },
                }
            ],
        }

        # Should not raise an exception
        result = validate_config(config)
        assert result is True

    def test_invalid_mode(self):
        """Test that an invalid mode is caught."""
        config = {
            "mode": "invalid_mode",
            "rules": [
                {
                    "id": "test-rule",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "Invalid mode" in str(e)
            assert "add_only" in str(e)
            assert "sync" in str(e)

    def test_missing_required_fields(self):
        """Test that missing required fields are caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    # Missing 'id' and 'album_name'
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "Missing required field" in str(e)

    def test_duplicate_rule_ids(self):
        """Test that duplicate rule IDs are caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "duplicate-id",
                    "album_name": "First Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                },
                {
                    "id": "duplicate-id",  # Same ID!
                    "album_name": "Second Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                },
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "Duplicate rule ID" in str(e)
            assert "duplicate-id" in str(e)

    def test_invalid_date_format(self):
        """Test that invalid date formats are caught."""
        invalid_dates = [
            "2025-01-01",  # Missing time
            "2025-01-01 00:00:00",  # Space instead of T
            "2025-01-01T00:00:00",  # Missing timezone
            "01/01/2025",  # Wrong format
            "2025-13-01T00:00:00.000Z",  # Invalid month
            "2025-02-31T00:00:00.000Z",  # Invalid day
        ]

        for invalid_date in invalid_dates:
            config = {
                "mode": "add_only",
                "rules": [
                    {
                        "id": "test-rule",
                        "album_name": "Test Album",
                        "taken_range_utc": {
                            "start": invalid_date,
                            "end": "2025-12-31T23:59:59.999Z",
                        },
                    }
                ],
            }

            try:
                validate_config(config)
                assert False, f"Should have caught invalid date: {invalid_date}"
            except ConfigValidationError as e:
                assert "ISO 8601" in str(e) or "Invalid date" in str(e)

    def test_valid_date_formats(self):
        """Test that various valid date formats are accepted."""
        valid_dates = [
            "2025-01-01T00:00:00.000Z",  # UTC with milliseconds
            "2025-01-01T00:00:00Z",  # UTC without milliseconds
            "2025-01-01T12:00:00+05:30",  # With timezone offset
            "2025-01-01T12:00:00-08:00",  # Negative offset
        ]

        for valid_date in valid_dates:
            config = {
                "mode": "add_only",
                "rules": [
                    {
                        "id": f"test-rule-{valid_date[:10]}",
                        "album_name": "Test Album",
                        "taken_range_utc": {
                            "start": valid_date,
                            "end": "2025-12-31T23:59:59.999Z",
                        },
                    }
                ],
            }

            # Should not raise an exception
            result = validate_config(config)
            assert result is True

    def test_start_after_end_date(self):
        """Test that start date after end date is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-rule",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-12-31T23:59:59.999Z",
                        "end": "2025-01-01T00:00:00.000Z",  # End before start!
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "start date must be before end date" in str(e)

    def test_invalid_asset_types(self):
        """Test that invalid asset types are caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-rule",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "asset_types": ["INVALID_TYPE"],
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "Invalid asset_type" in str(e)
            assert "INVALID_TYPE" in str(e)


class TestRuleFilters:
    """Test RuleFilters class."""

    def test_default_filters(self):
        """Test that default filters only include IMAGE assets."""
        filters = RuleFilters.from_config(None)

        assert filters.is_favorite is None
        assert filters.asset_types == ["IMAGE"]
        assert filters.camera_make is None
        assert filters.camera_model is None
        assert filters.include_people == []

    def test_parse_filters_is_favorite(self):
        """Test parsing is_favorite filter."""
        filters_config = {"is_favorite": True}
        filters = RuleFilters.from_config(filters_config)

        assert filters.is_favorite is True

    def test_parse_filters_asset_types(self):
        """Test parsing asset_types filter."""
        filters_config = {"asset_types": ["IMAGE", "VIDEO"]}
        filters = RuleFilters.from_config(filters_config)

        assert "IMAGE" in filters.asset_types
        assert "VIDEO" in filters.asset_types

    def test_parse_filters_camera(self):
        """Test parsing camera filters."""
        filters_config = {"camera": {"make": "Apple", "model": "iPhone 15 Pro"}}
        filters = RuleFilters.from_config(filters_config)

        assert filters.camera_make == "Apple"
        assert filters.camera_model == "iPhone 15 Pro"

    def test_parse_filters_people(self):
        """Test parsing people filters."""
        filters_config = {
            "people": {"include": ["Jay", "Alice", "Bob"]}
        }
        filters = RuleFilters.from_config(filters_config)

        assert "Jay" in filters.include_people
        assert "Alice" in filters.include_people
        assert "Bob" in filters.include_people

    def test_parse_complex_filters(self):
        """Test parsing all filters together."""
        filters_config = {
            "is_favorite": True,
            "asset_types": ["IMAGE"],
            "camera": {"make": "Canon"},
            "people": {"include": ["Charlie", "Dana"]},
        }
        filters = RuleFilters.from_config(filters_config)

        assert filters.is_favorite is True
        assert filters.asset_types == ["IMAGE"]
        assert filters.camera_make == "Canon"
        assert "Charlie" in filters.include_people
        assert "Dana" in filters.include_people

    def test_asset_types_normalized_to_uppercase(self):
        """Test that asset types are normalized to uppercase."""
        filters_config = {"asset_types": ["image", "video"]}
        filters = RuleFilters.from_config(filters_config)

        assert "IMAGE" in filters.asset_types
        assert "VIDEO" in filters.asset_types


class TestBackwardCompatibility:
    """Test backward compatibility with old config format."""

    def test_old_format_without_filters(self):
        """Test that old format without filters section still works."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "old-format-rule",
                    "album_name": "Old Format Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                }
            ],
        }

        # Should pass validation
        result = validate_config(config)
        assert result is True

        # Should default to IMAGE only
        filters = RuleFilters.from_config(None)
        assert filters.asset_types == ["IMAGE"]


def test_comprehensive_example():
    """
    Comprehensive example showing a complete valid configuration
    with both old and new formats.
    """
    config = {
        "mode": "add_only",
        "rules": [
            # Old format - still works
            {
                "id": "christmas-2025",
                "album_name": "Christmas 2025",
                "description": "Christmas photos",
                "taken_range_utc": {
                    "start": "2025-12-25T00:00:00.000Z",
                    "end": "2025-12-26T00:00:00.000Z",
                },
            },
            # New format with filters
            {
                "id": "favorites-2025",
                "album_name": "My Favorites 2025",
                "description": "Favorite images from 2025",
                "taken_range_utc": {
                    "start": "2025-01-01T00:00:00.000Z",
                    "end": "2025-12-31T23:59:59.999Z",
                },
                "filters": {
                    "is_favorite": True,
                    "asset_types": ["IMAGE"],
                },
            },
            # New format with complex filters
            {
                "id": "iphone-family",
                "album_name": "iPhone Family Photos",
                "description": "Family photos taken with iPhone",
                "taken_range_utc": {
                    "start": "2025-01-01T00:00:00.000Z",
                    "end": "2025-12-31T23:59:59.999Z",
                },
                "filters": {
                    "camera": {"make": "Apple"},
                    "tags": {"include": ["family"], "exclude": ["screenshot"]},
                    "asset_types": ["IMAGE"],
                },
            },
        ],
    }

    # Should pass validation
    result = validate_config(config)
    assert result is True


if __name__ == "__main__":
    # Run tests manually
    print("Running validation and filtering tests...\n")

    test_validator = TestConfigValidation()
    test_filters = TestRuleFilters()
    test_compat = TestBackwardCompatibility()

    tests = [
        ("Valid basic config", test_validator.test_valid_basic_config),
        ("Valid config with filters", test_validator.test_valid_config_with_filters),
        ("Invalid mode", test_validator.test_invalid_mode),
        ("Missing required fields", test_validator.test_missing_required_fields),
        ("Duplicate rule IDs", test_validator.test_duplicate_rule_ids),
        ("Invalid date format", test_validator.test_invalid_date_format),
        ("Valid date formats", test_validator.test_valid_date_formats),
        ("Start after end date", test_validator.test_start_after_end_date),
        ("Invalid asset types", test_validator.test_invalid_asset_types),
        ("Default filters", test_filters.test_default_filters),
        ("Parse is_favorite", test_filters.test_parse_filters_is_favorite),
        ("Parse asset_types", test_filters.test_parse_filters_asset_types),
        ("Parse camera", test_filters.test_parse_filters_camera),
        ("Parse tags", test_filters.test_parse_filters_tags),
        ("Parse complex filters", test_filters.test_parse_complex_filters),
        (
            "Asset types normalized",
            test_filters.test_asset_types_normalized_to_uppercase,
        ),
        ("Old format compatibility", test_compat.test_old_format_without_filters),
        ("Comprehensive example", test_comprehensive_example),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ {name}: {str(e)}")
            failed += 1
        except Exception as e:
            print(f"✗ {name}: Unexpected error - {str(e)}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")

    if failed == 0:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print(f"\n✗ {failed} test(s) failed")
        sys.exit(1)
