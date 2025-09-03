#!/usr/bin/env python3
"""
Debug environment settings to check configuration differences
"""
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings

def check_environment_config():
    """Check environment configuration for proxy and extraction settings"""
    
    print("=== Environment Configuration Debug ===")
    print()
    
    # Check proxy settings
    print("Proxy Configuration:")
    print(f"  USE_PROXY: {getattr(settings, 'USE_PROXY', 'NOT_SET')}")
    print(f"  PROXY_SERVER: {getattr(settings, 'PROXY_SERVER', 'NOT_SET')}")
    print(f"  PROXY_USERNAME: {getattr(settings, 'PROXY_USERNAME', 'NOT_SET')}")
    print(f"  PROXY_PASSWORD: {'***' if getattr(settings, 'PROXY_PASSWORD', None) else 'NOT_SET'}")
    print()
    
    # Check old Decodo settings
    print("Legacy Decodo Configuration:")
    print(f"  DECODO_USERNAME: {getattr(settings, 'DECODO_USERNAME', 'NOT_SET')}")
    print(f"  DECODO_PASSWORD: {'***' if getattr(settings, 'DECODO_PASSWORD', None) else 'NOT_SET'}")
    print(f"  DECODO_ENDPOINT: {getattr(settings, 'DECODO_ENDPOINT', 'NOT_SET')}")
    print(f"  DECODO_PORT_RESIDENTIAL: {getattr(settings, 'DECODO_PORT_RESIDENTIAL', 'NOT_SET')}")
    print()
    
    # Check extraction settings
    print("Content Extraction Configuration:")
    print(f"  USE_INTELLIGENT_EXTRACTION_ONLY: {getattr(settings, 'USE_INTELLIGENT_EXTRACTION_ONLY', 'NOT_SET')}")
    print(f"  INTELLIGENT_EXTRACTION_CONCURRENCY: {getattr(settings, 'INTELLIGENT_EXTRACTION_CONCURRENCY', 'NOT_SET')}")
    print(f"  ARCHIVE_ORG_TIMEOUT: {getattr(settings, 'ARCHIVE_ORG_TIMEOUT', 'NOT_SET')}")
    print()
    
    # Check environment variables from OS
    print("Environment Variables (from OS):")
    proxy_env_vars = [
        'USE_PROXY', 'PROXY_SERVER', 'PROXY_USERNAME', 'PROXY_PASSWORD',
        'DECODO_USERNAME', 'DECODO_PASSWORD', 'DECODO_ENDPOINT'
    ]
    
    for var in proxy_env_vars:
        value = os.environ.get(var, 'NOT_SET')
        if 'PASSWORD' in var and value != 'NOT_SET':
            value = '***'
        print(f"  {var}: {value}")
    print()
    
    # Check if we're in Celery worker context
    celery_vars = ['CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND', 'C_FORCE_ROOT']
    print("Celery Environment:")
    for var in celery_vars:
        value = os.environ.get(var, 'NOT_SET')
        print(f"  {var}: {value}")
    print()
    
    return {
        'proxy_configured': bool(getattr(settings, 'PROXY_SERVER', None)),
        'proxy_username': bool(getattr(settings, 'PROXY_USERNAME', None)),
        'proxy_password': bool(getattr(settings, 'PROXY_PASSWORD', None))
    }

if __name__ == "__main__":
    config_status = check_environment_config()
    
    print("=== Configuration Status ===")
    for key, status in config_status.items():
        print(f"{key}: {'✓' if status else '✗'}")
    
    if all(config_status.values()):
        print("\n✓ Proxy configuration appears complete")
    else:
        print("\n✗ Proxy configuration incomplete - this may explain extraction failures")