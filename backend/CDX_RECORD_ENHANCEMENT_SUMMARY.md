# CDXRecord Multi-Source Enhancement Summary

## Overview
Enhanced the `CDXRecord` class in `backend/app/services/wayback_machine.py` to support both Wayback Machine and Common Crawl archive sources while maintaining full backward compatibility.

## Key Enhancements

### 1. Archive Source Tracking
- Added `source: ArchiveSource` field with default `WAYBACK_MACHINE` for backward compatibility
- Imported `ArchiveSource` enum from `models.project`
- Added source-specific fields for Common Crawl WARC metadata

### 2. Factory Methods
Added two class methods for creating records from different sources:

```python
@classmethod
def from_wayback_response(cls, cdx_line: Union[str, List]) -> 'CDXRecord':
    """Create CDXRecord from Wayback Machine CDX API response"""

@classmethod  
def from_common_crawl_response(cls, cdx_obj: Union[Dict, object]) -> 'CDXRecord':
    """Create CDXRecord from Common Crawl CDX response"""
```

### 3. Enhanced Properties
- **New Properties:**
  - `archive_url`: Generic property that returns appropriate URL based on source
  - `is_wayback_machine`: Boolean check for Wayback Machine source
  - `is_common_crawl`: Boolean check for Common Crawl source
  - `warc_filename`: Extract WARC filename when available (Common Crawl)

- **Enhanced Legacy Properties:**
  - `wayback_url`: Now handles non-Wayback sources gracefully
  - `content_url`: Generates WARC URLs for Common Crawl when available
  - `capture_date`: Supports multiple timestamp formats (Wayback, ISO)

### 4. Common Crawl Integration
- Support for WARC file metadata (`warc_filename`, `warc_offset`, `warc_length`)
- Automatic WARC URL generation: `https://data.commoncrawl.org/{path}?offset={offset}&length={length}`
- Handles both cdx_toolkit objects and dictionary responses
- Normalizes field name differences between sources

### 5. Error Handling & Robustness
- Graceful degradation when source-specific data isn't available
- Robust timestamp parsing for multiple formats
- Clear warnings for inappropriate property usage
- Fallback behaviors for missing WARC data

### 6. Backward Compatibility
- Existing direct construction continues to work unchanged
- All existing properties maintain their behavior for Wayback Machine records
- Default source is `WAYBACK_MACHINE` when not specified
- No breaking changes to existing API

## Implementation Details

### Data Structure
```python
@dataclass
class CDXRecord:
    # Core fields (unchanged)
    timestamp: str
    original_url: str
    mime_type: str
    status_code: str
    digest: str
    length: str
    
    # New fields for multi-source support
    source: ArchiveSource = ArchiveSource.WAYBACK_MACHINE
    warc_filename: Optional[str] = None
    warc_offset: Optional[int] = None  
    warc_length: Optional[int] = None
```

### URL Generation Logic
```python
# Wayback Machine
archive_url = f"https://web.archive.org/web/{timestamp}/{url}"

# Common Crawl (with WARC data)
archive_url = f"https://data.commoncrawl.org/{warc_filename}?offset={offset}&length={length}"

# Fallback
archive_url = f"{url} (from {source})"
```

### Timestamp Format Support
- Standard: `YYYYMMDDHHMMSS` (Wayback Machine format)
- ISO: `YYYY-MM-DDTHH:MM:SSZ` (Common Crawl format)
- Short: Padded with zeros for compatibility
- Malformed: Fallback to epoch time with warning

## Usage Examples

### Wayback Machine (Existing Code)
```python
# Continues to work unchanged
record = CDXRecord.from_wayback_response(cdx_row)
url = record.wayback_url
content = record.content_url
```

### Common Crawl (New)
```python
record = CDXRecord.from_common_crawl_response(cc_data)
url = record.archive_url  # Returns WARC URL
is_cc = record.is_common_crawl  # True
```

### Archive-Agnostic Code
```python
# Works with any source
if record.is_wayback_machine:
    url = record.wayback_url
elif record.is_common_crawl and record.warc_filename:
    url = record.archive_url
else:
    url = record.original_url
```

## Testing Verification
- ✅ Wayback Machine support (backward compatibility)
- ✅ Common Crawl support with WARC URLs  
- ✅ Factory methods for different sources
- ✅ Archive-agnostic properties
- ✅ Robust error handling
- ✅ Multiple timestamp formats
- ✅ Docker environment compatibility

## Integration Points
- Compatible with existing `CDXAPIClient` class
- Ready for future `CommonCrawlService` integration
- Filters (`StaticAssetFilter`, `ListPageFilter`, etc.) work with all sources
- Existing scraping pipeline unchanged

## Benefits
1. **Future-Proof**: Ready for Common Crawl integration
2. **Backward Compatible**: Zero breaking changes to existing code
3. **Flexible**: Archive-agnostic properties for universal usage
4. **Robust**: Comprehensive error handling and fallbacks
5. **Maintainable**: Clear separation of concerns between archive sources
6. **Extensible**: Easy to add support for additional archive sources

The enhanced CDXRecord provides a solid foundation for multi-source archive support while ensuring existing Wayback Machine functionality continues to work seamlessly.