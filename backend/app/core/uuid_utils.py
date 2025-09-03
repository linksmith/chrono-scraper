"""
UUID utilities for the application
"""
import time
import uuid
from typing import Union


def uuid_v7() -> uuid.UUID:
    """
    Generate a UUIDv7 with time-based ordering for better database indexing.
    
    UUIDv7 format (RFC 9562):
    - 48-bit timestamp (milliseconds since Unix epoch)  
    - 12-bit random data for sub-millisecond ordering
    - 4-bit version (0111 = 7)
    - 2-bit variant (10) 
    - 62-bit random data
    
    Returns:
        UUID: A UUIDv7 with time-based prefix for optimal database indexing
    """
    # Get current time in milliseconds
    timestamp_ms = int(time.time() * 1000)
    
    # Generate random bytes for the rest
    random_bytes = uuid.uuid4().bytes
    
    # Build UUID bytes manually for better control
    uuid_bytes = bytearray(16)
    
    # First 6 bytes: 48-bit timestamp (big-endian)
    uuid_bytes[0] = (timestamp_ms >> 40) & 0xFF
    uuid_bytes[1] = (timestamp_ms >> 32) & 0xFF  
    uuid_bytes[2] = (timestamp_ms >> 24) & 0xFF
    uuid_bytes[3] = (timestamp_ms >> 16) & 0xFF
    uuid_bytes[4] = (timestamp_ms >> 8) & 0xFF
    uuid_bytes[5] = timestamp_ms & 0xFF
    
    # Next 2 bytes: 12-bit random + 4-bit version
    uuid_bytes[6] = (random_bytes[6] & 0x0F) | 0x70  # Version 7 in upper nibble
    uuid_bytes[7] = random_bytes[7]
    
    # Next 2 bytes: 2-bit variant + 14-bit random  
    uuid_bytes[8] = (random_bytes[8] & 0x3F) | 0x80  # Variant 10
    uuid_bytes[9] = random_bytes[9]
    
    # Last 6 bytes: 48-bit random
    uuid_bytes[10:16] = random_bytes[10:16]
    
    return uuid.UUID(bytes=bytes(uuid_bytes))


def is_uuid_v7(uuid_obj: Union[uuid.UUID, str]) -> bool:
    """
    Check if a UUID is version 7.
    
    Args:
        uuid_obj: UUID object or string to check
        
    Returns:
        bool: True if UUID is version 7
    """
    if isinstance(uuid_obj, str):
        uuid_obj = uuid.UUID(uuid_obj)
    
    return uuid_obj.version == 7


def extract_timestamp_from_uuid_v7(uuid_obj: Union[uuid.UUID, str]) -> int:
    """
    Extract timestamp from UUIDv7.
    
    Args:
        uuid_obj: UUIDv7 object or string
        
    Returns:
        int: Timestamp in milliseconds since Unix epoch
        
    Raises:
        ValueError: If UUID is not version 7
    """
    if isinstance(uuid_obj, str):
        uuid_obj = uuid.UUID(uuid_obj)
    
    if not is_uuid_v7(uuid_obj):
        raise ValueError("UUID is not version 7")
    
    # Extract 48-bit timestamp from most significant bits
    return (uuid_obj.int >> 80) & 0xFFFFFFFFFFFF