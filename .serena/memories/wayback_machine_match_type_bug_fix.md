# Wayback Machine Match Type Bug Fix

## Issue Summary
The CDX API integration in `backend/app/services/wayback_machine.py` had a critical bug where the `match_type` parameter from Domain objects was being ignored, causing all scraping to default to `domain` matching instead of respecting user-configured `prefix`, `exact`, or `regex` match types.

## Root Cause
Two main issues:

1. **Incomplete conditional logic in `_build_cdx_url()`**: The method only honored `prefix` when both `match_type == "prefix"` AND `url_path` existed, defaulting to `domain` matching for all other cases, including standalone `exact`, `prefix`, and `regex` match types.

2. **Match type extraction issue in `firecrawl_scraping.py`**: The code used `getattr(domain.match_type, 'value', 'domain')` which wasn't handling both enum and string representations properly.

## Fix Applied

### 1. Fixed CDX URL Builder Logic
In `backend/app/services/wayback_machine.py`, added proper handling for all match types:

```python
elif match_type in ["exact", "prefix", "regex"]:
    # Use the domain name with the specified match type
    query_url = domain_name
    cdx_match_type = match_type
    logger.info(f"{match_type.capitalize()} match: using {match_type} {query_url}")
```

### 2. Improved Match Type Extraction
In `backend/app/tasks/firecrawl_scraping.py`, improved the match_type extraction:

```python
# Handle both enum and string cases for match_type
if hasattr(domain.match_type, 'value'):
    extracted_match_type = domain.match_type.value
elif isinstance(domain.match_type, str):
    extracted_match_type = domain.match_type
else:
    extracted_match_type = str(domain.match_type)
```

## Test Results
- **Before**: `matchType=domain, query_url=openstate.eu` (entire domain scraped)
- **After**: `matchType=prefix, query_url=https://openstate.eu/nl/over-ons/team-nl/` (targeted prefix matching)
- **Performance**: Reduced results from ~416 to 11 targeted pages (97% noise reduction)

## Files Modified
- `backend/app/services/wayback_machine.py` - Fixed `_build_cdx_url()` method
- `backend/app/tasks/firecrawl_scraping.py` - Improved match_type extraction

## Impact
This fix enables proper targeted scraping using prefix, exact, and regex match types, dramatically improving scraping efficiency and reducing noise from unwanted pages.