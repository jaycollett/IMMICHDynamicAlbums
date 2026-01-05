"""
Condition tree structure for AND/OR logical operations.

This module provides a tree-based structure for evaluating complex filter conditions
with AND/OR logic. Conditions can be nested to arbitrary depth to express queries like:
- (filter1 AND filter2)
- (filter1 OR filter2 OR filter3)
- ((filter1 AND filter2) OR (filter3 AND filter4))
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class ConditionType(Enum):
    """Type of condition node."""
    AND = "and"
    OR = "or"
    LEAF = "leaf"


@dataclass
class FilterCondition:
    """
    Represents a leaf condition (actual filter).

    This encapsulates all possible filter types that can be applied
    to assets in a single API call or client-side filtering operation.
    """
    # Favorite filter
    is_favorite: Optional[bool] = None

    # Asset types (e.g., IMAGE, VIDEO)
    asset_types: Optional[List[str]] = None

    # Camera filters
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None

    # People filter (person IDs - already resolved)
    person_ids: Optional[List[str]] = None

    # Tags (for future implementation)
    include_tags: Optional[List[str]] = None
    exclude_tags: Optional[List[str]] = None

    # Resolution filter (list of [width, height] pairs)
    resolution: Optional[List[List[int]]] = None

    def has_filters(self) -> bool:
        """Check if this condition has any filters set."""
        return any([
            self.is_favorite is not None,
            self.asset_types is not None,
            self.camera_make is not None,
            self.camera_model is not None,
            self.person_ids is not None,
            self.include_tags is not None,
            self.exclude_tags is not None,
            self.resolution is not None,
        ])

    def __repr__(self):
        parts = []
        if self.is_favorite is not None:
            parts.append(f"favorite={self.is_favorite}")
        if self.asset_types:
            parts.append(f"types={self.asset_types}")
        if self.camera_make:
            parts.append(f"make={self.camera_make}")
        if self.camera_model:
            parts.append(f"model={self.camera_model}")
        if self.person_ids:
            parts.append(f"people={len(self.person_ids)}")
        if self.include_tags:
            parts.append(f"tags+={self.include_tags}")
        if self.exclude_tags:
            parts.append(f"tags-={self.exclude_tags}")
        if self.resolution:
            parts.append(f"resolution={len(self.resolution)} sizes")
        return f"FilterCondition({', '.join(parts)})"


class ConditionNode:
    """
    Tree node for AND/OR logical conditions.

    A condition tree is built from YAML configuration and evaluated recursively:
    - LEAF nodes contain actual filters and make API calls
    - AND nodes intersect results from all children
    - OR nodes union results from all children
    """

    def __init__(
        self,
        node_type: ConditionType,
        children: Optional[List['ConditionNode']] = None,
        condition: Optional[FilterCondition] = None,
    ):
        """
        Initialize a condition node.

        Args:
            node_type: Type of node (AND, OR, LEAF)
            children: Child nodes (for AND/OR nodes)
            condition: Filter condition (for LEAF nodes)
        """
        self.node_type = node_type
        self.children = children or []
        self.condition = condition

        # Validation
        if node_type in (ConditionType.AND, ConditionType.OR):
            if not self.children:
                raise ValueError(f"{node_type.value} node must have at least one child")
        elif node_type == ConditionType.LEAF:
            if condition is None:
                raise ValueError("LEAF node must have a condition")

    @classmethod
    def from_config(cls, config: Any, people_resolver=None) -> 'ConditionNode':
        """
        Parse configuration into a condition tree.

        Args:
            config: Configuration dict/list from YAML
            people_resolver: Optional resolver for people names to IDs

        Returns:
            Root ConditionNode

        Examples:
            # Simple leaf
            {"is_favorite": true} → LEAF node

            # AND operation
            {"and": [{"is_favorite": true}, {"camera": {"make": "Apple"}}]}
            → AND node with 2 LEAF children

            # OR operation
            {"or": [{"people": {"include": ["Jay"]}}, {"people": {"include": ["Alice"]}}]}
            → OR node with 2 LEAF children

            # Nested
            {"or": [{"and": [...]}, {"and": [...]}]}
            → OR node with 2 AND children
        """
        # Check if this is a logical operator
        if isinstance(config, dict):
            if "and" in config:
                # AND node
                operands = config["and"]
                if not isinstance(operands, list):
                    raise ValueError("'and:' must be a list of conditions")

                children = [cls.from_config(operand, people_resolver) for operand in operands]
                return cls(ConditionType.AND, children=children)

            elif "or" in config:
                # OR node
                operands = config["or"]
                if not isinstance(operands, list):
                    raise ValueError("'or:' must be a list of conditions")

                children = [cls.from_config(operand, people_resolver) for operand in operands]
                return cls(ConditionType.OR, children=children)

            else:
                # Leaf condition
                return cls._parse_leaf_condition(config, people_resolver)

        else:
            raise ValueError(f"Invalid condition config type: {type(config).__name__}")

    @classmethod
    def _parse_leaf_condition(cls, config: Dict, people_resolver=None) -> 'ConditionNode':
        """
        Parse a leaf condition from config.

        Args:
            config: Filter configuration dict
            people_resolver: Optional resolver for people names to IDs

        Returns:
            LEAF ConditionNode
        """
        condition = FilterCondition()

        # Parse is_favorite
        if "is_favorite" in config:
            condition.is_favorite = config["is_favorite"]

        # Parse asset_types
        if "asset_types" in config:
            asset_types = config["asset_types"]
            if not isinstance(asset_types, list):
                asset_types = [asset_types]
            condition.asset_types = [t.upper() for t in asset_types]

        # Parse camera filters
        if "camera" in config:
            camera = config["camera"]
            if isinstance(camera, dict):
                condition.camera_make = camera.get("make")
                condition.camera_model = camera.get("model")

        # Parse people filter
        if "people" in config:
            people = config["people"]
            if isinstance(people, dict):
                include_people = people.get("include", [])

                # Resolve people names to IDs
                if include_people and people_resolver:
                    person_ids = people_resolver.resolve_people_names(include_people)
                    if person_ids:
                        condition.person_ids = person_ids
                    else:
                        logger.warning(f"No valid people found for: {include_people}")
                        # Set to empty list to indicate filter was requested but no matches
                        # This will cause evaluation to return empty set instead of all assets
                        condition.person_ids = []

        # Parse tags (for future implementation)
        if "tags" in config:
            tags = config["tags"]
            if isinstance(tags, dict):
                condition.include_tags = tags.get("include")
                condition.exclude_tags = tags.get("exclude")

        # Parse resolution filter
        if "resolution" in config:
            resolution = config["resolution"]
            if isinstance(resolution, dict):
                include_resolutions = resolution.get("include", [])
                if include_resolutions:
                    condition.resolution = include_resolutions

        return cls(ConditionType.LEAF, condition=condition)

    def evaluate(
        self,
        client,
        base_assets: Optional[Set[str]] = None,
        date_filters: Optional[Dict] = None,
    ) -> Set[str]:
        """
        Recursively evaluate the condition tree.

        Args:
            client: ImmichClient instance for API calls
            base_assets: Optional set of assets to filter (from date-range query)
            date_filters: Optional dict with date range filters to apply

        Returns:
            Set of asset IDs that match this condition
        """
        if self.node_type == ConditionType.LEAF:
            return self._evaluate_leaf(client, base_assets, date_filters)

        elif self.node_type == ConditionType.AND:
            # Intersection of all children
            if not self.children:
                return set()

            logger.debug(f"AND node evaluating {len(self.children)} children")
            result = None
            for i, child in enumerate(self.children):
                logger.debug(f"AND child {i+1}/{len(self.children)}: {child.node_type}")
                child_result = child.evaluate(client, base_assets, date_filters)
                logger.debug(f"AND child {i+1} returned {len(child_result)} assets")
                if result is None:
                    result = child_result
                else:
                    result = result & child_result
                    logger.debug(f"AND intersection: {len(result)} assets remain")

                # Early exit if result is empty
                if not result:
                    logger.debug("AND early exit: empty result")
                    return set()

            return result if result is not None else set()

        elif self.node_type == ConditionType.OR:
            # Union of all children
            result = set()
            logger.debug(f"OR node evaluating {len(self.children)} children")
            for i, child in enumerate(self.children):
                logger.debug(f"OR child {i+1}/{len(self.children)}: {child.node_type}")
                child_result = child.evaluate(client, base_assets, date_filters)
                logger.debug(f"OR child {i+1} returned {len(child_result)} assets")
                result = result | child_result
                logger.debug(f"OR union: {len(result)} assets total")

            return result

        else:
            raise ValueError(f"Unknown node type: {self.node_type}")

    def _evaluate_leaf(
        self,
        client,
        base_assets: Optional[Set[str]],
        date_filters: Optional[Dict],
    ) -> Set[str]:
        """
        Evaluate a leaf condition by making API call(s).

        Args:
            client: ImmichClient instance
            base_assets: Optional set of assets to filter
            date_filters: Optional dict with date range filters

        Returns:
            Set of asset IDs matching this leaf condition
        """
        if not self.condition or not self.condition.has_filters():
            # No filters - return base assets or empty set
            return base_assets if base_assets is not None else set()

        # Build search parameters
        search_params = {}

        # Add date filters if provided
        if date_filters:
            search_params.update(date_filters)

        # Add this condition's filters
        if self.condition.is_favorite is not None:
            search_params["is_favorite"] = self.condition.is_favorite

        if self.condition.asset_types is not None:
            search_params["asset_types"] = self.condition.asset_types

        if self.condition.camera_make:
            search_params["camera_make"] = self.condition.camera_make

        if self.condition.camera_model:
            search_params["camera_model"] = self.condition.camera_model

        if self.condition.person_ids is not None:
            # Empty list means filter was requested but no valid people found
            # Return empty set immediately (no matches possible)
            if len(self.condition.person_ids) == 0:
                logger.debug("People filter requested but no valid people found - returning empty set")
                return set()
            search_params["include_people_ids"] = self.condition.person_ids

        # Make API call
        logger.debug(f"Evaluating leaf condition: {self.condition}")
        asset_ids = client.search_assets(**search_params)

        # Intersect with base assets if provided
        if base_assets is not None:
            asset_ids = asset_ids & base_assets

        # Client-side filtering for resolution (if specified)
        if self.condition.resolution and asset_ids:
            resolution_filter = ResolutionFilter(client)
            asset_ids = resolution_filter.filter_by_resolution(
                asset_ids,
                self.condition.resolution
            )

        # TODO: Client-side filtering for tags when implemented

        return asset_ids

    def optimize(self) -> 'ConditionNode':
        """
        Optimize the condition tree to minimize API calls.

        Optimizations:
        1. Combine adjacent AND LEAF nodes into single API call
        2. Flatten nested AND/OR nodes of same type
        3. Remove empty nodes

        Returns:
            Optimized ConditionNode (may be self)
        """
        # Recursively optimize children first
        if self.children:
            self.children = [child.optimize() for child in self.children]

        # Optimization 1: Flatten nested nodes of same type
        if self.node_type in (ConditionType.AND, ConditionType.OR):
            flattened_children = []
            for child in self.children:
                if child.node_type == self.node_type:
                    # Merge same-type child's children into this level
                    flattened_children.extend(child.children)
                else:
                    flattened_children.append(child)
            self.children = flattened_children

        # Optimization 2: Combine adjacent AND LEAF nodes
        if self.node_type == ConditionType.AND:
            combined = self._combine_and_leaves()
            if combined:
                return combined

        # Optimization 3: Simplify single-child AND/OR nodes
        if self.node_type in (ConditionType.AND, ConditionType.OR):
            if len(self.children) == 1:
                # Single child - return it directly
                return self.children[0]
            elif len(self.children) == 0:
                # Empty node - return empty leaf
                return ConditionNode(ConditionType.LEAF, condition=FilterCondition())

        return self

    def _combine_and_leaves(self) -> Optional['ConditionNode']:
        """
        Combine adjacent LEAF nodes in an AND operation into a single API call.

        Returns:
            Combined LEAF node if all children are compatible, None otherwise
        """
        # Check if all children are LEAF nodes
        if not all(child.node_type == ConditionType.LEAF for child in self.children):
            return None

        # Check if all leaves can be combined (no conflicting filters)
        combined_condition = FilterCondition()

        for child in self.children:
            if not child.condition:
                continue

            cond = child.condition

            # Check for conflicts and combine
            if cond.is_favorite is not None:
                if combined_condition.is_favorite is not None:
                    # Conflicting favorites - can't combine
                    return None
                combined_condition.is_favorite = cond.is_favorite

            if cond.asset_types is not None:
                if combined_condition.asset_types is not None:
                    # Intersect asset types
                    combined_condition.asset_types = list(
                        set(combined_condition.asset_types) & set(cond.asset_types)
                    )
                    if not combined_condition.asset_types:
                        # Empty intersection - no results possible
                        return ConditionNode(ConditionType.LEAF, condition=FilterCondition())
                else:
                    combined_condition.asset_types = cond.asset_types

            if cond.camera_make:
                if combined_condition.camera_make and combined_condition.camera_make != cond.camera_make:
                    # Conflicting makes - can't combine
                    return None
                combined_condition.camera_make = cond.camera_make

            if cond.camera_model:
                if combined_condition.camera_model and combined_condition.camera_model != cond.camera_model:
                    # Conflicting models - can't combine
                    return None
                combined_condition.camera_model = cond.camera_model

            if cond.person_ids:
                if combined_condition.person_ids is not None:
                    # Can't combine multiple people filters in single API call
                    # Each people filter needs its own API call for proper OR/AND logic
                    # (API uses AND logic: multiple personIds = ALL people must be present)
                    return None
                combined_condition.person_ids = cond.person_ids

        # Successfully combined all conditions
        logger.debug(f"Combined {len(self.children)} AND leaves into single condition")
        return ConditionNode(ConditionType.LEAF, condition=combined_condition)

    def __repr__(self):
        if self.node_type == ConditionType.LEAF:
            return f"LEAF({self.condition})"
        else:
            return f"{self.node_type.value.upper()}({len(self.children)} children)"


class ResolutionFilter:
    """
    Client-side resolution filtering with parallel metadata fetching.

    This class filters assets based on their resolution (width x height).
    Since resolution data is not available via the search API, we fetch
    asset metadata in parallel and filter client-side.
    """

    def __init__(self, client, max_workers: int = 10):
        """
        Initialize resolution filter.

        Args:
            client: ImmichClient instance
            max_workers: Number of parallel workers for metadata fetching
        """
        self.client = client
        self.max_workers = max_workers

    def filter_by_resolution(
        self,
        asset_ids: Set[str],
        target_resolutions: List[List[int]]
    ) -> Set[str]:
        """
        Filter assets by resolution.

        Args:
            asset_ids: Set of asset IDs to filter
            target_resolutions: List of [width, height] pairs to match

        Returns:
            Set of asset IDs that match any of the target resolutions
        """
        if not asset_ids or not target_resolutions:
            return set()

        logger.info(f"Filtering {len(asset_ids)} assets by {len(target_resolutions)} resolution(s)")

        # Convert target resolutions to set of tuples for fast lookup
        target_set = {tuple(res) for res in target_resolutions}

        # Fetch metadata in parallel
        from concurrent.futures import ThreadPoolExecutor

        matching_assets = set()
        asset_id_list = list(asset_ids)

        def check_single_asset(asset_id: str) -> Optional[str]:
            """Check if single asset matches resolution filter."""
            try:
                asset_data = self.client.get_asset_metadata(asset_id)
                resolution = self._extract_resolution(asset_data)

                if resolution and resolution in target_set:
                    return asset_id
                return None

            except Exception as e:
                logger.warning(f"Failed to fetch metadata for asset {asset_id}: {str(e)}")
                return None

        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(check_single_asset, aid) for aid in asset_id_list]
            for future in futures:
                result = future.result()
                if result:
                    matching_assets.add(result)

        logger.info(f"Resolution filter matched {len(matching_assets)} assets")
        return matching_assets

    def _extract_resolution(self, asset: Dict) -> Optional[tuple]:
        """
        Extract resolution from asset metadata.

        Priority:
        1. exifInfo.exifImageWidth/Height (EXIF data - most accurate)
        2. originalWidth/Height (file metadata fallback)

        Args:
            asset: Asset dict from Immich API

        Returns:
            Tuple of (width, height) or None if not available
        """
        exif = asset.get('exifInfo', {})

        # Try EXIF dimensions first (most accurate)
        exif_width = exif.get('exifImageWidth')
        exif_height = exif.get('exifImageHeight')

        if exif_width and exif_height:
            return (int(exif_width), int(exif_height))

        # Fallback to original dimensions
        orig_width = asset.get('originalWidth')
        orig_height = asset.get('originalHeight')

        if orig_width and orig_height:
            return (int(orig_width), int(orig_height))

        logger.debug(f"Asset {asset.get('id')}: No resolution metadata available")
        return None
