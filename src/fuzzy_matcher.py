"""
Fuzzy matching module for finding assets related to exact matches via metadata proximity.
"""
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Optional, Set

from dateutil.parser import parse as parse_iso8601

from immich_client import ImmichClient


logger = logging.getLogger(__name__)

# Performance tuning constants
MAX_FUZZY_SEEDS = 50  # Maximum number of exact matches to use as seeds
PARALLEL_WORKERS = 10  # Number of parallel threads for metadata fetching


@dataclass
class AssetMetadata:
    """Metadata for proximity calculations."""
    asset_id: str
    timestamp: Optional[datetime]
    latitude: Optional[float]
    longitude: Optional[float]


class FuzzyMatcher:
    """Finds assets related to exact matches via metadata proximity."""

    def __init__(
        self,
        client: ImmichClient,
        time_window_minutes: int = 240,
        location_radius_meters: float = 100.0
    ):
        """
        Initialize the fuzzy matcher.

        Args:
            client: Immich API client
            time_window_minutes: Time window for proximity matching (default: 240 = 4 hours)
            location_radius_meters: GPS radius for proximity matching (default: 100)
        """
        self.client = client
        self.time_window = timedelta(minutes=time_window_minutes)
        self.location_radius = location_radius_meters

    def find_related_assets(
        self,
        exact_match_ids: Set[str],
        rule_date_filters: Dict
    ) -> Set[str]:
        """
        Find assets related to exact matches via proximity.

        Args:
            exact_match_ids: Asset IDs from exact rule matching
            rule_date_filters: Original rule date filters (for API queries)

        Returns:
            Set of asset IDs found via fuzzy matching (excludes exact matches)
        """
        if not exact_match_ids:
            logger.debug("No exact matches provided for fuzzy matching")
            return set()

        logger.info(f"Starting fuzzy matching for {len(exact_match_ids)} exact matches")

        # Performance safeguard: sample if too many exact matches
        if len(exact_match_ids) > MAX_FUZZY_SEEDS:
            logger.info(f"Sampling {MAX_FUZZY_SEEDS} assets from {len(exact_match_ids)} exact matches")
            sampled_ids = set(random.sample(list(exact_match_ids), MAX_FUZZY_SEEDS))
        else:
            sampled_ids = exact_match_ids

        # Step 1: Fetch metadata for exact matches
        exact_metadata = self._fetch_asset_metadata(sampled_ids)
        if not exact_metadata:
            logger.warning("Could not fetch metadata for any exact matches")
            return set()

        logger.debug(f"Fetched metadata for {len(exact_metadata)} assets")

        # Step 2: Calculate expanded time boundaries (clamped to rule boundaries)
        start_time, end_time = self._calculate_time_boundaries(exact_metadata, rule_date_filters)
        logger.debug(f"Expanded time window: {start_time} to {end_time}")

        # Step 3: Query candidates within time window
        candidates = self._query_candidates(start_time, end_time, rule_date_filters)
        if not candidates:
            logger.info("No candidate assets found in expanded time window")
            return set()

        logger.info(f"Found {len(candidates)} candidate assets in time window")

        # Step 4: Filter by proximity (time + GPS if available)
        fuzzy_matches = self._filter_by_proximity(candidates, exact_metadata)

        # Step 5: Exclude exact matches from fuzzy results
        fuzzy_matches = fuzzy_matches - exact_match_ids

        logger.info(f"Fuzzy matching found {len(fuzzy_matches)} related assets")
        return fuzzy_matches

    def _fetch_asset_metadata(self, asset_ids: Set[str]) -> List[AssetMetadata]:
        """
        Fetch timestamp and GPS data for assets in parallel.

        Args:
            asset_ids: Set of asset IDs to fetch

        Returns:
            List of AssetMetadata objects (may be shorter if some fetches fail)
        """
        asset_id_list = list(asset_ids)

        def fetch_single(asset_id: str) -> Optional[AssetMetadata]:
            """Fetch metadata for a single asset."""
            try:
                asset_data = self.client.get_asset_metadata(asset_id)
                return self._extract_metadata(asset_data)
            except Exception as e:
                logger.warning(f"Failed to fetch metadata for asset {asset_id}: {str(e)}")
                return None

        # Fetch in parallel using ThreadPoolExecutor
        metadata_list = []
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = [executor.submit(fetch_single, aid) for aid in asset_id_list]
            for future in futures:
                result = future.result()
                if result:
                    metadata_list.append(result)

        return metadata_list

    def _extract_metadata(self, asset: Dict) -> Optional[AssetMetadata]:
        """
        Extract timestamp and GPS from asset data.

        Args:
            asset: Asset dict from Immich API

        Returns:
            AssetMetadata or None if no timestamp available
        """
        asset_id = asset.get('id')

        # Extract timestamp (priority: exifInfo.dateTimeOriginal > fileCreatedAt > fileModifiedAt)
        timestamp = None
        exif = asset.get('exifInfo', {})

        if exif.get('dateTimeOriginal'):
            try:
                timestamp = parse_iso8601(exif['dateTimeOriginal'])
            except Exception as e:
                logger.warning(f"Asset {asset_id}: Failed to parse dateTimeOriginal: {e}")

        if not timestamp and asset.get('fileCreatedAt'):
            try:
                timestamp = parse_iso8601(asset['fileCreatedAt'])
            except Exception as e:
                logger.warning(f"Asset {asset_id}: Failed to parse fileCreatedAt: {e}")

        if not timestamp and asset.get('fileModifiedAt'):
            try:
                timestamp = parse_iso8601(asset['fileModifiedAt'])
                logger.debug(f"Asset {asset_id}: Using fileModifiedAt (no EXIF date)")
            except Exception as e:
                logger.warning(f"Asset {asset_id}: Failed to parse fileModifiedAt: {e}")

        if not timestamp:
            logger.warning(f"Asset {asset_id}: No timestamp available, skipping")
            return None

        # Extract GPS coordinates
        latitude = exif.get('latitude')
        longitude = exif.get('longitude')

        return AssetMetadata(
            asset_id=asset_id,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude
        )

    def _calculate_time_boundaries(
        self,
        metadata_list: List[AssetMetadata],
        rule_date_filters: Dict
    ) -> tuple:
        """
        Calculate expanded time range covering all matches + window.
        Clamps to rule date boundaries to ensure we don't extend beyond the 24-hour day period.

        Args:
            metadata_list: List of asset metadata
            rule_date_filters: Rule date filters with taken_after/before or created_after/before

        Returns:
            Tuple of (start_time, end_time)
        """
        timestamps = [m.timestamp for m in metadata_list if m.timestamp]

        if not timestamps:
            raise ValueError("No valid timestamps found in metadata")

        min_time = min(timestamps)
        max_time = max(timestamps)

        # Expand by time_window on both sides
        start_time = min_time - self.time_window
        end_time = max_time + self.time_window

        # Clamp to rule date boundaries if available
        # Check for taken date boundaries first, then created date boundaries
        if 'taken_after' in rule_date_filters:
            rule_start = parse_iso8601(rule_date_filters['taken_after'])
            start_time = max(start_time, rule_start)

        if 'taken_before' in rule_date_filters:
            rule_end = parse_iso8601(rule_date_filters['taken_before'])
            end_time = min(end_time, rule_end)

        if 'created_after' in rule_date_filters:
            rule_start = parse_iso8601(rule_date_filters['created_after'])
            start_time = max(start_time, rule_start)

        if 'created_before' in rule_date_filters:
            rule_end = parse_iso8601(rule_date_filters['created_before'])
            end_time = min(end_time, rule_end)

        return start_time, end_time

    def _query_candidates(
        self,
        start_time: datetime,
        end_time: datetime,
        rule_date_filters: Dict
    ) -> Set[str]:
        """
        Query Immich for assets within expanded time window.

        Args:
            start_time: Start of expanded window
            end_time: End of expanded window
            rule_date_filters: Original rule date filters (to determine which date field to use)

        Returns:
            Set of candidate asset IDs
        """
        # Determine which date field to use based on original rule
        use_taken_date = 'taken_after' in rule_date_filters or 'taken_before' in rule_date_filters

        try:
            if use_taken_date:
                candidates = self.client.search_assets(
                    taken_after=start_time.isoformat(),
                    taken_before=end_time.isoformat(),
                    asset_types=["IMAGE", "VIDEO"],  # Match all asset types
                    default_to_image=False
                )
            else:
                # Use created date range
                candidates = self.client.search_assets(
                    created_after=start_time.isoformat(),
                    created_before=end_time.isoformat(),
                    asset_types=["IMAGE", "VIDEO"],
                    default_to_image=False
                )

            return candidates

        except Exception as e:
            logger.error(f"Failed to query candidates: {str(e)}")
            return set()

    def _filter_by_proximity(
        self,
        candidates: Set[str],
        exact_metadata: List[AssetMetadata]
    ) -> Set[str]:
        """
        Filter candidates by time and GPS proximity to exact matches.

        Args:
            candidates: Set of candidate asset IDs
            exact_metadata: Metadata of exact match assets

        Returns:
            Set of asset IDs within proximity thresholds
        """
        if not candidates:
            return set()

        # Fetch metadata for candidates
        candidate_metadata = self._fetch_asset_metadata(candidates)
        if not candidate_metadata:
            return set()

        fuzzy_matches = set()

        for candidate in candidate_metadata:
            if not candidate.timestamp:
                continue  # Skip if no timestamp

            # Check if within time_window AND location_radius of ANY exact match
            for exact in exact_metadata:
                if not exact.timestamp:
                    continue

                # Check time proximity
                time_diff = abs((candidate.timestamp - exact.timestamp).total_seconds())
                if time_diff > self.time_window.total_seconds():
                    continue  # Too far in time

                # Check GPS proximity (if both have GPS)
                if candidate.latitude and candidate.longitude and exact.latitude and exact.longitude:
                    distance = self._haversine_distance(
                        candidate.latitude, candidate.longitude,
                        exact.latitude, exact.longitude
                    )

                    if distance > self.location_radius:
                        continue  # Too far in distance

                # If we reach here, candidate is within proximity
                fuzzy_matches.add(candidate.asset_id)
                break  # No need to check other exact matches

        logger.debug(f"Filtered {len(candidate_metadata)} candidates to {len(fuzzy_matches)} fuzzy matches")
        return fuzzy_matches

    def _haversine_distance(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate distance in meters between two GPS coordinates using Haversine formula.

        Args:
            lat1: Latitude of point 1
            lon1: Longitude of point 1
            lat2: Latitude of point 2
            lon2: Longitude of point 2

        Returns:
            Distance in meters
        """
        # Earth radius in meters
        R = 6371000

        # Convert to radians
        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        return R * c
