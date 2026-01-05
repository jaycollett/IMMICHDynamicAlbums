# Filter Reference Guide

Quick reference for all available filters in Immich Dynamic Albums.

## Filter Structure

Filters are defined in the `filters` section of a rule:

```yaml
rules:
  - id: "rule-id"
    album_name: "Album Name"
    taken_range_utc:
      start: "2025-01-01T00:00:00.000Z"
      end: "2025-12-31T23:59:59.999Z"
    filters:
      # All filters are optional
      is_favorite: true
      asset_types: [IMAGE, VIDEO]
      camera:
        make: "Apple"
        model: "iPhone 15 Pro"
      tags:
        include: ["family"]
        exclude: ["screenshot"]
```

## Filter Types

### Date Range Filters (Top Level)

Located at the rule level, not in the `filters` section.

#### `taken_range_utc`
Filter by the date/time the photo was taken (from EXIF data).

```yaml
taken_range_utc:
  start: "2025-01-01T00:00:00.000Z"  # Optional
  end: "2025-12-31T23:59:59.999Z"    # Optional
```

**Notes**:
- Uses `takenDate` from EXIF metadata
- Timezone must be included (Z for UTC, or +/-HH:MM)
- Can specify just start, just end, or both
- ISO 8601 format required

#### `created_range_utc`
Filter by the date/time the asset was uploaded to Immich.

```yaml
created_range_utc:
  start: "2025-01-01T00:00:00.000Z"  # Optional
  end: "2025-12-31T23:59:59.999Z"    # Optional
```

**Notes**:
- Uses Immich's internal creation timestamp
- Useful for "recent uploads" albums
- Same format requirements as `taken_range_utc`

### Favorite Filter

#### `is_favorite`
Filter by favorite status.

```yaml
filters:
  is_favorite: true   # Only favorites
  # or
  is_favorite: false  # Only non-favorites
```

**Type**: Boolean (true/false)
**Default**: None (no filtering by favorite status)
**Use Cases**:
- Best of the year albums
- Curated collections
- Selected highlights

### Asset Type Filter

#### `asset_types`
Filter by asset type.

```yaml
filters:
  asset_types:
    - IMAGE
    - VIDEO
```

**Type**: List of strings
**Default**: `[IMAGE]` (for backward compatibility)
**Valid Values**:
- `IMAGE` - Photos
- `VIDEO` - Videos
- `AUDIO` - Audio files
- `OTHER` - Other file types

**Important**: Videos are excluded by default due to limited GPS and face detection support in Immich. Explicitly include `VIDEO` if you want them.

**Examples**:

Images only (default):
```yaml
filters:
  asset_types: [IMAGE]
```

Images and videos:
```yaml
filters:
  asset_types: [IMAGE, VIDEO]
```

Videos only:
```yaml
filters:
  asset_types: [VIDEO]
```

### Camera Filters

#### `camera.make`
Filter by camera manufacturer.

```yaml
filters:
  camera:
    make: "Apple"
```

**Type**: String (case-sensitive)
**Default**: None (no filtering)
**Common Values**:
- `"Apple"` - iPhones, iPads
- `"Canon"` - Canon cameras
- `"SONY"` - Sony cameras
- `"NIKON CORPORATION"` - Nikon cameras
- `"Samsung"` - Samsung phones
- `"Google"` - Pixel phones

**How to find your camera make**: Check the EXIF data of a photo from your device.

#### `camera.model`
Filter by specific camera model.

```yaml
filters:
  camera:
    model: "iPhone 15 Pro"
```

**Type**: String (case-sensitive)
**Default**: None (no filtering)
**Examples**:
- `"iPhone 15 Pro"`
- `"Canon EOS R5"`
- `"ILCE-7M3"` (Sony A7 III)
- `"NIKON D850"`

**Notes**:
- Can be used with or without `make`
- More specific than `make` alone
- Check your photo's EXIF data for exact model string

#### Combined Camera Filters

```yaml
filters:
  camera:
    make: "Canon"
    model: "Canon EOS R5"
```

**Behavior**: Assets must match both make AND model if both are specified.

### Tag Filters

#### `tags.include`
Include assets with at least one of these tags.

```yaml
filters:
  tags:
    include:
      - "family"
      - "vacation"
      - "landscape"
```

**Type**: List of strings
**Default**: Empty (no inclusion filtering)
**Behavior**: Asset must have **at least one** of the listed tags
**Note**: Tag filtering may be done client-side if API doesn't support it

#### `tags.exclude`
Exclude assets with any of these tags.

```yaml
filters:
  tags:
    exclude:
      - "screenshot"
      - "duplicate"
      - "test"
```

**Type**: List of strings
**Default**: Empty (no exclusion filtering)
**Behavior**: Asset must **not have any** of the listed tags

#### Combined Tag Filters

```yaml
filters:
  tags:
    include: ["family", "friends"]
    exclude: ["screenshot", "blurry"]
```

**Behavior**:
1. First, asset must have at least one tag from `include`
2. Then, asset must not have any tag from `exclude`

## Filter Combinations

Filters can be combined for precise asset selection. All specified filters must match (AND logic).

### Example 1: Favorite iPhone Photos

```yaml
filters:
  is_favorite: true
  camera:
    make: "Apple"
  asset_types: [IMAGE]
```

**Matches**: Assets that are favorites AND from Apple devices AND are images

### Example 2: Non-Screenshot Family Photos

```yaml
filters:
  camera:
    make: "Apple"
  tags:
    include: ["family"]
    exclude: ["screenshot"]
  asset_types: [IMAGE]
```

**Matches**: Assets from Apple devices AND tagged "family" AND not tagged "screenshot" AND are images

### Example 3: DSLR Photos from Vacation

```yaml
filters:
  camera:
    make: "Canon"
    model: "Canon EOS R5"
  tags:
    include: ["vacation", "travel"]
  asset_types: [IMAGE]
```

**Matches**: Assets from Canon EOS R5 AND tagged "vacation" or "travel" AND are images

### Example 4: Recent Video Uploads

```yaml
created_range_utc:
  start: "2025-01-01T00:00:00.000Z"
filters:
  asset_types: [VIDEO]
```

**Matches**: Assets created after Jan 1, 2025 AND are videos

## Default Behaviors

If a filter is not specified, it's not applied:

| Filter | If Not Specified |
|--------|------------------|
| `is_favorite` | Include both favorites and non-favorites |
| `asset_types` | Default to `[IMAGE]` only |
| `camera.make` | Include all camera makes |
| `camera.model` | Include all camera models |
| `tags.include` | Include all assets (no tag requirement) |
| `tags.exclude` | Exclude nothing |

## Performance Notes

### API-Side Filtering (Fast)
These filters are applied by the Immich API:
- Date ranges (`taken_range_utc`, `created_range_utc`)
- `is_favorite`
- `camera.make`
- `camera.model`
- `asset_types` (partially - type checking is client-side)

### Client-Side Filtering (Slower)
These filters may be applied client-side:
- `tags.include` (if API doesn't support it)
- `tags.exclude` (if API doesn't support it)
- Final `asset_types` verification

**Tip**: Use date ranges to limit the initial asset set, then apply other filters for best performance.

## Validation Rules

The configuration validator checks:

1. **Date Format**: Must be ISO 8601 with timezone
   - Valid: `2025-01-01T00:00:00.000Z`
   - Invalid: `2025-01-01`

2. **Date Logic**: Start date must be before end date
   - Valid: start=Jan 1, end=Dec 31
   - Invalid: start=Dec 31, end=Jan 1

3. **Asset Types**: Must be valid type
   - Valid: `IMAGE`, `VIDEO`, `AUDIO`, `OTHER`
   - Invalid: `PHOTO`, `MOVIE`, etc.

4. **Data Types**: Filters must be correct type
   - `is_favorite`: boolean (true/false)
   - `asset_types`: list of strings
   - `camera`: dictionary with string values
   - `tags`: dictionary with lists of strings

## Common Patterns

### Pattern: Time Periods

```yaml
# Year
taken_range_utc:
  start: "2025-01-01T00:00:00.000Z"
  end: "2025-12-31T23:59:59.999Z"

# Month
taken_range_utc:
  start: "2025-07-01T00:00:00.000Z"
  end: "2025-07-31T23:59:59.999Z"

# Week
taken_range_utc:
  start: "2025-07-14T00:00:00.000Z"
  end: "2025-07-21T00:00:00.000Z"

# Day
taken_range_utc:
  start: "2025-12-25T00:00:00.000Z"
  end: "2025-12-26T00:00:00.000Z"
```

### Pattern: Device-Specific Albums

```yaml
# iPhone album
filters:
  camera:
    make: "Apple"
  asset_types: [IMAGE]

# Android album
filters:
  camera:
    make: "Samsung"
  asset_types: [IMAGE]

# DSLR album
filters:
  camera:
    make: "Canon"
  asset_types: [IMAGE]
```

### Pattern: Content-Type Albums

```yaml
# Screenshots (to exclude elsewhere)
filters:
  tags:
    include: ["screenshot"]

# No screenshots
filters:
  tags:
    exclude: ["screenshot"]

# Professional photos
filters:
  camera:
    make: "Canon"
  is_favorite: true
  tags:
    exclude: ["test", "draft"]
```

### Pattern: Best-Of Albums

```yaml
# Best of year
filters:
  is_favorite: true
  tags:
    exclude: ["duplicate", "blurry"]
  asset_types: [IMAGE]

# Best iPhone shots
filters:
  is_favorite: true
  camera:
    make: "Apple"
  asset_types: [IMAGE]
```

## Troubleshooting

### Not Getting Expected Results?

1. **Check logs**: See what filters are being applied
   ```
   INFO - Rule xyz: Using new filters: RuleFilters(...)
   INFO - Found N assets matching criteria
   ```

2. **Test with --dry-run**: See what would happen
   ```bash
   python src/main.py --config config.yaml --dry-run --once
   ```

3. **Simplify filters**: Start with just date range, then add filters one by one

4. **Verify EXIF data**: Make sure your assets have the metadata you're filtering on

5. **Check case sensitivity**: Camera make/model are case-sensitive

### No Assets Matched?

Possible reasons:
- Date range doesn't match your assets
- Camera make/model doesn't match EXIF data exactly
- Tags don't exist or are spelled differently
- Asset type filter is too restrictive
- Multiple filters are too specific when combined

**Solution**: Remove filters one by one to find which is excluding your assets.

## API Compatibility

Some filters depend on Immich API support:

| Filter | API Support | Fallback |
|--------|-------------|----------|
| Date ranges | ✅ Always | N/A |
| `is_favorite` | ✅ Usually | None |
| `camera` | ✅ Usually | None |
| `asset_types` | ⚠️ Partial | Client-side check |
| `tags` | ⚠️ Depends | Client-side if needed |

**Note**: If API doesn't support a filter, it may be applied client-side (slower but works).

## Quick Reference Card

```yaml
rules:
  - id: "rule-id"                    # Required, must be unique
    album_name: "Album Name"         # Required
    description: "Description"       # Optional

    # Date filters (top level)
    taken_range_utc:                 # Optional
      start: "YYYY-MM-DDTHH:MM:SS.mmmZ"
      end: "YYYY-MM-DDTHH:MM:SS.mmmZ"

    created_range_utc:               # Optional
      start: "YYYY-MM-DDTHH:MM:SS.mmmZ"
      end: "YYYY-MM-DDTHH:MM:SS.mmmZ"

    # New filters section
    filters:                         # Optional (defaults to IMAGE only)
      is_favorite: true              # Optional: true/false

      asset_types:                   # Optional: default [IMAGE]
        - IMAGE
        - VIDEO

      camera:                        # Optional
        make: "Apple"                # Optional
        model: "iPhone 15 Pro"       # Optional

      tags:                          # Optional
        include:                     # Optional
          - "family"
        exclude:                     # Optional
          - "screenshot"
```

## See Also

- `config.yaml.example` - Complete examples
- `MIGRATION_GUIDE.md` - How to adopt new features
- `IMPLEMENTATION_SUMMARY.md` - Technical details
