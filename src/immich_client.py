"""
Immich API client for managing albums and searching assets.
"""
import logging
import time
from typing import Dict, List, Optional, Set
import requests
from requests.adapters import HTTPAdapter


logger = logging.getLogger(__name__)


class ImmichClient:
    """Client for interacting with Immich API."""

    def __init__(self, base_url: str, api_key: str):
        """
        Initialize the Immich client.

        Args:
            base_url: Immich API base URL (e.g., https://immich.example.com/api)
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
        }
        self.session = requests.Session()
        # Configure HTTPAdapter with larger connection pool for parallel processing
        adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.session.headers.update(self.headers)
        self._user_cache = None

    def get_my_user(self) -> Dict:
        """Get current user information."""
        if self._user_cache is None:
            url = f"{self.base_url}/users/me"
            response = self.session.get(url)
            response.raise_for_status()
            self._user_cache = response.json()
        return self._user_cache

    def get_all_users(self) -> List[Dict]:
        """
        Get all users on the server.

        Returns:
            List of user dicts with id, email, name, etc.
        """
        url = f"{self.base_url}/users"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def get_all_people(self) -> List[Dict]:
        """
        Get all people (faces) from the server.

        Returns:
            List of people dicts with id, name, etc.
        """
        url = f"{self.base_url}/people"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("people", [])

    def get_asset_metadata(self, asset_id: str) -> Dict:
        """
        Fetch full metadata for a single asset.

        Args:
            asset_id: ID of the asset to fetch

        Returns:
            Dict with asset metadata including exifInfo, fileCreatedAt, etc.
        """
        url = f"{self.base_url}/assets/{asset_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def search_assets(
        self,
        taken_after: Optional[str] = None,
        taken_before: Optional[str] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        is_favorite: Optional[bool] = None,
        asset_types: Optional[List[str]] = None,
        camera_make: Optional[str] = None,
        camera_model: Optional[str] = None,
        include_people_ids: Optional[List[str]] = None,
        page_size: int = 1000,
        default_to_image: bool = True,
    ) -> Set[str]:
        """
        Search for assets by metadata.

        Args:
            taken_after: ISO 8601 timestamp for earliest taken date
            taken_before: ISO 8601 timestamp for latest taken date
            created_after: ISO 8601 timestamp for earliest created date
            created_before: ISO 8601 timestamp for latest created date
            is_favorite: Filter by favorite status
            asset_types: List of asset types to include (e.g., ["IMAGE", "VIDEO"]).
                        Pass empty list or None to fetch all types.
            camera_make: Filter by camera make
            camera_model: Filter by camera model
            include_people_ids: List of person IDs (assets must have at least one of these people)
            page_size: Number of results per page
            default_to_image: If True and asset_types is None, default to ["IMAGE"] for
                            backward compatibility. Set to False to fetch all types when None.

        Returns:
            Set of asset IDs matching the criteria
        """
        url = f"{self.base_url}/search/metadata"
        asset_ids = set()
        page = 1

        # Handle asset_types default
        filter_by_type = True
        if asset_types is None:
            if default_to_image:
                # Backward compatibility: default to IMAGE only
                asset_types = ["IMAGE"]
            else:
                # New behavior: fetch all types, no filtering
                filter_by_type = False
                asset_types = []  # Empty list for logging only

        while True:
            payload = {
                "page": page,
                "size": page_size,
            }

            # Add date filters
            if taken_after:
                payload["takenAfter"] = taken_after
            if taken_before:
                payload["takenBefore"] = taken_before
            if created_after:
                payload["createdAfter"] = created_after
            if created_before:
                payload["createdBefore"] = created_before

            # Add favorite filter
            if is_favorite is not None:
                payload["isFavorite"] = is_favorite

            # Add camera filters
            if camera_make:
                payload["make"] = camera_make
            if camera_model:
                payload["model"] = camera_model

            # Add people filter
            # IMPORTANT: Immich API uses AND logic for personIds
            # Multiple IDs = assets with ALL of those people (not ANY)
            # Example: personIds: [id1, id2] → returns assets with person1 AND person2
            # For OR logic (ANY person), use explicit OR conditions which make separate API calls
            if include_people_ids:
                payload["personIds"] = include_people_ids

            logger.debug(f"Searching assets: page {page}, payload: {payload}")
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            # Extract asset IDs from the response
            assets = data.get("assets", {}).get("items", [])
            if not assets:
                break

            # Filter by asset types (if specified)
            for asset in assets:
                asset_type = asset.get("type", "").upper()
                if filter_by_type:
                    if asset_type in asset_types:
                        asset_ids.add(asset["id"])
                    else:
                        logger.debug(f"Skipping asset {asset.get('id')} (type: {asset_type}, wanted: {asset_types})")
                else:
                    # No type filtering - include all
                    asset_ids.add(asset["id"])

            # Check if there are more pages
            next_page = data.get("assets", {}).get("nextPage")
            if next_page is None:
                break

            page = next_page
            time.sleep(0.1)  # Be nice to the API

        if filter_by_type and asset_types:
            asset_type_str = ", ".join(asset_types)
            logger.info(f"Found {len(asset_ids)} assets ({asset_type_str}) matching criteria")
        else:
            logger.info(f"Found {len(asset_ids)} assets (all types) matching criteria")
        return asset_ids

    def list_albums(self) -> List[Dict]:
        """List all albums."""
        url = f"{self.base_url}/albums"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def find_album_by_name(self, album_name: str) -> Optional[Dict]:
        """
        Find an album by name.

        Args:
            album_name: Name of the album to find

        Returns:
            Album dict if found, None otherwise
        """
        albums = self.list_albums()
        for album in albums:
            if album.get("albumName") == album_name:
                # Fetch full album details (list_albums doesn't include albumUsers)
                album_id = album.get("id")
                if album_id:
                    url = f"{self.base_url}/albums/{album_id}"
                    response = self.session.get(url)
                    response.raise_for_status()
                    return response.json()
                return album
        return None

    def create_album(
        self,
        album_name: str,
        description: Optional[str] = None,
        asset_ids: Optional[List[str]] = None,
        share_user_ids: Optional[List[str]] = None,
    ) -> Dict:
        """
        Create a new album.

        Args:
            album_name: Name for the new album
            description: Optional description
            asset_ids: Optional initial asset IDs to add
            share_user_ids: Optional list of user IDs to share album with (as viewers)

        Returns:
            Created album dict
        """
        me = self.get_my_user()
        url = f"{self.base_url}/albums"

        # Build album payload
        payload = {
            "albumName": album_name,
        }

        # Add other users as viewers (owner is implicit, don't include in albumUsers)
        if share_user_ids:
            album_users = []
            for user_id in share_user_ids:
                # Skip owner (they're automatically the owner, can't be in albumUsers)
                if user_id != me["id"]:
                    album_users.append({"userId": user_id, "role": "viewer"})

            # Only add albumUsers if there are other users to share with
            if album_users:
                payload["albumUsers"] = album_users

        if description:
            payload["description"] = description

        if asset_ids:
            payload["assetIds"] = asset_ids

        # Log album creation
        if share_user_ids:
            other_users_count = len([uid for uid in share_user_ids if uid != me["id"]])
            if other_users_count > 0:
                logger.info(f"Creating album '{album_name}' shared with {other_users_count} user(s)")
            else:
                logger.info(f"Creating album: {album_name}")
        else:
            logger.info(f"Creating album: {album_name}")

        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    def update_album_sharing(self, album_id: str, share_user_ids: List[str]) -> Optional[Dict]:
        """
        Update sharing settings for an existing album.

        Args:
            album_id: ID of the album to update
            share_user_ids: List of user IDs to share album with (as viewers)

        Returns:
            Updated album dict if successful, None if failed
        """
        me = self.get_my_user()
        url = f"{self.base_url}/albums/{album_id}"

        # Build albumUsers array (exclude owner)
        album_users = [
            {"userId": uid, "role": "viewer"}
            for uid in share_user_ids
            if uid != me["id"]
        ]

        payload = {"albumUsers": album_users}
        logger.debug(f"Updating album {album_id} sharing: {len(album_users)} user(s)")

        # Try PATCH first (partial update)
        try:
            response = self.session.patch(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Fallback to PUT if PATCH not supported
            if e.response.status_code == 405:
                logger.debug("PATCH not supported, trying PUT")
                try:
                    response = self.session.put(url, json=payload)
                    response.raise_for_status()
                    return response.json()
                except requests.exceptions.HTTPError as put_error:
                    logger.warning(f"Failed to update album sharing with PUT: {put_error}")
                    return None
            else:
                logger.warning(f"Failed to update album sharing: {e}")
                return None

    def has_sharing_changed(self, album: Dict, desired_user_ids: List[str]) -> bool:
        """
        Check if album sharing differs from desired state.

        Args:
            album: Album dict containing current albumUsers
            desired_user_ids: List of user IDs that should have access

        Returns:
            True if sharing needs to be updated, False otherwise
        """
        # Extract current viewer user IDs (exclude owner/editor roles)
        # Note: API returns albumUsers with nested user object: {"user": {"id": "..."}, "role": "..."}
        current_user_ids = {
            user["user"]["id"]
            for user in album.get("albumUsers", [])
            if user.get("role") == "viewer"
        }

        # Compare with desired state
        return current_user_ids != set(desired_user_ids)

    def add_assets_to_album(self, album_id: str, asset_ids: Set[str], chunk_size: int = 500) -> None:
        """
        Add assets to an album.

        Args:
            album_id: ID of the album
            asset_ids: Set of asset IDs to add
            chunk_size: Number of assets to add per request
        """
        if not asset_ids:
            logger.debug(f"No assets to add to album {album_id}")
            return

        url = f"{self.base_url}/albums/{album_id}/assets"
        asset_list = list(asset_ids)

        # Process in chunks
        for i in range(0, len(asset_list), chunk_size):
            chunk = asset_list[i:i + chunk_size]
            payload = {"ids": chunk}

            logger.info(f"Adding {len(chunk)} assets to album {album_id}")
            response = self.session.put(url, json=payload)
            response.raise_for_status()

            time.sleep(0.1)  # Be nice to the API

    def remove_assets_from_album(self, album_id: str, asset_ids: Set[str], chunk_size: int = 500) -> None:
        """
        Remove assets from an album.

        Args:
            album_id: ID of the album
            asset_ids: Set of asset IDs to remove
            chunk_size: Number of assets to remove per request
        """
        if not asset_ids:
            logger.debug(f"No assets to remove from album {album_id}")
            return

        url = f"{self.base_url}/albums/{album_id}/assets"
        asset_list = list(asset_ids)

        # Process in chunks
        for i in range(0, len(asset_list), chunk_size):
            chunk = asset_list[i:i + chunk_size]
            payload = {"ids": chunk}

            logger.info(f"Removing {len(chunk)} assets from album {album_id}")
            response = self.session.delete(url, json=payload)
            response.raise_for_status()

            time.sleep(0.1)  # Be nice to the API

    def get_album_assets(self, album_id: str) -> Set[str]:
        """
        Get all asset IDs in an album.

        Args:
            album_id: ID of the album

        Returns:
            Set of asset IDs in the album
        """
        # Note: The API endpoint to get album details with assets
        # This might need adjustment based on actual API response structure
        url = f"{self.base_url}/albums/{album_id}"
        response = self.session.get(url)
        response.raise_for_status()
        album_data = response.json()

        asset_ids = set()
        for asset in album_data.get("assets", []):
            asset_ids.add(asset["id"])

        return asset_ids
