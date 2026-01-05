"""
Rule parsing and execution for dynamic album management.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import yaml

from immich_client import ImmichClient
from database import Database
from validation import validate_config, ConfigValidationError
from conditions import ConditionNode, FilterCondition, ConditionType


logger = logging.getLogger(__name__)


class UserResolver:
    """Resolves user identifiers (emails/IDs) to user IDs."""

    def __init__(self, all_users: List[Dict]):
        """
        Initialize the user resolver.

        Args:
            all_users: List of user dicts from get_all_users()
        """
        self.all_users = all_users
        self.email_to_id = {user["email"]: user["id"] for user in all_users}
        self.id_to_email = {user["id"]: user["email"] for user in all_users}
        self.owner_id = None

    def set_owner(self, owner_id: str):
        """
        Set the owner ID to exclude from sharing.

        Args:
            owner_id: The current user's ID (from get_my_user)
        """
        self.owner_id = owner_id

    def resolve_share_identifiers(self, share_with) -> Optional[List[str]]:
        """
        Resolve share_with to user IDs (owner excluded).

        Args:
            share_with: "ALL", list of emails/IDs, or None

        Returns:
            List of user IDs, or None if no valid users
        """
        if share_with is None:
            return None

        if share_with == "ALL":
            return [u["id"] for u in self.all_users if u["id"] != self.owner_id]

        if isinstance(share_with, list):
            resolved_ids = []
            for identifier in share_with:
                user_id = self._resolve_identifier(identifier)
                if user_id and user_id != self.owner_id:
                    resolved_ids.append(user_id)
            return resolved_ids if resolved_ids else None

        return None

    def _resolve_identifier(self, identifier: str) -> Optional[str]:
        """
        Resolve email or user ID to user ID.

        Args:
            identifier: Email address or user ID

        Returns:
            User ID if found, None otherwise
        """
        # Try as email first
        if identifier in self.email_to_id:
            return self.email_to_id[identifier]

        # Fallback to user ID
        if identifier in self.id_to_email:
            return identifier

        logger.warning(f"User '{identifier}' not found")
        return None


class PeopleResolver:
    """Resolves people names to person IDs."""

    def __init__(self, all_people: List[Dict]):
        """
        Initialize with list of people from Immich API.

        Args:
            all_people: List of people dicts with id, name, etc.
        """
        self.all_people = all_people
        self.name_to_id = {person["name"]: person["id"] for person in all_people}

    def resolve_people_names(self, names: List[str]) -> Optional[List[str]]:
        """
        Resolve people names to person IDs.

        Args:
            names: List of person names

        Returns:
            List of person IDs, or None if no valid people found
        """
        if not names:
            return None

        resolved_ids = []
        for name in names:
            if name in self.name_to_id:
                resolved_ids.append(self.name_to_id[name])
            else:
                logger.warning(f"Person '{name}' not found in Immich")

        return resolved_ids if resolved_ids else None


@dataclass
class RuleFilters:
    """
    Represents filters for asset matching.

    This class encapsulates all the various filter criteria that can be applied
    when searching for assets to include in a dynamic album.
    """

    # Favorite filter
    is_favorite: Optional[bool] = None

    # Asset types (e.g., IMAGE, VIDEO)
    asset_types: List[str] = field(default_factory=lambda: ["IMAGE"])

    # Camera filters
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None

    # People filter (names to resolve to IDs)
    include_people: List[str] = field(default_factory=list)

    # Resolution filter (list of [width, height] pairs)
    resolution: Optional[List[List[int]]] = None

    @classmethod
    def from_config(cls, filters_config: Optional[Dict]) -> "RuleFilters":
        """
        Create RuleFilters from configuration dictionary.

        Args:
            filters_config: Filters section from rule configuration, or None

        Returns:
            RuleFilters instance with parsed configuration
        """
        if not filters_config:
            # Return defaults (IMAGE only for backward compatibility)
            return cls()

        # Parse is_favorite
        is_favorite = filters_config.get("is_favorite")

        # Parse asset_types (default to IMAGE for backward compatibility)
        asset_types = filters_config.get("asset_types", ["IMAGE"])
        if not isinstance(asset_types, list):
            asset_types = [asset_types]
        # Normalize to uppercase
        asset_types = [t.upper() for t in asset_types]

        # Parse camera filters
        camera = filters_config.get("camera", {})
        camera_make = camera.get("make") if isinstance(camera, dict) else None
        camera_model = camera.get("model") if isinstance(camera, dict) else None

        # Parse people filter (list of person names to match)
        people = filters_config.get("people", {})
        include_people = people.get("include", []) if isinstance(people, dict) else []

        # Parse resolution filter
        resolution_config = filters_config.get("resolution", {})
        resolution = resolution_config.get("include") if isinstance(resolution_config, dict) else None
        # Don't set resolution if empty list
        if resolution is not None and len(resolution) == 0:
            resolution = None

        return cls(
            is_favorite=is_favorite,
            asset_types=asset_types,
            camera_make=camera_make,
            camera_model=camera_model,
            include_people=include_people,
            resolution=resolution,
        )


class Rule:
    """Represents a single album rule."""

    def __init__(self, rule_config: Dict, people_resolver: Optional['PeopleResolver'] = None):
        """
        Initialize a rule from configuration.

        Args:
            rule_config: Rule configuration dict from YAML
            people_resolver: Optional resolver for people names to IDs (needed for conditions)
        """
        self.id = rule_config["id"]
        self.album_name = rule_config["album_name"]
        self.description = rule_config.get("description")

        # Date range filters (maintained at top level for backward compatibility)
        taken_range = rule_config.get("taken_range_utc", {})
        self.taken_after = taken_range.get("start")
        self.taken_before = taken_range.get("end")

        created_range = rule_config.get("created_range_utc", {})
        self.created_after = created_range.get("start")
        self.created_before = created_range.get("end")

        # Parse share_with for per-rule sharing override
        self.share_with = rule_config.get("share_with")

        # Parse fuzzy_match for per-rule fuzzy matching override
        self.fuzzy_match = rule_config.get("fuzzy_match")  # None, True, or False

        # Determine which format to use: conditions or filters
        if "conditions" in rule_config:
            # New conditions format
            logger.debug(f"Rule {self.id}: Using conditions format")
            self.condition_tree = ConditionNode.from_config(
                rule_config["conditions"],
                people_resolver
            )
            # Optimize the tree to minimize API calls
            self.condition_tree = self.condition_tree.optimize()
            self.filters = None
        else:
            # Old filters format (or no filters)
            filters_config = rule_config.get("filters")
            self.filters = RuleFilters.from_config(filters_config)

            # Convert filters to condition tree for backward compatibility
            self.condition_tree = self._convert_filters_to_tree()

            # Log if using filters
            if filters_config:
                logger.debug(f"Rule {self.id}: Using filters format (converted to conditions)")

    def __repr__(self):
        return f"Rule(id={self.id}, album_name={self.album_name})"

    def _convert_filters_to_tree(self) -> ConditionNode:
        """
        Convert old-style filters to condition tree for backward compatibility.

        Returns:
            ConditionNode representing the filters (single LEAF node)
        """
        if not self.filters:
            # No filters - empty condition
            return ConditionNode(ConditionType.LEAF, condition=FilterCondition())

        # Create filter condition from RuleFilters
        condition = FilterCondition(
            is_favorite=self.filters.is_favorite,
            asset_types=self.filters.asset_types,
            camera_make=self.filters.camera_make,
            camera_model=self.filters.camera_model,
            resolution=self.filters.resolution,
        )

        # Note: people are resolved later in execute(), so we don't set person_ids here
        # They will be passed separately to the evaluation

        return ConditionNode(ConditionType.LEAF, condition=condition)

    def execute(self, client: ImmichClient, people_resolver: Optional['PeopleResolver'] = None) -> Set[str]:
        """
        Execute the rule to find matching assets.

        Args:
            client: Immich API client
            people_resolver: Optional resolver for people names to IDs

        Returns:
            Set of asset IDs that match this rule
        """
        logger.info(f"Executing rule: {self.id} ({self.album_name})")

        # Build date filters dict (if any)
        date_filters = {}
        if self.taken_after:
            date_filters["taken_after"] = self.taken_after
        if self.taken_before:
            date_filters["taken_before"] = self.taken_before
        if self.created_after:
            date_filters["created_after"] = self.created_after
        if self.created_before:
            date_filters["created_before"] = self.created_before

        # For backward compatibility: resolve people in old filters format
        if self.filters and self.filters.include_people and people_resolver:
            include_people_ids = people_resolver.resolve_people_names(self.filters.include_people)
            if include_people_ids:
                logger.debug(f"Resolved {len(self.filters.include_people)} people to {len(include_people_ids)} IDs")
                # Add people to the condition tree's leaf node
                if self.condition_tree.condition:
                    self.condition_tree.condition.person_ids = include_people_ids

        # Get base asset set from date-range query (if we have date filters)
        base_assets = None
        if date_filters:
            # Make initial API call with just date filters to get base set
            logger.debug(f"Fetching base assets with date filters: {date_filters}")
            base_assets = client.search_assets(
                **date_filters,
                default_to_image=False  # Don't default to IMAGE, get all types
            )
            logger.debug(f"Base assets from date range: {len(base_assets)}")

        # Evaluate condition tree
        asset_ids = self.condition_tree.evaluate(
            client,
            base_assets=base_assets,
            date_filters=date_filters if date_filters else None
        )

        logger.info(f"Rule {self.id} matched {len(asset_ids)} assets")
        return asset_ids


class RuleEngine:
    """Manages and executes album rules."""

    def __init__(
        self,
        config_path: str,
        default_timezone: str = "America/New_York",
        people_resolver: Optional['PeopleResolver'] = None
    ):
        """
        Initialize the rule engine.

        Args:
            config_path: Path to the YAML configuration file
            default_timezone: Default IANA timezone for recurring rules
            people_resolver: Optional resolver for people names to IDs (needed for conditions)
        """
        self.config_path = config_path
        self.default_timezone = default_timezone
        self.people_resolver = people_resolver
        self.mode = "add_only"
        self.rules: List[Rule] = []
        self._load_config()

    def _create_local_midnight_utc(
        self, year: int, month: int, day: int, tz_name: str, duration_days: int
    ) -> tuple[str, str]:
        """
        Create start/end datetimes for a local calendar day, converted to UTC.

        This method creates timezone-aware datetimes for the beginning and end of a
        calendar day in the specified timezone, then converts them to UTC for use in
        the IMMICH API. This ensures that recurring rules capture photos taken during
        the local calendar day, not the UTC calendar day.

        Args:
            year: Year
            month: Month (1-12)
            day: Day (1-31)
            tz_name: IANA timezone name (e.g., "America/New_York")
            duration_days: Number of days to include

        Returns:
            Tuple of (start_str, end_str) in ISO 8601 format with UTC timezone

        Example:
            Christmas 2025 in America/New_York (EST, UTC-5):
            - Input: year=2025, month=12, day=25, tz_name="America/New_York", duration_days=1
            - Local start: 2025-12-25 00:00:00 EST
            - UTC start: 2025-12-25T05:00:00.000Z
            - Local end: 2025-12-26 00:00:00 EST
            - UTC end: 2025-12-26T05:00:00.000Z
        """
        # Create timezone object
        tz = ZoneInfo(tz_name)

        # Create timezone-aware datetime at midnight in the specified timezone
        local_start = datetime(year, month, day, 0, 0, 0, tzinfo=tz)

        # Calculate end datetime (start + duration)
        local_end = local_start + timedelta(days=duration_days)

        # Convert to UTC
        utc_start = local_start.astimezone(timezone.utc)
        utc_end = local_end.astimezone(timezone.utc)

        # Format as ISO 8601 with milliseconds and Z suffix
        start_str = utc_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_str = utc_end.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        return start_str, end_str

    def _expand_recurring_rule(self, rule_config: Dict) -> List[Dict]:
        """
        Expand a recurring rule into multiple year-specific rules.

        Args:
            rule_config: Rule configuration with recurring settings

        Returns:
            List of expanded rule configurations (one per year)
        """
        base_id = rule_config["id"]
        month_day = rule_config["month_day"]  # Format: "MM-DD" e.g., "12-25"
        album_name_template = rule_config["album_name_template"]
        year_range = rule_config["year_range"]  # [start_year, end_year]
        duration_days = rule_config.get("duration_days", 1)
        description = rule_config.get("description", "Auto-managed by dynamic-albums script")
        filters = rule_config.get("filters", {})
        conditions = rule_config.get("conditions")  # May be None if using filters
        tz_name = rule_config["timezone"]  # Required field (validated)

        expanded_rules = []

        # Parse month and day
        month, day = map(int, month_day.split("-"))

        # Generate rule for each year
        for year in range(year_range[0], year_range[1] + 1):
            try:
                # Create timezone-aware start/end datetimes converted to UTC
                start_str, end_str = self._create_local_midnight_utc(
                    year, month, day, tz_name, duration_days
                )

                # Create expanded rule config
                expanded_rule = {
                    "id": f"{base_id}-{year}",
                    "album_name": album_name_template.format(year=year),
                    "description": description,
                    "taken_range_utc": {
                        "start": start_str,
                        "end": end_str,
                    },
                }

                # Include either conditions or filters (not both)
                if conditions:
                    expanded_rule["conditions"] = conditions
                if filters:
                    expanded_rule["filters"] = filters

                expanded_rules.append(expanded_rule)
                logger.debug(f"Expanded recurring rule {base_id} for year {year}")
            except ValueError as e:
                # Skip invalid dates (e.g., Feb 29 in non-leap years)
                logger.debug(f"Skipping invalid date for {base_id} year {year}: {e}")
                continue

        logger.info(f"Expanded recurring rule '{base_id}' into {len(expanded_rules)} year-specific rules")
        return expanded_rules

    def _load_config(self):
        """Load configuration from YAML file."""
        logger.info(f"Loading configuration from: {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate configuration before processing
        try:
            validate_config(config)
        except ConfigValidationError as e:
            logger.error(f"Configuration validation failed:\n{str(e)}")
            raise

        self.mode = config.get("mode", "add_only")
        logger.info(f"Sync mode: {self.mode}")

        rules_config = config.get("rules", [])

        # Expand recurring rules
        expanded_rules_config = []
        for rule_config in rules_config:
            if rule_config.get("recurring"):
                # Expand this recurring rule into multiple year-specific rules
                expanded = self._expand_recurring_rule(rule_config)
                expanded_rules_config.extend(expanded)
            else:
                # Regular rule, add as-is
                expanded_rules_config.append(rule_config)

        # Create Rule objects from expanded config
        for rule_config in expanded_rules_config:
            rule = Rule(rule_config, people_resolver=self.people_resolver)
            self.rules.append(rule)
            logger.debug(f"Loaded rule: {rule}")

        logger.info(f"Loaded {len(self.rules)} rules")

    def has_per_rule_sharing(self) -> bool:
        """
        Check if any rule has per-rule sharing configured.

        Returns:
            True if at least one rule has share_with field
        """
        return any(rule.share_with is not None for rule in self.rules)

    def has_people_filtering(self) -> bool:
        """
        Check if any rule has people filtering configured.

        Returns:
            True if at least one rule has people filter
        """
        for rule in self.rules:
            # Check filters format
            if rule.filters and rule.filters.include_people:
                return True
            # Check conditions format
            if hasattr(rule, 'conditions') and rule.conditions:
                # Check if any condition tree has people filters
                if self._conditions_has_people(rule.conditions):
                    return True
        return False

    def _conditions_has_people(self, node) -> bool:
        """Recursively check if condition tree contains people filters."""
        if hasattr(node, 'include_people') and node.include_people:
            return True
        if hasattr(node, 'conditions'):
            return any(self._conditions_has_people(c) for c in node.conditions)
        return False

    def _resolve_share_user_ids(
        self,
        rule: Rule,
        global_share_user_ids: Optional[List[str]],
        user_resolver: Optional['UserResolver']
    ) -> Optional[List[str]]:
        """
        Resolve share_user_ids with per-rule override priority.

        Priority:
            1. Per-rule share_with (if present)
            2. Global default

        Args:
            rule: Rule to resolve sharing for
            global_share_user_ids: Global default sharing list
            user_resolver: UserResolver instance for email→ID resolution

        Returns:
            List of user IDs to share with, or None for private
        """
        # Check per-rule override
        if rule.share_with is not None:
            if not user_resolver:
                logger.warning(f"Rule '{rule.id}' has share_with but no resolver")
                return None

            resolved = user_resolver.resolve_share_identifiers(rule.share_with)

            if resolved:
                logger.debug(f"Rule '{rule.id}': Per-rule sharing with {len(resolved)} user(s)")
            else:
                logger.warning(f"Rule '{rule.id}': share_with specified but no valid users")

            return resolved

        # Use global default
        return global_share_user_ids

    def sync_rule(
        self,
        rule: Rule,
        client: ImmichClient,
        db: Database,
        dry_run: bool = False,
        global_share_user_ids: Optional[List[str]] = None,
        user_resolver: Optional['UserResolver'] = None,
        people_resolver: Optional['PeopleResolver'] = None,
        global_fuzzy_match: bool = False
    ) -> Dict:
        """
        Sync a single rule.

        Args:
            rule: Rule to sync
            client: Immich API client
            db: Database connection
            dry_run: If True, only log what would be done
            global_share_user_ids: Global default list of user IDs to share albums with
            user_resolver: UserResolver for per-rule sharing resolution
            people_resolver: PeopleResolver for resolving people names to IDs
            global_fuzzy_match: Global fuzzy matching setting (can be overridden per-rule)

        Returns:
            Dict with sync statistics
        """
        stats = {
            "rule_id": rule.id,
            "album_name": rule.album_name,
            "assets_added": 0,
            "assets_removed": 0,
        }

        # Find assets matching this rule (exact matches)
        # Use self.people_resolver (set during RuleEngine initialization)
        desired_asset_ids = rule.execute(client, self.people_resolver)

        # Determine if fuzzy matching is enabled for this rule
        fuzzy_enabled = rule.fuzzy_match if rule.fuzzy_match is not None else global_fuzzy_match

        # Run fuzzy matching if enabled and we have exact matches
        fuzzy_asset_ids = set()
        if fuzzy_enabled and desired_asset_ids:
            from fuzzy_matcher import FuzzyMatcher

            logger.info(f"Running fuzzy matching for rule {rule.id} ({len(desired_asset_ids)} exact matches)")
            fuzzy_matcher = FuzzyMatcher(client)

            # Build date filters dict for fuzzy matcher
            date_filters = {}
            if rule.taken_after:
                date_filters["taken_after"] = rule.taken_after
            if rule.taken_before:
                date_filters["taken_before"] = rule.taken_before
            if rule.created_after:
                date_filters["created_after"] = rule.created_after
            if rule.created_before:
                date_filters["created_before"] = rule.created_before

            try:
                fuzzy_asset_ids = fuzzy_matcher.find_related_assets(desired_asset_ids, date_filters)
                logger.info(f"Fuzzy matching found {len(fuzzy_asset_ids)} related assets for rule {rule.id}")
            except Exception as e:
                logger.error(f"Fuzzy matching failed for rule {rule.id}: {str(e)}", exc_info=True)
                # Continue without fuzzy matches

        # Combine exact and fuzzy matches
        all_asset_ids = desired_asset_ids | fuzzy_asset_ids

        if not all_asset_ids:
            logger.info(f"No assets (exact or fuzzy) match rule {rule.id}, skipping")
            return stats

        # Record analyzed assets (both exact and fuzzy)
        for asset_id in all_asset_ids:
            db.record_analyzed_asset(asset_id)

        # Find or create the album
        album = client.find_album_by_name(rule.album_name)

        if not album:
            # New album - create with sharing
            if dry_run:
                logger.info(f"[DRY RUN] Would create album: {rule.album_name}")
            else:
                share_ids = self._resolve_share_user_ids(rule, global_share_user_ids, user_resolver)
                logger.info(f"Creating album: {rule.album_name}")
                album = client.create_album(
                    album_name=rule.album_name,
                    description=rule.description,
                    share_user_ids=share_ids,
                )
        else:
            # Existing album - update sharing if needed
            if not dry_run and user_resolver:
                share_ids = self._resolve_share_user_ids(rule, global_share_user_ids, user_resolver)

                if share_ids is not None and client.has_sharing_changed(album, share_ids):
                    logger.info(f"Updating sharing for '{rule.album_name}': {len(share_ids)} user(s)")
                    updated_album = client.update_album_sharing(album["id"], share_ids)
                    if updated_album:
                        album = updated_album  # Use updated album data

        album_id = album.get("id") if album else None

        if self.mode == "add_only":
            # Add-only mode: just add new assets
            if album_id:
                # Get assets we've already added (Dict[asset_id -> match_type])
                known_assets = db.get_album_assets_for_rule(rule.id, album_id)
                known_asset_ids = set(known_assets.keys())

                # Split new additions by type
                exact_to_add = desired_asset_ids - known_asset_ids
                fuzzy_to_add = fuzzy_asset_ids - known_asset_ids

                if exact_to_add or fuzzy_to_add:
                    total_to_add = len(exact_to_add) + len(fuzzy_to_add)
                    if dry_run:
                        logger.info(f"[DRY RUN] Would add {total_to_add} assets to {rule.album_name} ({len(exact_to_add)} exact, {len(fuzzy_to_add)} fuzzy)")
                    else:
                        # Add exact matches
                        if exact_to_add:
                            logger.info(f"Adding {len(exact_to_add)} exact match assets to {rule.album_name}")
                            client.add_assets_to_album(album_id, exact_to_add)
                            db.record_album_membership(rule.id, album_id, rule.album_name, exact_to_add, match_type='exact')
                            stats["assets_added"] += len(exact_to_add)

                        # Add fuzzy matches
                        if fuzzy_to_add:
                            logger.info(f"Adding {len(fuzzy_to_add)} fuzzy match assets to {rule.album_name}")
                            client.add_assets_to_album(album_id, fuzzy_to_add)
                            db.record_album_membership(rule.id, album_id, rule.album_name, fuzzy_to_add, match_type='fuzzy')
                            stats["assets_added"] += len(fuzzy_to_add)
                else:
                    logger.info(f"No new assets to add for rule {rule.id}")
        else:
            # True sync mode: add missing, remove extras
            if album_id:
                # Get assets we've already added (Dict[asset_id -> match_type])
                known_assets = db.get_album_assets_for_rule(rule.id, album_id)
                known_asset_ids = set(known_assets.keys())

                # Split additions by type
                exact_to_add = desired_asset_ids - known_asset_ids
                fuzzy_to_add = fuzzy_asset_ids - known_asset_ids

                # Remove assets that are no longer matched (exact or fuzzy)
                to_remove = known_asset_ids - all_asset_ids

                if exact_to_add or fuzzy_to_add:
                    total_to_add = len(exact_to_add) + len(fuzzy_to_add)
                    if dry_run:
                        logger.info(f"[DRY RUN] Would add {total_to_add} assets to {rule.album_name} ({len(exact_to_add)} exact, {len(fuzzy_to_add)} fuzzy)")
                    else:
                        # Add exact matches
                        if exact_to_add:
                            logger.info(f"Adding {len(exact_to_add)} exact match assets to {rule.album_name}")
                            client.add_assets_to_album(album_id, exact_to_add)
                            db.record_album_membership(rule.id, album_id, rule.album_name, exact_to_add, match_type='exact')
                            stats["assets_added"] += len(exact_to_add)

                        # Add fuzzy matches
                        if fuzzy_to_add:
                            logger.info(f"Adding {len(fuzzy_to_add)} fuzzy match assets to {rule.album_name}")
                            client.add_assets_to_album(album_id, fuzzy_to_add)
                            db.record_album_membership(rule.id, album_id, rule.album_name, fuzzy_to_add, match_type='fuzzy')
                            stats["assets_added"] += len(fuzzy_to_add)

                if to_remove:
                    if dry_run:
                        logger.info(f"[DRY RUN] Would remove {len(to_remove)} assets from {rule.album_name}")
                    else:
                        logger.info(f"Removing {len(to_remove)} assets from {rule.album_name}")
                        client.remove_assets_from_album(album_id, to_remove)
                        db.remove_album_memberships(rule.id, album_id, to_remove)
                        stats["assets_removed"] = len(to_remove)

                if not exact_to_add and not fuzzy_to_add and not to_remove:
                    logger.info(f"Album {rule.album_name} is already in sync")

        return stats

    def sync_all(
        self,
        client: ImmichClient,
        db: Database,
        dry_run: bool = False,
        global_share_user_ids: Optional[List[str]] = None,
        user_resolver: Optional['UserResolver'] = None,
        people_resolver: Optional['PeopleResolver'] = None,
        global_fuzzy_match: bool = False
    ) -> Dict:
        """
        Sync all rules.

        Args:
            client: Immich API client
            db: Database connection
            dry_run: If True, only log what would be done
            global_share_user_ids: Global default list of user IDs to share albums with
            user_resolver: UserResolver for per-rule sharing resolution
            people_resolver: DEPRECATED - now uses self.people_resolver from RuleEngine initialization
            global_fuzzy_match: Global fuzzy matching setting (can be overridden per-rule)

        Returns:
            Dict with overall sync statistics
        """
        overall_stats = {
            "rules_processed": 0,
            "total_assets_added": 0,
            "total_assets_removed": 0,
            "errors": [],
        }

        for rule in self.rules:
            try:
                stats = self.sync_rule(
                    rule, client, db, dry_run,
                    global_share_user_ids, user_resolver, people_resolver,
                    global_fuzzy_match
                )
                overall_stats["rules_processed"] += 1
                overall_stats["total_assets_added"] += stats["assets_added"]
                overall_stats["total_assets_removed"] += stats["assets_removed"]
            except Exception as e:
                error_msg = f"Error processing rule {rule.id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                overall_stats["errors"].append(error_msg)

        return overall_stats
