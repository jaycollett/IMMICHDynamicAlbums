"""
Tests for AND/OR conditional logic in filters.

These tests validate the condition tree structure, evaluation logic,
optimization, backward compatibility, and error handling.

To run these tests:
    pytest tests/test_conditions.py -v

or:
    python -m pytest tests/test_conditions.py -v
"""
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conditions import (
    ConditionNode,
    ConditionType,
    FilterCondition,
)
from validation import validate_config, ConfigValidationError
from rules import Rule, RuleFilters, PeopleResolver


class TestConditionTreeConstruction:
    """Test condition tree construction from YAML."""

    def test_simple_leaf_condition(self):
        """Test parsing a simple leaf condition."""
        config = {"is_favorite": True}
        node = ConditionNode.from_config(config)

        assert node.node_type == ConditionType.LEAF
        assert node.condition.is_favorite is True
        assert node.children == []

    def test_and_operation(self):
        """Test parsing an AND operation."""
        config = {
            "and": [
                {"is_favorite": True},
                {"camera": {"make": "Apple"}},
            ]
        }
        node = ConditionNode.from_config(config)

        assert node.node_type == ConditionType.AND
        assert len(node.children) == 2
        assert node.children[0].node_type == ConditionType.LEAF
        assert node.children[1].node_type == ConditionType.LEAF

    def test_or_operation(self):
        """Test parsing an OR operation."""
        config = {
            "or": [
                {"is_favorite": True},
                {"camera": {"make": "Apple"}},
            ]
        }
        node = ConditionNode.from_config(config)

        assert node.node_type == ConditionType.OR
        assert len(node.children) == 2

    def test_nested_conditions(self):
        """Test parsing nested AND/OR conditions."""
        config = {
            "or": [
                {
                    "and": [
                        {"is_favorite": True},
                        {"camera": {"make": "Apple"}},
                    ]
                },
                {
                    "and": [
                        {"camera": {"make": "Canon"}},
                        {"asset_types": ["VIDEO"]},
                    ]
                },
            ]
        }
        node = ConditionNode.from_config(config)

        assert node.node_type == ConditionType.OR
        assert len(node.children) == 2
        assert node.children[0].node_type == ConditionType.AND
        assert node.children[1].node_type == ConditionType.AND

    def test_people_condition_with_resolver(self):
        """Test parsing people condition with resolver."""
        # Mock people resolver
        people_resolver = Mock(spec=PeopleResolver)
        people_resolver.resolve_people_names.return_value = ["person-id-1", "person-id-2"]

        config = {"people": {"include": ["Jay", "Alice"]}}
        node = ConditionNode.from_config(config, people_resolver)

        assert node.node_type == ConditionType.LEAF
        assert node.condition.person_ids == ["person-id-1", "person-id-2"]
        people_resolver.resolve_people_names.assert_called_once_with(["Jay", "Alice"])

    def test_multiple_filters_in_leaf(self):
        """Test leaf condition with multiple filters."""
        config = {
            "is_favorite": True,
            "camera": {"make": "Apple", "model": "iPhone 15 Pro"},
            "asset_types": ["IMAGE"],
        }
        node = ConditionNode.from_config(config)

        assert node.node_type == ConditionType.LEAF
        assert node.condition.is_favorite is True
        assert node.condition.camera_make == "Apple"
        assert node.condition.camera_model == "iPhone 15 Pro"
        assert node.condition.asset_types == ["IMAGE"]


class TestConditionTreeEvaluation:
    """Test condition tree evaluation logic."""

    def test_leaf_evaluation(self):
        """Test evaluating a simple leaf condition."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.return_value = {"asset1", "asset2", "asset3"}

        # Create leaf node
        condition = FilterCondition(is_favorite=True, asset_types=["IMAGE"])
        node = ConditionNode(ConditionType.LEAF, condition=condition)

        # Evaluate
        result = node.evaluate(mock_client)

        assert result == {"asset1", "asset2", "asset3"}
        mock_client.search_assets.assert_called_once()

    def test_and_evaluation(self):
        """Test AND operation (intersection)."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.side_effect = [
            {"asset1", "asset2", "asset3"},  # First child
            {"asset2", "asset3", "asset4"},  # Second child
        ]

        # Create AND node with two children
        child1 = ConditionNode(
            ConditionType.LEAF,
            condition=FilterCondition(is_favorite=True)
        )
        child2 = ConditionNode(
            ConditionType.LEAF,
            condition=FilterCondition(camera_make="Apple")
        )
        node = ConditionNode(ConditionType.AND, children=[child1, child2])

        # Evaluate
        result = node.evaluate(mock_client)

        # Should be intersection: {asset2, asset3}
        assert result == {"asset2", "asset3"}

    def test_or_evaluation(self):
        """Test OR operation (union)."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.side_effect = [
            {"asset1", "asset2"},  # First child
            {"asset3", "asset4"},  # Second child
        ]

        # Create OR node with two children
        child1 = ConditionNode(
            ConditionType.LEAF,
            condition=FilterCondition(is_favorite=True)
        )
        child2 = ConditionNode(
            ConditionType.LEAF,
            condition=FilterCondition(camera_make="Apple")
        )
        node = ConditionNode(ConditionType.OR, children=[child1, child2])

        # Evaluate
        result = node.evaluate(mock_client)

        # Should be union: {asset1, asset2, asset3, asset4}
        assert result == {"asset1", "asset2", "asset3", "asset4"}

    def test_nested_evaluation(self):
        """Test nested AND/OR evaluation."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.side_effect = [
            {"asset1", "asset2"},  # First AND branch, child 1
            {"asset2", "asset3"},  # First AND branch, child 2
            {"asset4", "asset5"},  # Second AND branch, child 1
            {"asset5", "asset6"},  # Second AND branch, child 2
        ]

        # Create: OR(AND(leaf, leaf), AND(leaf, leaf))
        and1 = ConditionNode(
            ConditionType.AND,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True)),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Apple")),
            ]
        )
        and2 = ConditionNode(
            ConditionType.AND,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Canon")),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(asset_types=["VIDEO"])),
            ]
        )
        or_node = ConditionNode(ConditionType.OR, children=[and1, and2])

        # Evaluate
        result = or_node.evaluate(mock_client)

        # First AND: {asset1, asset2} ∩ {asset2, asset3} = {asset2}
        # Second AND: {asset4, asset5} ∩ {asset5, asset6} = {asset5}
        # OR: {asset2} ∪ {asset5} = {asset2, asset5}
        assert result == {"asset2", "asset5"}

    def test_evaluation_with_base_assets(self):
        """Test evaluation with base asset set (date-filtered)."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.return_value = {"asset1", "asset2", "asset3", "asset4"}

        # Base assets from date range
        base_assets = {"asset2", "asset3", "asset5"}

        # Create leaf node
        condition = FilterCondition(is_favorite=True)
        node = ConditionNode(ConditionType.LEAF, condition=condition)

        # Evaluate
        result = node.evaluate(mock_client, base_assets=base_assets)

        # Should be intersection with base assets
        assert result == {"asset2", "asset3"}

    def test_empty_result_early_exit(self):
        """Test AND operation with early exit on empty result."""
        # Mock client
        mock_client = Mock()
        mock_client.search_assets.side_effect = [
            set(),  # First child returns empty
            {"asset1", "asset2"},  # Second child should not be called
        ]

        # Create AND node
        child1 = ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True))
        child2 = ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Apple"))
        node = ConditionNode(ConditionType.AND, children=[child1, child2])

        # Evaluate
        result = node.evaluate(mock_client)

        # Should return empty and not call second child
        assert result == set()
        assert mock_client.search_assets.call_count == 1


class TestConditionOptimization:
    """Test condition tree optimization."""

    def test_flatten_nested_and(self):
        """Test flattening nested AND nodes."""
        # Create nested AND: AND(leaf1, AND(leaf2, leaf3))
        inner_and = ConditionNode(
            ConditionType.AND,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True)),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Apple")),
            ]
        )
        outer_and = ConditionNode(
            ConditionType.AND,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(asset_types=["IMAGE"])),
                inner_and,
            ]
        )

        # Optimize
        optimized = outer_and.optimize()

        # Should flatten AND nodes, then combine all compatible leaves into single LEAF
        # Since all three filters are compatible, they get combined into one API call
        assert optimized.node_type == ConditionType.LEAF
        assert optimized.condition.is_favorite is True
        assert optimized.condition.camera_make == "Apple"
        assert optimized.condition.asset_types == ["IMAGE"]

    def test_flatten_nested_or(self):
        """Test flattening nested OR nodes."""
        # Create nested OR: OR(leaf1, OR(leaf2, leaf3))
        inner_or = ConditionNode(
            ConditionType.OR,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True)),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Apple")),
            ]
        )
        outer_or = ConditionNode(
            ConditionType.OR,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(asset_types=["IMAGE"])),
                inner_or,
            ]
        )

        # Optimize
        optimized = outer_or.optimize()

        # Should flatten to OR(leaf1, leaf2, leaf3)
        assert optimized.node_type == ConditionType.OR
        assert len(optimized.children) == 3

    def test_combine_and_leaves(self):
        """Test combining AND leaf nodes into single API call."""
        # Create AND with compatible leaves
        node = ConditionNode(
            ConditionType.AND,
            children=[
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True)),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(camera_make="Apple")),
                ConditionNode(ConditionType.LEAF, condition=FilterCondition(asset_types=["IMAGE"])),
            ]
        )

        # Optimize
        optimized = node.optimize()

        # Should combine into single LEAF node
        assert optimized.node_type == ConditionType.LEAF
        assert optimized.condition.is_favorite is True
        assert optimized.condition.camera_make == "Apple"
        assert optimized.condition.asset_types == ["IMAGE"]

    def test_single_child_simplification(self):
        """Test simplification of single-child AND/OR nodes."""
        # Create AND with single child
        leaf = ConditionNode(ConditionType.LEAF, condition=FilterCondition(is_favorite=True))
        and_node = ConditionNode(ConditionType.AND, children=[leaf])

        # Optimize
        optimized = and_node.optimize()

        # Should return the leaf directly
        assert optimized.node_type == ConditionType.LEAF
        assert optimized.condition.is_favorite is True


class TestBackwardCompatibility:
    """Test backward compatibility with old filters format."""

    def test_old_filters_format_still_works(self):
        """Test that old filters format is still supported."""
        rule_config = {
            "id": "old-style",
            "album_name": "Old Style Album",
            "taken_range_utc": {
                "start": "2025-01-01T00:00:00.000Z",
                "end": "2025-12-31T23:59:59.999Z",
            },
            "filters": {
                "is_favorite": True,
                "asset_types": ["IMAGE"],
                "camera": {"make": "Apple"},
            },
        }

        # Should not raise exception
        rule = Rule(rule_config)

        # Should have condition tree (converted from filters)
        assert rule.condition_tree is not None
        assert rule.condition_tree.node_type == ConditionType.LEAF
        assert rule.condition_tree.condition.is_favorite is True
        assert rule.condition_tree.condition.asset_types == ["IMAGE"]
        assert rule.condition_tree.condition.camera_make == "Apple"

    def test_no_filters_creates_empty_condition(self):
        """Test that rule with no filters creates empty condition."""
        rule_config = {
            "id": "no-filters",
            "album_name": "No Filters Album",
            "taken_range_utc": {
                "start": "2025-01-01T00:00:00.000Z",
                "end": "2025-12-31T23:59:59.999Z",
            },
        }

        rule = Rule(rule_config)

        # Should have condition tree
        # Note: For backward compatibility, defaults to IMAGE asset type
        assert rule.condition_tree is not None
        assert rule.condition_tree.node_type == ConditionType.LEAF
        assert rule.condition_tree.condition.asset_types == ["IMAGE"]

    def test_filters_to_tree_conversion(self):
        """Test conversion of RuleFilters to condition tree."""
        rule_config = {
            "id": "conversion-test",
            "album_name": "Conversion Test",
            "filters": {
                "is_favorite": True,
                "asset_types": ["IMAGE", "VIDEO"],
                "camera": {"make": "Apple", "model": "iPhone 15"},
            },
        }

        rule = Rule(rule_config)

        # Verify conversion
        assert rule.filters is not None
        assert rule.condition_tree is not None

        # Condition tree should match filters
        cond = rule.condition_tree.condition
        assert cond.is_favorite == rule.filters.is_favorite
        assert cond.asset_types == rule.filters.asset_types
        assert cond.camera_make == rule.filters.camera_make
        assert cond.camera_model == rule.filters.camera_model


class TestConditionValidation:
    """Test validation of condition structures."""

    def test_valid_and_condition(self):
        """Test validation accepts valid AND condition."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "and-test",
                    "album_name": "AND Test",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "and": [
                            {"is_favorite": True},
                            {"camera": {"make": "Apple"}},
                        ]
                    },
                }
            ],
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True

    def test_valid_or_condition(self):
        """Test validation accepts valid OR condition."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "or-test",
                    "album_name": "OR Test",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "or": [
                            {"is_favorite": True},
                            {"camera": {"make": "Apple"}},
                        ]
                    },
                }
            ],
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True

    def test_valid_nested_condition(self):
        """Test validation accepts nested conditions."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "nested-test",
                    "album_name": "Nested Test",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "or": [
                            {
                                "and": [
                                    {"is_favorite": True},
                                    {"camera": {"make": "Apple"}},
                                ]
                            },
                            {
                                "and": [
                                    {"camera": {"make": "Canon"}},
                                    {"asset_types": ["VIDEO"]},
                                ]
                            },
                        ]
                    },
                }
            ],
        }

        # Should not raise exception
        result = validate_config(config)
        assert result is True

    def test_reject_too_few_operands(self):
        """Test validation rejects AND/OR with < 2 operands."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "too-few",
                    "album_name": "Too Few",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "or": [
                            {"is_favorite": True},
                            # Only one condition!
                        ]
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "'or:' must have at least 2 conditions" in str(e)

    def test_reject_both_filters_and_conditions(self):
        """Test validation rejects having both filters and conditions."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "both",
                    "album_name": "Both",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "filters": {"is_favorite": True},
                    "conditions": {
                        "or": [
                            {"camera": {"make": "Apple"}},
                            {"camera": {"make": "Canon"}},
                        ]
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "Cannot have both 'filters' and 'conditions'" in str(e)

    def test_reject_unknown_logical_operator(self):
        """Test validation rejects unknown logical operators."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "unknown-op",
                    "album_name": "Unknown Op",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "xor": [
                            {"is_favorite": True},
                            {"camera": {"make": "Apple"}},
                        ]
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "xor" in str(e).lower()

    def test_reject_invalid_filter_in_condition(self):
        """Test validation rejects invalid filters in conditions."""
        config = {
            "mode": "add_only",
            "rules": [
                {
                    "id": "invalid-filter",
                    "album_name": "Invalid Filter",
                    "taken_range_utc": {
                        "start": "2025-01-01T00:00:00.000Z",
                        "end": "2025-12-31T23:59:59.999Z",
                    },
                    "conditions": {
                        "and": [
                            {"is_favorite": True},
                            {"asset_types": ["INVALID_TYPE"]},
                        ]
                    },
                }
            ],
        }

        try:
            validate_config(config)
            assert False, "Should have raised ConfigValidationError"
        except ConfigValidationError as e:
            assert "INVALID_TYPE" in str(e)


class TestFilterCondition:
    """Test FilterCondition helper methods."""

    def test_has_filters_returns_true_when_filters_set(self):
        """Test has_filters returns True when filters are set."""
        condition = FilterCondition(is_favorite=True, asset_types=["IMAGE"])
        assert condition.has_filters() is True

    def test_has_filters_returns_false_when_no_filters(self):
        """Test has_filters returns False when no filters set."""
        condition = FilterCondition()
        assert condition.has_filters() is False

    def test_repr_includes_all_filters(self):
        """Test __repr__ includes all filter types."""
        condition = FilterCondition(
            is_favorite=True,
            asset_types=["IMAGE", "VIDEO"],
            camera_make="Apple",
            camera_model="iPhone 15",
        )
        repr_str = repr(condition)

        assert "favorite=True" in repr_str
        assert "types=['IMAGE', 'VIDEO']" in repr_str
        assert "make=Apple" in repr_str
        assert "model=iPhone 15" in repr_str


class TestErrorHandling:
    """Test error handling in condition construction and evaluation."""

    def test_leaf_without_condition_raises_error(self):
        """Test that LEAF node without condition raises error."""
        try:
            node = ConditionNode(ConditionType.LEAF)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "LEAF node must have a condition" in str(e)

    def test_and_without_children_raises_error(self):
        """Test that AND node without children raises error."""
        try:
            node = ConditionNode(ConditionType.AND)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "and node must have at least one child" in str(e).lower()

    def test_or_without_children_raises_error(self):
        """Test that OR node without children raises error."""
        try:
            node = ConditionNode(ConditionType.OR)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "or node must have at least one child" in str(e).lower()

    def test_invalid_config_type_raises_error(self):
        """Test that invalid config type raises error."""
        try:
            node = ConditionNode.from_config("invalid")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid condition config type" in str(e)

    def test_non_list_operands_raises_error(self):
        """Test that non-list operands raise error."""
        try:
            config = {"and": "not-a-list"}
            node = ConditionNode.from_config(config)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "'and:' must be a list" in str(e)


if __name__ == "__main__":
    # Allow running tests directly
    import pytest
    pytest.main([__file__, "-v"])
