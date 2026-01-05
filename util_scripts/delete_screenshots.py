#!/usr/bin/env python3
"""
One-off script to delete all screenshots from the "Screenshots for Review" album.
This will PERMANENTLY DELETE the image files from Immich.
"""

import logging
import os
import sys
from typing import Set
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


ALBUM_NAME = "Screenshots for Review"


def delete_assets(client: ImmichClient, asset_ids: Set[str], batch_size: int = 100) -> None:
    """
    Delete assets from Immich permanently.

    Args:
        client: ImmichClient instance
        asset_ids: Set of asset IDs to delete
        batch_size: Number of assets to delete per request
    """
    if not asset_ids:
        logger.warning("No assets to delete.")
        return

    url = f"{client.base_url}/assets"
    asset_list = list(asset_ids)
    total = len(asset_list)
    deleted = 0

    logger.info(f"Deleting {total} assets in batches of {batch_size}...")

    # Process in batches
    for i in range(0, total, batch_size):
        chunk = asset_list[i:i + batch_size]
        payload = {"ids": chunk}

        try:
            logger.info(f"Deleting batch {(i // batch_size) + 1}: assets {i + 1}-{min(i + batch_size, total)} of {total}")
            response = client.session.delete(url, json=payload)
            response.raise_for_status()
            deleted += len(chunk)
            logger.info(f"Successfully deleted {deleted}/{total} assets")
        except Exception as e:
            logger.error(f"Failed to delete batch: {e}")
            logger.error(f"Response: {response.text if 'response' in locals() else 'No response'}")
            raise


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
    logger.info("Screenshot Deletion Script - PERMANENT DELETION")
    logger.info("=" * 60)
    logger.info(f"Album: {ALBUM_NAME}")
    logger.info("=" * 60)

    # Initialize client
    client = ImmichClient(base_url, api_key)

    try:
        # Find the album
        logger.info(f"Looking for album '{ALBUM_NAME}'...")
        album = client.find_album_by_name(ALBUM_NAME)

        if not album:
            logger.error(f"Album '{ALBUM_NAME}' not found!")
            sys.exit(1)

        album_id = album["id"]
        logger.info(f"Found album (ID: {album_id})")

        # Get all assets in the album
        logger.info("Fetching all assets in the album...")
        asset_ids = client.get_album_assets(album_id)

        if not asset_ids:
            logger.info("Album is empty. Nothing to delete.")
            sys.exit(0)

        logger.info(f"Found {len(asset_ids)} screenshots in the album")

        # Confirm deletion
        logger.warning("=" * 60)
        logger.warning("WARNING: This will PERMANENTLY DELETE these images!")
        logger.warning(f"Total images to delete: {len(asset_ids)}")
        logger.warning("=" * 60)

        response = input("Are you sure you want to delete ALL these screenshots? (yes/no): ")

        if response.lower() != "yes":
            logger.info("Deletion cancelled by user.")
            sys.exit(0)

        # Double confirmation
        response = input("This cannot be undone. Type 'DELETE' to confirm: ")

        if response != "DELETE":
            logger.info("Deletion cancelled by user.")
            sys.exit(0)

        # Delete the assets
        delete_assets(client, asset_ids)

        logger.info("=" * 60)
        logger.info("Script completed successfully!")
        logger.info(f"Deleted {len(asset_ids)} screenshots from Immich.")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Script failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
