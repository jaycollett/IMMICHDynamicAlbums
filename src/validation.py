"""
Configuration validation for Immich Dynamic Albums.

This module provides comprehensive validation for the YAML configuration file,
ensuring all rules are properly formatted with valid dates, unique IDs, and
correct filter specifications.
"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo, available_timezones

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Base exception for configuration validation errors."""
    pass


class DateFormatError(ConfigValidationError):
    """Exception raised when date format is invalid."""
    pass


class DuplicateRuleError(ConfigValidationError):
    """Exception raised when duplicate rule IDs are found."""
    pass


class ConfigValidator:
    """
    Validates configuration files for Immich Dynamic Albums.

    Performs comprehensive validation including:
    - ISO 8601 date format validation with timezone checking
    - Rule ID uniqueness validation
    - Mode enum validation
    - Required field checking
    - Filter structure validation
    """

    VALID_MODES = {"add_only", "sync"}
    VALID_ASSET_TYPES = {"IMAGE", "VIDEO", "AUDIO", "OTHER"}

    # ISO 8601 date format regex (supports various formats with timezone)
    ISO_8601_PATTERN = re.compile(
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$'
    )

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the validator with a configuration dict.

        Args:
            config: Configuration dictionary loaded from YAML
        """
        self.config = config
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        """
        Perform full validation of the configuration.

        Returns:
            True if validation passes, False otherwise

        Raises:
            ConfigValidationError: If validation fails with detailed error message
        """
        self.errors = []
        self.warnings = []

        # Validate top-level structure
        self._validate_mode()
        self._validate_rules_exist()

        # Validate each rule
        if "rules" in self.config:
            self._validate_rules()

        # Report results
        if self.warnings:
            for warning in self.warnings:
                logger.warning(f"Configuration warning: {warning}")

        if self.errors:
            error_message = self._format_error_message()
            raise ConfigValidationError(error_message)

        logger.info("Configuration validation passed successfully")
        return True

    def _validate_mode(self):
        """Validate the sync mode setting."""
        mode = self.config.get("mode", "add_only")

        if mode not in self.VALID_MODES:
            self.errors.append(
                f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(self.VALID_MODES))}.\n"
                f"  Suggestion: Use 'add_only' (safer, only adds assets) or 'sync' (adds and removes assets)."
            )

    def _validate_rules_exist(self):
        """Ensure at least one rule is defined."""
        rules = self.config.get("rules", [])

        if not rules:
            self.errors.append(
                "No rules defined in configuration.\n"
                "  Suggestion: Add at least one rule under the 'rules:' section."
            )
        elif not isinstance(rules, list):
            self.errors.append(
                "Rules must be a list.\n"
                "  Suggestion: Ensure 'rules:' is followed by a list of rule definitions."
            )

    def _validate_rules(self):
        """Validate all rules."""
        rules = self.config.get("rules", [])
        seen_ids: Set[str] = set()

        for idx, rule in enumerate(rules):
            rule_context = f"Rule #{idx + 1}"

            if not isinstance(rule, dict):
                self.errors.append(
                    f"{rule_context}: Rule must be a dictionary, got {type(rule).__name__}."
                )
                continue

            # Add ID to context if available
            rule_id = rule.get("id")
            if rule_id:
                rule_context = f"Rule '{rule_id}'"

            # Validate required fields
            self._validate_required_fields(rule, rule_context)

            # Check for duplicate IDs
            if rule_id:
                if rule_id in seen_ids:
                    self.errors.append(
                        f"{rule_context}: Duplicate rule ID '{rule_id}'.\n"
                        f"  Suggestion: Each rule must have a unique ID."
                    )
                seen_ids.add(rule_id)

            # Validate date ranges
            self._validate_date_ranges(rule, rule_context)

            # Validate filters or conditions (mutually exclusive)
            if "filters" in rule and "conditions" in rule:
                self.errors.append(
                    f"{rule_context}: Cannot have both 'filters' and 'conditions'.\n"
                    f"  Suggestion: Use either 'filters:' (old format) or 'conditions:' (new AND/OR format)."
                )
            elif "filters" in rule:
                self._validate_filters(rule["filters"], rule_context)
            elif "conditions" in rule:
                self._validate_conditions(rule["conditions"], rule_context)

            # Validate share_with (if present)
            if "share_with" in rule:
                self._validate_share_with(rule["share_with"], rule_context)

            # Validate fuzzy_match (if present)
            if "fuzzy_match" in rule:
                fuzzy_match = rule["fuzzy_match"]
                if not isinstance(fuzzy_match, bool):
                    self.errors.append(
                        f"{rule_context}: 'fuzzy_match' must be a boolean (true/false).\n"
                        f"  Suggestion: Use 'fuzzy_match: true' to enable or 'fuzzy_match: false' to disable."
                    )

            # Check for deprecated format and warn
            self._check_deprecated_format(rule, rule_context)

    def _validate_required_fields(self, rule: Dict[str, Any], context: str):
        """Validate that required fields are present."""
        # Check if this is a recurring rule
        if rule.get("recurring"):
            # Recurring rules have different required fields
            required_fields = ["id", "recurring", "month_day", "album_name_template", "year_range", "timezone"]

            for field in required_fields:
                if field not in rule:
                    self.errors.append(
                        f"{context}: Missing required field '{field}' for recurring rule.\n"
                        f"  Suggestion: Add '{field}:' to the recurring rule definition."
                    )
                elif field == "year_range":
                    # Validate year_range is a list of two integers
                    year_range = rule.get("year_range")
                    if not isinstance(year_range, list) or len(year_range) != 2:
                        self.errors.append(
                            f"{context}: 'year_range' must be a list of two years [start_year, end_year]."
                        )
                    elif not all(isinstance(y, int) for y in year_range):
                        self.errors.append(
                            f"{context}: 'year_range' must contain integers."
                        )
                    elif year_range[0] > year_range[1]:
                        self.errors.append(
                            f"{context}: 'year_range' start year must be <= end year."
                        )
                elif field == "month_day":
                    # Validate month_day format "MM-DD"
                    month_day = rule.get("month_day")
                    if not isinstance(month_day, str):
                        self.errors.append(
                            f"{context}: 'month_day' must be a string in format 'MM-DD' (e.g., '12-25')."
                        )
                    elif not re.match(r'^\d{2}-\d{2}$', month_day):
                        self.errors.append(
                            f"{context}: 'month_day' must be in format 'MM-DD' (e.g., '12-25'), got '{month_day}'."
                        )
                elif field == "timezone":
                    # Validate timezone is a valid IANA timezone name
                    timezone = rule.get("timezone")
                    if timezone:
                        self._validate_timezone(timezone, context)
                elif not rule[field]:
                    self.errors.append(
                        f"{context}: Field '{field}' cannot be empty."
                    )
        else:
            # Regular rules
            required_fields = ["id", "album_name"]

            for field in required_fields:
                if field not in rule:
                    self.errors.append(
                        f"{context}: Missing required field '{field}'.\n"
                        f"  Suggestion: Add '{field}:' to the rule definition."
                    )
                elif not rule[field]:
                    self.errors.append(
                        f"{context}: Field '{field}' cannot be empty."
                    )

    def _validate_date_ranges(self, rule: Dict[str, Any], context: str):
        """Validate date range formats and logic."""
        # Skip date range validation for recurring rules (they generate dates automatically)
        if rule.get("recurring"):
            return

        # Validate taken_range_utc
        taken_range = rule.get("taken_range_utc", {})
        if taken_range:
            self._validate_date_range(taken_range, "taken_range_utc", context)

        # Validate created_range_utc
        created_range = rule.get("created_range_utc", {})
        if created_range:
            self._validate_date_range(created_range, "created_range_utc", context)

        # Check that at least one filter is specified
        has_taken = taken_range and (taken_range.get("start") or taken_range.get("end"))
        has_created = created_range and (created_range.get("start") or created_range.get("end"))
        has_filters = "filters" in rule

        if not (has_taken or has_created or has_filters):
            self.warnings.append(
                f"{context}: No filters specified. This rule will match no assets.\n"
                f"  Suggestion: Add at least one date range or filter."
            )

    def _validate_date_range(
        self,
        date_range: Dict[str, Any],
        range_name: str,
        context: str
    ):
        """Validate a date range object."""
        if not isinstance(date_range, dict):
            self.errors.append(
                f"{context}: {range_name} must be a dictionary with 'start' and/or 'end' fields."
            )
            return

        start = date_range.get("start")
        end = date_range.get("end")

        # Validate start date
        if start:
            self._validate_iso8601_date(start, f"{context}: {range_name}.start")

        # Validate end date
        if end:
            self._validate_iso8601_date(end, f"{context}: {range_name}.end")

        # Validate logical consistency
        if start and end:
            try:
                start_dt = self._parse_iso8601(start)
                end_dt = self._parse_iso8601(end)

                if start_dt >= end_dt:
                    self.errors.append(
                        f"{context}: {range_name} start date must be before end date.\n"
                        f"  Start: {start}\n"
                        f"  End: {end}"
                    )
            except ValueError:
                # Skip comparison if dates are invalid (will be caught by format validation)
                pass

    def _validate_iso8601_date(self, date_str: str, context: str):
        """
        Validate ISO 8601 date format.

        Args:
            date_str: Date string to validate
            context: Context for error messages

        Raises:
            Adds error to self.errors if validation fails
        """
        if not isinstance(date_str, str):
            self.errors.append(
                f"{context}: Date must be a string, got {type(date_str).__name__}."
            )
            return

        # Check format with regex first
        if not self.ISO_8601_PATTERN.match(date_str):
            self.errors.append(
                f"{context}: Invalid ISO 8601 date format '{date_str}'.\n"
                f"  Expected format: YYYY-MM-DDTHH:MM:SS.mmmZ or YYYY-MM-DDTHH:MM:SS+HH:MM\n"
                f"  Examples:\n"
                f"    - 2025-12-25T00:00:00.000Z (UTC)\n"
                f"    - 2025-12-25T00:00:00Z (UTC without milliseconds)\n"
                f"    - 2025-12-25T12:00:00+05:30 (with timezone offset)"
            )
            return

        # Try to parse to ensure it's a valid date
        try:
            self._parse_iso8601(date_str)
        except ValueError as e:
            self.errors.append(
                f"{context}: Invalid date value '{date_str}': {str(e)}\n"
                f"  Suggestion: Check that the date components are valid (e.g., no February 31st)."
            )

    def _parse_iso8601(self, date_str: str) -> datetime:
        """
        Parse an ISO 8601 date string.

        Args:
            date_str: ISO 8601 formatted date string

        Returns:
            datetime object

        Raises:
            ValueError: If date string cannot be parsed
        """
        # Handle 'Z' suffix (UTC timezone)
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'

        # Try parsing with different formats
        for fmt in [
            '%Y-%m-%dT%H:%M:%S.%f%z',  # With milliseconds and timezone
            '%Y-%m-%dT%H:%M:%S%z',      # Without milliseconds
        ]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Could not parse date: {date_str}")

    def _validate_timezone(self, tz_name: str, context: str):
        """
        Validate IANA timezone name using zoneinfo.

        Args:
            tz_name: IANA timezone name (e.g., "America/New_York")
            context: Context string for error messages

        Adds error to self.errors if timezone is invalid.
        """
        if not isinstance(tz_name, str):
            self.errors.append(
                f"{context}: timezone must be a string (IANA timezone name).\n"
                f"  Example: 'America/New_York', 'Europe/London', 'UTC'"
            )
            return

        # Check if timezone is valid
        try:
            ZoneInfo(tz_name)
        except Exception:
            # Provide helpful suggestions for common mistakes
            common_timezones = [
                "America/New_York", "America/Chicago", "America/Denver",
                "America/Los_Angeles", "America/Phoenix", "Pacific/Honolulu",
                "Europe/London", "Europe/Paris", "Asia/Tokyo", "UTC"
            ]

            suggestions = []
            # Check for common mistakes
            if tz_name in ["EST", "EDT", "PST", "PDT", "CST", "CDT"]:
                suggestions.append(
                    f"  '{tz_name}' is an abbreviation. Use full IANA name like 'America/New_York' instead."
                )
            elif "/" not in tz_name:
                suggestions.append(
                    f"  Timezone must be in format 'Region/City' (e.g., 'America/New_York')."
                )

            # Suggest similar timezones
            tz_lower = tz_name.lower()
            similar = [tz for tz in common_timezones if tz_lower in tz.lower()]
            if similar:
                suggestions.append(f"  Did you mean: {', '.join(similar)}?")
            else:
                suggestions.append(f"  Common timezones: {', '.join(common_timezones[:5])}")

            error_msg = f"{context}: Invalid timezone '{tz_name}'."
            if suggestions:
                error_msg += "\n" + "\n".join(suggestions)

            self.errors.append(error_msg)

    def _validate_filters(self, filters: Dict[str, Any], context: str):
        """Validate the filters section."""
        if not isinstance(filters, dict):
            self.errors.append(
                f"{context}: filters must be a dictionary."
            )
            return

        # Validate is_favorite
        if "is_favorite" in filters:
            if not isinstance(filters["is_favorite"], bool):
                self.errors.append(
                    f"{context}: filters.is_favorite must be a boolean (true/false)."
                )

        # Validate asset_types
        if "asset_types" in filters:
            asset_types = filters["asset_types"]
            if not isinstance(asset_types, list):
                self.errors.append(
                    f"{context}: filters.asset_types must be a list."
                )
            else:
                for asset_type in asset_types:
                    if asset_type not in self.VALID_ASSET_TYPES:
                        self.errors.append(
                            f"{context}: Invalid asset_type '{asset_type}'. "
                            f"Must be one of: {', '.join(sorted(self.VALID_ASSET_TYPES))}."
                        )

        # Validate camera filters
        if "camera" in filters:
            camera = filters["camera"]
            if not isinstance(camera, dict):
                self.errors.append(
                    f"{context}: filters.camera must be a dictionary."
                )
            else:
                if "make" in camera and not isinstance(camera["make"], str):
                    self.errors.append(
                        f"{context}: filters.camera.make must be a string."
                    )
                if "model" in camera and not isinstance(camera["model"], str):
                    self.errors.append(
                        f"{context}: filters.camera.model must be a string."
                    )

        # Validate people
        if "people" in filters:
            people = filters["people"]
            if not isinstance(people, dict):
                self.errors.append(
                    f"{context}: filters.people must be a dictionary."
                )
            else:
                if "include" in people:
                    if not isinstance(people["include"], list):
                        self.errors.append(
                            f"{context}: filters.people.include must be a list."
                        )
                    elif not all(isinstance(name, str) for name in people["include"]):
                        self.errors.append(
                            f"{context}: filters.people.include must contain only strings."
                        )

        # Validate tags
        if "tags" in filters:
            tags = filters["tags"]
            if not isinstance(tags, dict):
                self.errors.append(
                    f"{context}: filters.tags must be a dictionary."
                )
            else:
                if "include" in tags:
                    if not isinstance(tags["include"], list):
                        self.errors.append(
                            f"{context}: filters.tags.include must be a list."
                        )
                    elif not all(isinstance(tag, str) for tag in tags["include"]):
                        self.errors.append(
                            f"{context}: filters.tags.include must contain only strings."
                        )

                if "exclude" in tags:
                    if not isinstance(tags["exclude"], list):
                        self.errors.append(
                            f"{context}: filters.tags.exclude must be a list."
                        )
                    elif not all(isinstance(tag, str) for tag in tags["exclude"]):
                        self.errors.append(
                            f"{context}: filters.tags.exclude must contain only strings."
                        )

        # Validate resolution
        if "resolution" in filters:
            resolution = filters["resolution"]
            if not isinstance(resolution, dict):
                self.errors.append(
                    f"{context}: filters.resolution must be a dictionary."
                )
            else:
                if "include" in resolution:
                    include = resolution["include"]
                    if not isinstance(include, list):
                        self.errors.append(
                            f"{context}: filters.resolution.include must be a list of [width, height] pairs."
                        )
                    else:
                        for idx, res in enumerate(include):
                            if not isinstance(res, list):
                                self.errors.append(
                                    f"{context}: filters.resolution.include[{idx}] must be a list [width, height]."
                                )
                            elif len(res) != 2:
                                self.errors.append(
                                    f"{context}: filters.resolution.include[{idx}] must have exactly 2 elements [width, height]."
                                )
                            elif not all(isinstance(v, int) and v > 0 for v in res):
                                self.errors.append(
                                    f"{context}: filters.resolution.include[{idx}] must contain positive integers."
                                )

    def _validate_conditions(self, conditions: Any, context: str):
        """
        Recursively validate AND/OR condition structure.

        Args:
            conditions: Conditions dict from rule configuration
            context: Context string for error messages
        """
        if not isinstance(conditions, dict):
            self.errors.append(
                f"{context}: conditions must be a dictionary.\n"
                f"  Expected format: {{'and': [...]}}, {{'or': [...]}}, or leaf condition"
            )
            return

        # Check if this is a logical operator (and/or)
        if "and" in conditions:
            self._validate_logical_operator(conditions["and"], "and", context)
        elif "or" in conditions:
            self._validate_logical_operator(conditions["or"], "or", context)
        else:
            # This is a leaf condition - validate as filter
            self._validate_leaf_condition(conditions, context)

    def _validate_logical_operator(self, operands: Any, operator: str, context: str):
        """
        Validate AND/OR logical operator.

        Args:
            operands: List of operands for the logical operator
            operator: "and" or "or"
            context: Context string for error messages
        """
        if not isinstance(operands, list):
            self.errors.append(
                f"{context}: '{operator}:' must be a list of conditions.\n"
                f"  Example:\n"
                f"    {operator}:\n"
                f"      - is_favorite: true\n"
                f"      - camera:\n"
                f"          make: Apple"
            )
            return

        if len(operands) < 2:
            self.errors.append(
                f"{context}: '{operator}:' must have at least 2 conditions.\n"
                f"  Found {len(operands)} condition(s). Add more conditions to use '{operator}:'."
            )
            return

        # Recursively validate each operand
        for idx, operand in enumerate(operands):
            operand_context = f"{context}.{operator}[{idx}]"
            self._validate_conditions(operand, operand_context)

    def _validate_leaf_condition(self, condition: Dict[str, Any], context: str):
        """
        Validate a leaf condition (actual filter).

        Leaf conditions use the same format as the filters section,
        so we can reuse the existing filter validation.

        Args:
            condition: Leaf condition dict
            context: Context string for error messages
        """
        # Check for unknown logical operators
        unknown_operators = []
        for key in condition.keys():
            if key in ["and", "or"]:
                # This shouldn't happen here (should be caught by _validate_conditions)
                unknown_operators.append(key)
            elif key not in ["is_favorite", "asset_types", "camera", "people", "tags", "resolution"]:
                # Unknown filter key
                unknown_operators.append(key)

        if unknown_operators:
            # Check if they look like logical operators
            if any(op.lower() in ["not", "xor", "nor", "nand"] for op in unknown_operators):
                self.errors.append(
                    f"{context}: Unknown logical operator(s): {', '.join(unknown_operators)}.\n"
                    f"  Supported operators: 'and', 'or'\n"
                    f"  If you meant to use a filter, check the filter name spelling."
                )
            else:
                valid_filters = ["is_favorite", "asset_types", "camera", "people", "tags", "resolution"]
                self.errors.append(
                    f"{context}: Unknown filter(s): {', '.join(unknown_operators)}.\n"
                    f"  Valid filters: {', '.join(valid_filters)}"
                )

        # Reuse existing filter validation logic
        self._validate_filters(condition, context)

    def _validate_share_with(self, share_with: Any, context: str):
        """Validate share_with field format."""
        if share_with == "ALL":
            return  # Valid

        if isinstance(share_with, list):
            if len(share_with) == 0:
                self.warnings.append(
                    f"{context}: 'share_with' list is empty, album will be private"
                )
                return

            for idx, item in enumerate(share_with):
                if not isinstance(item, str):
                    self.errors.append(
                        f"{context}: 'share_with[{idx}]' must be a string"
                    )
                elif not item.strip():
                    self.errors.append(
                        f"{context}: 'share_with[{idx}]' cannot be empty"
                    )
                elif "@" not in item:
                    self.warnings.append(
                        f"{context}: 'share_with[{idx}]' ('{item}') doesn't look like an email address. "
                        f"Will try as user ID if email lookup fails."
                    )
        else:
            self.errors.append(
                f"{context}: 'share_with' must be 'ALL' or a list of email addresses.\n"
                f"  Examples:\n"
                f"    share_with: ALL\n"
                f"    share_with: [\"user1@example.com\", \"user2@example.com\"]"
            )

    def _check_deprecated_format(self, rule: Dict[str, Any], context: str):
        """Check for deprecated configuration format and provide migration guidance."""
        # Check if old format is being used (date ranges at top level without filters)
        has_old_taken = "taken_range_utc" in rule
        has_old_created = "created_range_utc" in rule
        has_new_filters = "filters" in rule

        if (has_old_taken or has_old_created) and not has_new_filters:
            # This is acceptable - old format is still supported
            logger.debug(f"{context}: Using backward-compatible date range format")
        elif has_new_filters:
            # Check if date ranges are duplicated in both places
            if has_old_taken or has_old_created:
                self.warnings.append(
                    f"{context}: Both old-style date ranges and new 'filters' section found.\n"
                    f"  The date ranges at the rule level will be used. Consider migrating to the new format:\n"
                    f"  Old format:\n"
                    f"    taken_range_utc:\n"
                    f"      start: ...\n"
                    f"  New format:\n"
                    f"    filters:\n"
                    f"      is_favorite: true\n"
                    f"      asset_types: [IMAGE]\n"
                    f"      # (date ranges stay at rule level for now)"
                )

    def _format_error_message(self) -> str:
        """Format all validation errors into a comprehensive message."""
        lines = [
            "",
            "=" * 70,
            "Configuration Validation Failed",
            "=" * 70,
            "",
            f"Found {len(self.errors)} error(s):",
            ""
        ]

        for i, error in enumerate(self.errors, 1):
            lines.append(f"{i}. {error}")
            lines.append("")

        lines.extend([
            "=" * 70,
            "Please fix the above errors and try again.",
            "=" * 70,
        ])

        return "\n".join(lines)


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Convenience function to validate a configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if validation passes

    Raises:
        ConfigValidationError: If validation fails
    """
    validator = ConfigValidator(config)
    return validator.validate()
