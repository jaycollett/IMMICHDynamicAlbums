#!/usr/bin/env python3
"""
One-off script to find screenshots by resolution and create an album.
This script searches for images with specific resolutions (1320x2868 or 1080x2400)
and adds them to a "Screenshots for Review" album.
"""

import logging
import os
import sys
from typing import Set, Tuple
from dotenv import load_dotenv

# Add src to path so we can import the client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from immich_client import ImmichClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Screenshot resolutions to search for
TARGET_RESOLUTIONS = [
    (1320, 2868),  # New phone
    (1080, 2400),  # Old phone
]

ALBUM_NAME = "Screenshots for Review"
ALBUM_DESCRIPTION = "Screenshots detected by resolution (1320x2868 or 1080x2400)"


def get_asset_resolution(client: ImmichClient, asset_id: str) -> Tuple[int, int]:
    """
    Get the resolution (width, height) of an asset.

    Args:
        client: ImmichClient instance
        asset_id: Asset ID to fetch

    Returns:
        Tuple of (width, height) or (0, 0) if not available
    """
    try:
        metadata = client.get_asset_metadata(asset_id)
        exif = metadata.get("exifInfo", {})

        # Try to get dimensions from exif
        width = exif.get("exifImageWidth", 0)
        height = exif.get("exifImageHeight", 0)

        # Some assets might have dimensions in different fields
        if width == 0 or height == 0:
            width = metadata.get("originalWidth", 0)
            height = metadata.get("originalHeight", 0)

        return (width, height)
    except Exception as e:
        logger.warning(f"Failed to get metadata for asset {asset_id}: {e}")
        return (0, 0)


def find_screenshots(client: ImmichClient, batch_size: int = 100) -> Set[str]:
    """
    Find all image assets matching screenshot resolutions.

    Args:
        client: ImmichClient instance
        batch_size: Number of assets to check before logging progress

    Returns:
        Set of asset IDs matching target resolutions
    """
    logger.info("Searching for all image assets...")

    # Get all image assets (no date filters)
    all_assets = client.search_assets(
        asset_types=["IMAGE"],
        default_to_image=True
    )

    total_assets = len(all_assets)
    logger.info(f"Found {total_assets} total image assets. Checking resolutions...")

    matching_assets = set()
    checked_count = 0

    for asset_id in all_assets:
        checked_count += 1

        # Log progress every batch_size assets
        if checked_count % batch_size == 0:
            logger.info(f"Progress: {checked_count}/{total_assets} assets checked, {len(matching_assets)} matches found")

        width, height = get_asset_resolution(client, asset_id)

        # Check if resolution matches any target
        if (width, height) in TARGET_RESOLUTIONS:
            logger.info(f"Found screenshot: {asset_id} ({width}x{height})")
            matching_assets.add(asset_id)

    logger.info(f"Finished checking all assets. Found {len(matching_assets)} screenshots.")
    return matching_assets


def create_screenshot_album(client: ImmichClient, asset_ids: Set[str]) -> None:
    """
    Create or update the screenshot review album with matching assets.

    Args:
        client: ImmichClient instance
        asset_ids: Set of asset IDs to add to album
    """
    if not asset_ids:
        logger.warning("No screenshots found. No album will be created.")
        return

    # Check if album already exists
    existing_album = client.find_album_by_name(ALBUM_NAME)

    if existing_album:
        album_id = existing_album["id"]
        logger.info(f"Album '{ALBUM_NAME}' already exists (ID: {album_id})")

        # Get current assets in album
        current_assets = client.get_album_assets(album_id)

        # Calculate what needs to be added
        assets_to_add = asset_ids - current_assets

        if assets_to_add:
            logger.info(f"Adding {len(assets_to_add)} new screenshots to existing album...")
            client.add_assets_to_album(album_id, assets_to_add)
            logger.info(f"Successfully added {len(assets_to_add)} screenshots.")
        else:
            logger.info("All screenshots are already in the album. Nothing to add.")

        logger.info(f"Album now contains {len(current_assets | asset_ids)} total screenshots.")
    else:
        # Create new album
        logger.info(f"Creating new album '{ALBUM_NAME}' with {len(asset_ids)} screenshots...")
        album = client.create_album(
            album_name=ALBUM_NAME,
            description=ALBUM_DESCRIPTION,
            asset_ids=list(asset_ids)
        )
        logger.info(f"Successfully created album (ID: {album['id']}) with {len(asset_ids)} screenshots.")


def main():
    """Main entry point for the script."""
    # Load environment variables
    load_dotenv()

    api_key = os.getenv("IMMICH_API_KEY")
    base_url = os.getenv("IMMICH_BASE_URL")

    if not api_key or not base_url:
        logger.error("IMMICH_API_KEY and IMMICH_BASE_URL must be set in .env file")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Screenshot Finder - One-off Script")
    logger.info("=" * 60)
    logger.info(f"Target resolutions: {', '.join([f'{w}x{h}' for w, h in TARGET_RESOLUTIONS])}")
    logger.info(f"Album name: {ALBUM_NAME}")
    logger.info("=" * 60)

    # Initialize client
    client = ImmichClient(base_url, api_key)

    try:
        # Find screenshots
        screenshot_ids = find_screenshots(client)

        # Create album
        create_screenshot_album(client, screenshot_ids)

        logger.info("=" * 60)
        logger.info("Script completed successfully!")
        logger.info(f"You can now review and remove screenshots from the '{ALBUM_NAME}' album.")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Script failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
