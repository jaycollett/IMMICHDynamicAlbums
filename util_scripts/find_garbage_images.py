#!/usr/bin/env python3
"""
Find potential "garbage" images using image quality analysis.

This script analyzes images in your Immich library to identify potential accidental
captures (blurry, dark, low contrast, etc.) and creates an album for review.

Usage:
    # Dry-run mode (analyze only, don't create album)
    python find_garbage_images.py --dry-run

    # Create album with flagged images
    python find_garbage_images.py --create-album "Review: Potential Garbage Images"

    # Custom thresholds
    python find_garbage_images.py --blur-threshold 50 --darkness-threshold 20

    # Limit number of images to analyze (for testing)
    python find_garbage_images.py --limit 100 --dry-run

    # Use 8 parallel workers for faster processing
    python find_garbage_images.py --workers 8 --dry-run

Requirements:
    pip install pillow opencv-python-headless requests python-dotenv
"""

import argparse
import io
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from PIL import Image

try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("Warning: opencv-python not available. Blur detection will be disabled.")
    print("Install with: pip install opencv-python-headless")

# Add src directory to path (go up one level from util_scripts, then to src)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, os.path.join(project_root, 'src'))
from immich_client import ImmichClient


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GarbageImageDetector:
    """Detect potentially garbage images using various quality metrics."""

    def __init__(
        self,
        client: ImmichClient,
        blur_threshold: float = 100.0,
        darkness_threshold: int = 30,
        contrast_threshold: int = 20,
        min_resolution: Optional[int] = None,
        min_issues: int = 1,
    ):
        """
        Initialize the garbage image detector.

        Args:
            client: Immich API client
            blur_threshold: Laplacian variance threshold (lower = more blurry)
                           Typical values: <50 very blurry, 50-100 blurry, >100 sharp
            darkness_threshold: Average brightness threshold (0-255, lower = darker)
                               Typical values: <20 very dark, 20-40 dark, >40 normal
            contrast_threshold: Standard deviation threshold (lower = less contrast)
                               Typical values: <15 very low, 15-30 low, >30 normal
            min_resolution: Minimum pixel count (width * height), None to disable
            min_issues: Minimum number of issues required to flag an image (default: 1)
                       Set to 2 to only flag images with multiple problems
        """
        self.client = client
        self.blur_threshold = blur_threshold
        self.darkness_threshold = darkness_threshold
        self.contrast_threshold = contrast_threshold
        self.min_resolution = min_resolution
        self.min_issues = min_issues

    def download_image_thumbnail(self, asset_id: str, session: requests.Session) -> Optional[Image.Image]:
        """
        Download a thumbnail of the image for analysis.

        Args:
            asset_id: ID of the asset to download
            session: Requests session to use for download

        Returns:
            PIL Image object or None if failed
        """
        # Use thumbnail endpoint for faster downloads
        # Format: preview is lower quality but faster, thumbnail is smaller
        url = f"{self.client.base_url}/assets/{asset_id}/thumbnail"

        try:
            response = session.get(url, params={"size": "preview"})
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            return image
        except Exception as e:
            logger.warning(f"Failed to download image {asset_id}: {e}")
            return None

    def calculate_blur(self, image: Image.Image) -> Optional[float]:
        """
        Calculate blur score using Laplacian variance.
        Lower values indicate more blur.

        Args:
            image: PIL Image object

        Returns:
            Blur score (variance) or None if OpenCV not available
        """
        if not OPENCV_AVAILABLE:
            return None

        # Convert PIL to OpenCV format
        img_array = np.array(image.convert('RGB'))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # Calculate Laplacian variance
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()

        return variance

    def calculate_brightness(self, image: Image.Image) -> float:
        """
        Calculate average brightness of the image.

        Args:
            image: PIL Image object

        Returns:
            Average brightness (0-255)
        """
        # Convert to grayscale and calculate mean
        grayscale = image.convert('L')
        pixels = list(grayscale.get_flattened_data())
        return sum(pixels) / len(pixels)

    def calculate_contrast(self, image: Image.Image) -> float:
        """
        Calculate contrast (standard deviation of pixel values).

        Args:
            image: PIL Image object

        Returns:
            Standard deviation of brightness
        """
        grayscale = image.convert('L')
        pixels = list(grayscale.get_flattened_data())

        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        std_dev = variance ** 0.5

        return std_dev

    def analyze_image(self, asset_id: str, asset_info: Dict, session: requests.Session) -> Optional[Dict]:
        """
        Analyze an image for garbage characteristics.

        Args:
            asset_id: ID of the asset
            asset_info: Asset metadata dict
            session: Requests session to use for download

        Returns:
            Dict with analysis results, or None if not flagged
        """
        image = self.download_image_thumbnail(asset_id, session)
        if not image:
            return None

        # Calculate metrics
        blur_score = self.calculate_blur(image) if OPENCV_AVAILABLE else None
        brightness = self.calculate_brightness(image)
        contrast = self.calculate_contrast(image)
        width, height = image.size
        resolution = width * height

        # Determine if image should be flagged
        reasons = []

        if blur_score is not None and blur_score < self.blur_threshold:
            reasons.append(f"blurry (score: {blur_score:.1f})")

        if brightness < self.darkness_threshold:
            reasons.append(f"dark (brightness: {brightness:.1f})")

        if contrast < self.contrast_threshold:
            reasons.append(f"low contrast (std: {contrast:.1f})")

        if self.min_resolution and resolution < self.min_resolution:
            reasons.append(f"low resolution ({width}x{height})")

        # Only flag if we have at least min_issues problems
        if len(reasons) < self.min_issues:
            return None

        return {
            "asset_id": asset_id,
            "reasons": reasons,
            "metrics": {
                "blur_score": blur_score,
                "brightness": brightness,
                "contrast": contrast,
                "resolution": f"{width}x{height}",
            },
            "original_name": asset_info.get("originalFileName", "unknown"),
            "taken_date": asset_info.get("fileCreatedAt", "unknown"),
        }

    def _process_single_asset(self, asset_id: str) -> Optional[Dict]:
        """
        Worker function to process a single asset (fetch metadata + analyze).
        This function is thread-safe as it creates its own session.

        Args:
            asset_id: ID of the asset to process

        Returns:
            Dict with analysis results, or None if not flagged or error occurred
        """
        # Create thread-local session with larger connection pool for thread safety
        session = requests.Session()
        # Configure HTTPAdapter with larger pool to handle concurrent requests
        adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update(self.client.headers)

        try:
            # Get asset metadata
            asset_info = self.client.get_asset_metadata(asset_id)

            # Analyze image
            result = self.analyze_image(asset_id, asset_info, session)
            if result:
                logger.debug(f"Flagged {asset_id}: {', '.join(result['reasons'])}")
            return result

        except Exception as e:
            logger.warning(f"Failed to process asset {asset_id}: {e}")
            return None
        finally:
            session.close()

    def find_garbage_images(
        self,
        limit: Optional[int] = None,
        workers: Optional[int] = None,
    ) -> List[Dict]:
        """
        Find all potential garbage images using parallel processing.

        Args:
            limit: Maximum number of images to analyze (for testing)
            workers: Number of parallel workers (default: cpu_count)

        Returns:
            List of flagged image analysis results
        """
        logger.info("Fetching all IMAGE assets from Immich...")

        # Get all image assets
        asset_ids = self.client.search_assets(
            asset_types=["IMAGE"],
            default_to_image=True,
        )

        total_assets = len(asset_ids)
        logger.info(f"Found {total_assets} total images to analyze")

        if limit:
            asset_ids = list(asset_ids)[:limit]
            logger.info(f"Limiting analysis to first {len(asset_ids)} images")

        # Determine number of workers
        if workers is None:
            workers = os.cpu_count() or 4
        logger.info(f"Using {workers} parallel workers")

        # Process images in parallel
        flagged_images = []
        processed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_asset_id = {
                executor.submit(self._process_single_asset, asset_id): asset_id
                for asset_id in asset_ids
            }

            # Process completed tasks
            for future in as_completed(future_to_asset_id):
                processed += 1

                if processed % 100 == 0:
                    logger.info(
                        f"Progress: {processed}/{len(asset_ids)} images analyzed, "
                        f"{len(flagged_images)} flagged"
                    )

                # Get result from completed task
                result = future.result()
                if result:
                    flagged_images.append(result)

        logger.info(f"Analysis complete: {len(flagged_images)}/{processed} images flagged as potential garbage")
        return flagged_images

    def create_review_album(
        self,
        flagged_images: List[Dict],
        album_name: str,
    ) -> Optional[str]:
        """
        Create an album with flagged images for review.

        Args:
            flagged_images: List of flagged image analysis results
            album_name: Name for the review album

        Returns:
            Album ID if created, None otherwise
        """
        if not flagged_images:
            logger.info("No images to add to album")
            return None

        asset_ids = [img["asset_id"] for img in flagged_images]

        # Check if album already exists
        existing_album = self.client.find_album_by_name(album_name)
        if existing_album:
            logger.warning(f"Album '{album_name}' already exists (ID: {existing_album['id']})")
            logger.info("Adding flagged images to existing album...")
            album_id = existing_album['id']
            self.client.add_assets_to_album(album_id, set(asset_ids))
        else:
            # Create new album
            description = (
                f"Automatically generated album containing {len(flagged_images)} "
                f"images flagged as potential garbage (blurry, dark, low contrast). "
                f"Review and delete unwanted images."
            )

            logger.info(f"Creating album '{album_name}' with {len(asset_ids)} images...")
            album = self.client.create_album(
                album_name=album_name,
                description=description,
                asset_ids=asset_ids,
            )
            album_id = album['id']

        logger.info(f"Album created/updated: {album_name} (ID: {album_id})")
        return album_id


def main():
    parser = argparse.ArgumentParser(
        description="Find potential garbage images in Immich library",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run mode (analyze only)
  python find_garbage_images.py --dry-run

  # Create album with default name
  python find_garbage_images.py

  # Custom album name
  python find_garbage_images.py --create-album "My Review Album"

  # Adjust thresholds (more aggressive detection)
  python find_garbage_images.py --blur-threshold 150 --darkness-threshold 40

  # Test on small subset
  python find_garbage_images.py --limit 50 --dry-run

Thresholds Guide:
  Blur Score (Laplacian variance):
    < 50    = Very blurry (likely garbage)
    50-100  = Somewhat blurry
    100-200 = Slight blur
    > 200   = Sharp

  Brightness (0-255):
    < 20    = Very dark (likely pocket shot)
    20-40   = Dark
    40-80   = Dim
    > 80    = Normal lighting

  Contrast (std deviation):
    < 15    = Very low (likely blank/uniform)
    15-30   = Low contrast
    30-50   = Normal
    > 50    = High contrast
        """
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze images but don't create album"
    )

    parser.add_argument(
        "--create-album",
        type=str,
        metavar="NAME",
        help="Create album with specified name (default: 'Review: Potential Garbage Images')"
    )

    parser.add_argument(
        "--blur-threshold",
        type=float,
        default=100.0,
        help="Blur detection threshold (default: 100.0, lower = more blurry)"
    )

    parser.add_argument(
        "--darkness-threshold",
        type=int,
        default=30,
        help="Darkness threshold 0-255 (default: 30, lower = darker)"
    )

    parser.add_argument(
        "--contrast-threshold",
        type=int,
        default=20,
        help="Contrast threshold (default: 20, lower = less contrast)"
    )

    parser.add_argument(
        "--min-resolution",
        type=int,
        metavar="PIXELS",
        help="Minimum resolution in pixels (e.g., 307200 for 640x480)"
    )

    parser.add_argument(
        "--min-issues",
        type=int,
        default=1,
        metavar="N",
        help="Minimum number of issues required to flag an image (default: 1). "
             "Set to 2 to only flag images with multiple problems (e.g., blurry AND dark)"
    )

    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Limit analysis to first N images (for testing)"
    )

    parser.add_argument(
        "--workers",
        type=int,
        metavar="N",
        help=f"Number of parallel workers (default: {os.cpu_count() or 4})"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Get Immich credentials from environment
    api_key = os.getenv("IMMICH_API_KEY")
    base_url = os.getenv("IMMICH_BASE_URL")

    if not api_key or not base_url:
        logger.error("Missing IMMICH_API_KEY or IMMICH_BASE_URL environment variables")
        logger.error("Set them in .env file or export them in your shell")
        sys.exit(1)

    # Initialize client and detector
    client = ImmichClient(base_url, api_key)
    detector = GarbageImageDetector(
        client=client,
        blur_threshold=args.blur_threshold,
        darkness_threshold=args.darkness_threshold,
        contrast_threshold=args.contrast_threshold,
        min_resolution=args.min_resolution,
        min_issues=args.min_issues,
    )

    # Print detection configuration
    logger.info("=" * 60)
    logger.info("Garbage Image Detection Configuration")
    logger.info("=" * 60)
    logger.info(f"Blur threshold: {args.blur_threshold} (lower = more blurry)")
    logger.info(f"Darkness threshold: {args.darkness_threshold} (0-255, lower = darker)")
    logger.info(f"Contrast threshold: {args.contrast_threshold} (lower = less contrast)")
    logger.info(f"Min issues to flag: {args.min_issues} (1=any issue, 2=multiple issues required)")
    if args.min_resolution:
        logger.info(f"Min resolution: {args.min_resolution} pixels")
    if args.limit:
        logger.info(f"Analysis limit: {args.limit} images")
    if args.workers:
        logger.info(f"Parallel workers: {args.workers}")
    logger.info("=" * 60)

    # Find garbage images
    flagged_images = detector.find_garbage_images(limit=args.limit, workers=args.workers)

    # Print results
    logger.info("\n" + "=" * 60)
    logger.info("ANALYSIS RESULTS")
    logger.info("=" * 60)

    if not flagged_images:
        logger.info("No garbage images found!")
        return

    logger.info(f"Found {len(flagged_images)} potential garbage images:\n")

    for i, img in enumerate(flagged_images[:20], 1):  # Show first 20
        logger.info(f"{i}. {img['original_name']}")
        logger.info(f"   Asset ID: {img['asset_id']}")
        logger.info(f"   Reasons: {', '.join(img['reasons'])}")
        logger.info(f"   Metrics: blur={img['metrics']['blur_score']}, "
                   f"brightness={img['metrics']['brightness']:.1f}, "
                   f"contrast={img['metrics']['contrast']:.1f}, "
                   f"resolution={img['metrics']['resolution']}")
        logger.info("")

    if len(flagged_images) > 20:
        logger.info(f"... and {len(flagged_images) - 20} more")

    # Create album if requested
    if not args.dry_run:
        album_name = args.create_album or "Review: Potential Garbage Images"
        detector.create_review_album(flagged_images, album_name)
        logger.info("\nDone! Check your Immich library for the review album.")
    else:
        logger.info("\nDry-run mode: No album created.")
        logger.info("Run without --dry-run to create an album with these images.")


if __name__ == "__main__":
    main()
