# Garbage Image Detection Utility

A one-off utility script to identify and flag potentially unwanted "garbage" images in your Immich library using computer vision techniques.

## What It Does

Analyzes images to identify:
- **Blurry photos** - Out-of-focus images from accidental captures
- **Dark images** - Very dark photos (likely pocket shots or lens cap on)
- **Low contrast images** - Blank or uniform content
- **Low resolution images** - Optional check for images below a size threshold

Creates an Immich album with flagged images for easy manual review and deletion.

## Installation

### 1. Install Optional Dependencies

From the project root:

```bash
pip install -r requirements-optional.txt
```

Or manually:
```bash
pip install pillow opencv-python-headless python-dotenv
```

**Note:** If `opencv-python-headless` fails to install, the script will still work but blur detection will be disabled.

### 2. Environment Setup

Make sure your `.env` file is configured with Immich credentials:

```bash
IMMICH_API_KEY=your-api-key-here
IMMICH_BASE_URL=https://your-immich-instance.com/api
```

## Usage

### Basic Usage

**Dry-run mode** (recommended first):
```bash
python util_scripts/find_garbage_images.py --dry-run
```

This analyzes all images and shows what would be flagged without creating an album.

**Create album with default settings:**
```bash
python util_scripts/find_garbage_images.py
```

Creates an album named "Review: Potential Garbage Images" with all flagged images.

### Custom Album Name

```bash
python util_scripts/find_garbage_images.py --create-album "To Delete"
```

### Testing on a Small Subset

```bash
# Analyze only first 100 images
python util_scripts/find_garbage_images.py --limit 100 --dry-run
```

### Adjusting Detection Sensitivity

**More aggressive** (flags more images):
```bash
python util_scripts/find_garbage_images.py --blur-threshold 150 --darkness-threshold 40
```

**More conservative** (only obvious garbage):
```bash
python util_scripts/find_garbage_images.py --blur-threshold 50 --darkness-threshold 20
```

**Include resolution check:**
```bash
# Flag images smaller than 640x480 (307,200 pixels)
python util_scripts/find_garbage_images.py --min-resolution 307200
```

### Enable Verbose Logging

```bash
python util_scripts/find_garbage_images.py --verbose --dry-run
```

## Understanding Thresholds

### Blur Score (Laplacian Variance)

The script calculates blur using OpenCV's Laplacian operator. **Lower values = more blur**.

| Range | Description | Recommendation |
|-------|-------------|----------------|
| < 50 | Very blurry | Likely garbage |
| 50-100 | Somewhat blurry | Potential garbage (default threshold) |
| 100-200 | Slight blur | Usually acceptable |
| > 200 | Sharp | Good quality |

**Default threshold:** `100.0`

### Brightness (0-255)

Average pixel brightness. **Lower values = darker images**.

| Range | Description | Recommendation |
|-------|-------------|----------------|
| < 20 | Very dark | Likely pocket shot |
| 20-40 | Dark | Potential garbage (default threshold: 30) |
| 40-80 | Dim | May be intentional low-light |
| > 80 | Normal | Good lighting |

**Default threshold:** `30`

### Contrast (Standard Deviation)

Measures variation in pixel values. **Lower values = less detail**.

| Range | Description | Recommendation |
|-------|-------------|----------------|
| < 15 | Very low | Likely blank/uniform |
| 15-30 | Low contrast | Potential garbage (default threshold: 20) |
| 30-50 | Normal | Typical photos |
| > 50 | High contrast | Good detail |

**Default threshold:** `20`

### Resolution

Minimum pixel count (width × height). Useful for flagging low-resolution images.

**Example values:**
- `307200` = 640×480 (VGA)
- `786432` = 1024×768 (XGA)
- `2073600` = 1920×1080 (Full HD)

**Default:** Disabled (no resolution check)

## All Command-Line Options

```bash
python util_scripts/find_garbage_images.py [OPTIONS]

Options:
  --dry-run                    Analyze only, don't create album
  --create-album NAME          Custom album name (default: "Review: Potential Garbage Images")
  --blur-threshold N           Blur detection threshold (default: 100.0, float)
  --darkness-threshold N       Darkness threshold 0-255 (default: 30, int)
  --contrast-threshold N       Contrast threshold (default: 20, int)
  --min-resolution PIXELS      Minimum resolution in pixels (disabled by default)
  --limit N                    Analyze only first N images (for testing)
  --verbose                    Enable debug logging
  --help                       Show help message
```

## How It Works

1. **Fetch Assets**: Retrieves all IMAGE-type assets from Immich
2. **Download Thumbnails**: Uses Immich preview endpoint (fast, efficient)
3. **Analyze Each Image**:
   - Calculate blur score using Laplacian variance (OpenCV)
   - Calculate average brightness (PIL)
   - Calculate contrast using standard deviation (PIL)
   - Check resolution if threshold specified
4. **Flag Images**: Images failing any threshold are flagged
5. **Create Album**: Flagged images added to Immich album for review
6. **Manual Review**: Browse album in Immich and delete unwanted images

## Example Output

```
============================================================
Garbage Image Detection Configuration
============================================================
Blur threshold: 100.0 (lower = more blurry)
Darkness threshold: 30 (0-255, lower = darker)
Contrast threshold: 20 (lower = less contrast)
Analysis limit: 10 images
============================================================
Fetching all IMAGE assets from Immich...
Found 65108 assets (IMAGE) matching criteria
Found 65108 total images to analyze
Limiting analysis to first 10 images
Analysis complete: 5/10 images flagged as potential garbage

============================================================
ANALYSIS RESULTS
============================================================
Found 5 potential garbage images:

1. IMG_20151017_102447161.jpg
   Asset ID: 3df0c808-de68-4233-aaf2-b1e9f7034261
   Reasons: blurry (score: 74.0)
   Metrics: blur=73.98, brightness=141.9, contrast=46.2, resolution=1920x1440

2. JCA_8639.dng
   Asset ID: 68d0c312-2414-4849-8579-55476c55f76c
   Reasons: blurry (score: 12.5), dark (brightness: 28.6)
   Metrics: blur=12.49, brightness=28.6, contrast=46.7, resolution=2172x1440

...
```

## Tips & Best Practices

### Start Conservative

Begin with default thresholds or more conservative settings:
```bash
python util_scripts/find_garbage_images.py --limit 100 --dry-run
```

Review the flagged images in the output. If too many false positives, increase thresholds. If missing obvious garbage, decrease thresholds.

### Test on Subsets

Use `--limit` to test on small batches:
```bash
python util_scripts/find_garbage_images.py --limit 500 --dry-run
```

### Multiple Passes

You can run the script multiple times with different thresholds. The album will be updated with new flagged images:

```bash
# First pass - very conservative (only obvious garbage)
python util_scripts/find_garbage_images.py --blur-threshold 50 --darkness-threshold 15

# Second pass - more aggressive (if first pass worked well)
python util_scripts/find_garbage_images.py --blur-threshold 100 --darkness-threshold 30
```

### Performance Considerations

For very large libraries (100k+ images):
- Use `--limit` to process in batches
- The script uses thumbnail previews (fast)
- Expect ~100-200 images per minute depending on network speed

### Manual Review

**Always manually review** flagged images before deletion. The script may flag:
- Intentional artistic blur
- Legitimate low-light photography
- Black and white photos (may trigger low contrast)
- Intentional low-resolution images

## Troubleshooting

### OpenCV Not Available

```
Warning: opencv-python not available. Blur detection will be disabled.
Install with: pip install opencv-python-headless
```

**Solution:** Install opencv-python-headless. The script will still work but won't detect blur.

### API Connection Issues

```
Failed to download image {asset_id}: ...
```

**Check:**
- `IMMICH_BASE_URL` is correct and ends with `/api`
- `IMMICH_API_KEY` has `asset.read` permission
- Network connectivity to Immich instance

### No Images Flagged

If the script finds no garbage images:
- Your library may genuinely have good quality photos
- Try more aggressive thresholds (higher blur, higher darkness)
- Use `--verbose` to see detailed metrics for all images

### Too Many False Positives

If legitimate photos are being flagged:
- Increase thresholds (more conservative)
- Review the metrics in output to see which threshold is triggering
- Adjust only the problematic threshold

## Integration with Main Application

This is a **standalone utility** - it does not integrate with the main dynamic albums application. It's designed to be run occasionally when you want to clean up your library.

**Workflow:**
1. Run garbage detection script
2. Review flagged images in Immich album
3. Delete unwanted images from Immich
4. Optional: Re-run main dynamic albums sync to update albums

## License

Same as main project: Apache License 2.0
