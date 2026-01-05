"""
Tests for resolution filtering functionality.

These tests verify that the resolution filtering feature works correctly
with both filters and conditions formats, including validation and
client-side filtering with parallel metadata fetching.

To run these tests:

    pytest tests/test_resolution_filter.py -v

or:

    python -m pytest tests/test_resolution_filter.py -v
"""
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conditions import FilterCondition, ConditionNode, ConditionType, ResolutionFilter
from rules import RuleFilters
from validation import validate_config, ConfigValidationError


class TestResolutionFilterDataStructures:
    """Test that resolution field is properly added to data structures."""

    def test_filter_condition_has_resolution_field(self):
        """Test that FilterCondition has resolution field."""
        condition = FilterCondition()
        assert hasattr(condition, 'resolution')
        assert condition.resolution is None

        # Test with resolution data
        condition = FilterCondition(resolution=[[1920, 1080], [3840, 2160]])
        assert condition.resolution == [[1920, 1080], [3840, 2160]]

    def test_filter_condition_has_filters_includes_resolution(self):
        """Test that has_filters() returns True when resolution is set."""
        condition = FilterCondition()
        assert condition.has_filters() is False

        condition = FilterCondition(resolution=[[1920, 1080]])
        assert condition.has_filters() is True

    def test_filter_condition_repr_includes_resolution(self):
        """Test that __repr__ includes resolution info."""
        condition = FilterCondition(resolution=[[1920, 1080], [3840, 2160]])
        repr_str = repr(condition)
        assert "resolution=2 sizes" in repr_str

    def test_rule_filters_has_resolution_field(self):
        """Test that RuleFilters has resolution field."""
        filters = RuleFilters()
        assert hasattr(filters, 'resolution')
        assert filters.resolution is None

        # Test with resolution data
        filters = RuleFilters(resolution=[[1920, 1080]])
        assert filters.resolution == [[1920, 1080]]


class TestResolutionFilterParsing:
    """Test parsing of resolution filters from config."""

    def test_parse_resolution_from_filters(self):
        """Test parsing resolution from filters config."""
        filters_config = {
            "resolution": {
                "include": [
                    [1920, 1080],
                    [3840, 2160]
                ]
            }
        }

        filters = RuleFilters.from_config(filters_config)
        assert filters.resolution == [[1920, 1080], [3840, 2160]]

    def test_parse_resolution_from_conditions(self):
        """Test parsing resolution from conditions config."""
        conditions_config = {
            "resolution": {
                "include": [
                    [1320, 2868],
                    [1080, 2400]
                ]
            }
        }

        node = ConditionNode.from_config(conditions_config)
        assert node.node_type == ConditionType.LEAF
        assert node.condition.resolution == [[1320, 2868], [1080, 2400]]

    def test_parse_empty_resolution_config(self):
        """Test that empty resolution config doesn't set field."""
        filters_config = {
            "resolution": {
                "include": []
            }
        }

        filters = RuleFilters.from_config(filters_config)
        assert filters.resolution is None

    def test_parse_missing_resolution_config(self):
        """Test that missing resolution config leaves field as None."""
        filters_config = {
            "is_favorite": True
        }

        filters = RuleFilters.from_config(filters_config)
        assert filters.resolution is None


class TestResolutionFilterValidation:
    """Test validation of resolution filter configuration."""

    def test_valid_resolution_filter(self):
        """Test that valid resolution filter passes validation."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": {
                            "include": [
                                [1920, 1080],
                                [3840, 2160]
                            ]
                        }
                    }
                }
            ]
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True

    def test_invalid_resolution_not_dict(self):
        """Test that resolution not being a dict is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": "invalid"
                    }
                }
            ]
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "filters.resolution must be a dictionary" in str(e)

    def test_invalid_resolution_include_not_list(self):
        """Test that resolution.include not being a list is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": {
                            "include": "invalid"
                        }
                    }
                }
            ]
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "must be a list of [width, height] pairs" in str(e)

    def test_invalid_resolution_pair_not_list(self):
        """Test that resolution pair not being a list is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": {
                            "include": [
                                "1920x1080"  # String instead of list
                            ]
                        }
                    }
                }
            ]
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "must be a list [width, height]" in str(e)

    def test_invalid_resolution_pair_wrong_length(self):
        """Test that resolution pair with wrong length is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": {
                            "include": [
                                [1920, 1080, 24]  # 3 elements instead of 2
                            ]
                        }
                    }
                }
            ]
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "must have exactly 2 elements" in str(e)

    def test_invalid_resolution_pair_not_positive_integers(self):
        """Test that resolution pair with non-positive or non-integer values is caught."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "resolution": {
                            "include": [
                                [1920, -1080]  # Negative height
                            ]
                        }
                    }
                }
            ]
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "must contain positive integers" in str(e)

    def test_valid_resolution_in_conditions(self):
        """Test that valid resolution in conditions format passes validation."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "and": [
                            {"is_favorite": True},
                            {
                                "resolution": {
                                    "include": [[1920, 1080]]
                                }
                            }
                        ]
                    }
                }
            ]
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True


class TestResolutionFilterClass:
    """Test the ResolutionFilter helper class."""

    def test_resolution_filter_initialization(self):
        """Test ResolutionFilter initialization."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        assert filter_obj.client == mock_client
        assert filter_obj.max_workers == 10

        # Test custom max_workers
        filter_obj = ResolutionFilter(mock_client, max_workers=5)
        assert filter_obj.max_workers == 5

    def test_extract_resolution_from_exif(self):
        """Test resolution extraction from EXIF data."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        asset = {
            'id': 'asset1',
            'exifInfo': {
                'exifImageWidth': 1920,
                'exifImageHeight': 1080
            }
        }

        resolution = filter_obj._extract_resolution(asset)
        assert resolution == (1920, 1080)

    def test_extract_resolution_from_original(self):
        """Test resolution extraction from original dimensions (fallback)."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        asset = {
            'id': 'asset1',
            'exifInfo': {},  # No EXIF data
            'originalWidth': 3840,
            'originalHeight': 2160
        }

        resolution = filter_obj._extract_resolution(asset)
        assert resolution == (3840, 2160)

    def test_extract_resolution_prioritizes_exif(self):
        """Test that EXIF data is prioritized over original dimensions."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        asset = {
            'id': 'asset1',
            'exifInfo': {
                'exifImageWidth': 1920,
                'exifImageHeight': 1080
            },
            'originalWidth': 3840,
            'originalHeight': 2160
        }

        resolution = filter_obj._extract_resolution(asset)
        assert resolution == (1920, 1080)  # EXIF takes priority

    def test_extract_resolution_returns_none_when_unavailable(self):
        """Test that None is returned when no resolution data is available."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        asset = {
            'id': 'asset1',
            'exifInfo': {}
        }

        resolution = filter_obj._extract_resolution(asset)
        assert resolution is None

    def test_filter_by_resolution_empty_inputs(self):
        """Test that empty inputs return empty set."""
        mock_client = Mock()
        filter_obj = ResolutionFilter(mock_client)

        # Empty asset IDs
        result = filter_obj.filter_by_resolution(set(), [[1920, 1080]])
        assert result == set()

        # Empty target resolutions
        result = filter_obj.filter_by_resolution({'asset1'}, [])
        assert result == set()

    def test_filter_by_resolution_matching(self):
        """Test filtering assets by resolution."""
        mock_client = Mock()

        # Mock metadata responses
        def mock_get_metadata(asset_id):
            metadata = {
                'asset1': {
                    'id': 'asset1',
                    'exifInfo': {'exifImageWidth': 1920, 'exifImageHeight': 1080}
                },
                'asset2': {
                    'id': 'asset2',
                    'exifInfo': {'exifImageWidth': 3840, 'exifImageHeight': 2160}
                },
                'asset3': {
                    'id': 'asset3',
                    'exifInfo': {'exifImageWidth': 1280, 'exifImageHeight': 720}
                }
            }
            return metadata.get(asset_id, {})

        mock_client.get_asset_metadata = mock_get_metadata

        filter_obj = ResolutionFilter(mock_client)

        # Filter for 1920x1080 and 3840x2160
        asset_ids = {'asset1', 'asset2', 'asset3'}
        target_resolutions = [[1920, 1080], [3840, 2160]]

        result = filter_obj.filter_by_resolution(asset_ids, target_resolutions)

        # Should match asset1 (1920x1080) and asset2 (3840x2160)
        # Should NOT match asset3 (1280x720)
        assert 'asset1' in result
        assert 'asset2' in result
        assert 'asset3' not in result

    def test_filter_by_resolution_handles_exceptions(self):
        """Test that exceptions during metadata fetch are handled gracefully."""
        mock_client = Mock()

        def mock_get_metadata(asset_id):
            if asset_id == 'asset_error':
                raise Exception("Network error")
            return {
                'id': asset_id,
                'exifInfo': {'exifImageWidth': 1920, 'exifImageHeight': 1080}
            }

        mock_client.get_asset_metadata = mock_get_metadata

        filter_obj = ResolutionFilter(mock_client)

        asset_ids = {'asset1', 'asset_error'}
        target_resolutions = [[1920, 1080]]

        # Should not raise exception, just skip the failed asset
        result = filter_obj.filter_by_resolution(asset_ids, target_resolutions)

        assert 'asset1' in result
        assert 'asset_error' not in result


class TestResolutionFilterIntegration:
    """Test integration of resolution filtering with condition evaluation."""

    def test_resolution_filter_in_leaf_evaluation(self):
        """Test that resolution filter is applied during leaf evaluation."""
        mock_client = Mock()

        # Mock search_assets to return some asset IDs
        mock_client.search_assets = Mock(return_value={'asset1', 'asset2', 'asset3'})

        # Mock metadata for resolution filtering
        def mock_get_metadata(asset_id):
            metadata = {
                'asset1': {
                    'id': 'asset1',
                    'exifInfo': {'exifImageWidth': 1920, 'exifImageHeight': 1080}
                },
                'asset2': {
                    'id': 'asset2',
                    'exifInfo': {'exifImageWidth': 3840, 'exifImageHeight': 2160}
                },
                'asset3': {
                    'id': 'asset3',
                    'exifInfo': {'exifImageWidth': 1280, 'exifImageHeight': 720}
                }
            }
            return metadata.get(asset_id, {})

        mock_client.get_asset_metadata = mock_get_metadata

        # Create condition with resolution filter
        condition = FilterCondition(
            is_favorite=True,
            resolution=[[1920, 1080]]
        )

        node = ConditionNode(ConditionType.LEAF, condition=condition)

        # Evaluate
        result = node.evaluate(mock_client)

        # Should only return asset1 (matches 1920x1080)
        assert 'asset1' in result
        assert 'asset2' not in result
        assert 'asset3' not in result

    def test_resolution_filter_combined_with_other_filters(self):
        """Test resolution filter works with other filters in AND logic."""
        config = {
            "and": [
                {"is_favorite": True},
                {
                    "resolution": {
                        "include": [[1920, 1080]]
                    }
                }
            ]
        }

        node = ConditionNode.from_config(config)

        # Should create AND node with two LEAF children
        assert node.node_type == ConditionType.AND
        assert len(node.children) == 2

        # First child should have is_favorite filter
        assert node.children[0].condition.is_favorite is True

        # Second child should have resolution filter
        assert node.children[1].condition.resolution == [[1920, 1080]]


class TestResolutionFilterBackwardCompatibility:
    """Test that resolution filter doesn't break existing functionality."""

    def test_filters_without_resolution_still_work(self):
        """Test that rules without resolution filter work as before."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-no-resolution",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {
                        "is_favorite": True,
                        "asset_types": ["IMAGE"]
                    }
                }
            ]
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True

    def test_empty_filters_still_work(self):
        """Test that rules with empty filters work as before."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "test-empty-filters",
                    "album_name": "Test Album",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    }
                }
            ]
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True
