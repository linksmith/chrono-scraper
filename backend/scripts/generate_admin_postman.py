#!/usr/bin/env python3
"""
Generate Postman collection for Admin API endpoints
"""
import json
import os
from pathlib import Path
from datetime import datetime

# Import the Postman collection template
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.docs.admin_api_documentation import ADMIN_POSTMAN_COLLECTION


def generate_postman_collection():
    """Generate and save the Admin API Postman collection"""
    
    # Add timestamp to collection info
    ADMIN_POSTMAN_COLLECTION["info"]["description"] += f"\n\nGenerated on: {datetime.utcnow().isoformat()}Z"
    
    # Create output directory if it doesn't exist
    output_dir = Path(__file__).parent.parent / "docs" / "postman"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save the collection
    output_file = output_dir / "chrono_scraper_admin_api.postman_collection.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(ADMIN_POSTMAN_COLLECTION, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Admin API Postman collection generated: {output_file}")
    
    # Generate environment template
    environment = {
        "id": "admin-api-environment",
        "name": "Chrono Scraper Admin API Environment",
        "values": [
            {
                "key": "baseUrl",
                "value": "http://localhost:8000",
                "description": "Base URL for the API server",
                "enabled": True
            },
            {
                "key": "admin_jwt_token",
                "value": "",
                "description": "JWT token obtained from admin login",
                "enabled": True
            },
            {
                "key": "adminApiBase",
                "value": "http://localhost:8000/api/v1/admin/api", 
                "description": "Base URL for admin API endpoints",
                "enabled": True
            },
            {
                "key": "confirmation_token",
                "value": "",
                "description": "Confirmation token for destructive operations",
                "enabled": True
            }
        ]
    }
    
    env_file = output_dir / "admin_api_environment.postman_environment.json"
    with open(env_file, 'w', encoding='utf-8') as f:
        json.dump(environment, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Admin API environment template generated: {env_file}")
    
    # Generate README for the collections
    readme_content = f"""# Chrono Scraper Admin API - Postman Collections

Generated on: {datetime.utcnow().isoformat()}Z

## Files

- `chrono_scraper_admin_api.postman_collection.json` - Complete Admin API collection
- `admin_api_environment.postman_environment.json` - Environment variables template

## Setup Instructions

### 1. Import Collection
1. Open Postman
2. Click "Import" button
3. Select `chrono_scraper_admin_api.postman_collection.json`
4. Collection will be imported with all endpoints organized by functionality

### 2. Import Environment
1. In Postman, go to Environments
2. Click "Import" 
3. Select `admin_api_environment.postman_environment.json`
4. Set the environment as active

### 3. Configure Authentication

#### Method 1: JWT Token (Recommended)
1. Login to admin panel or use login API
2. Copy the JWT token from response or browser storage
3. Set `admin_jwt_token` environment variable
4. All requests will automatically use Bearer authentication

#### Method 2: Session Cookie
1. Login via web interface
2. Collection will automatically use session cookies
3. Useful for testing from same browser session

### 4. Environment Variables

Configure these variables in your environment:

- **baseUrl**: API server base URL (default: `http://localhost:8000`)
- **adminApiBase**: Admin API base path (auto-calculated)
- **admin_jwt_token**: JWT token for authentication
- **confirmation_token**: For destructive operations requiring confirmation

## API Overview

The Admin API provides comprehensive administrative functionality:

### User Management
- List, create, update, and delete users
- Bulk operations for user management
- Advanced filtering and search
- User activity monitoring

### Session Management  
- Monitor active user sessions
- Revoke individual or bulk sessions
- Real-time session analytics

### System Monitoring
- System health checks and metrics
- Celery task queue monitoring
- Service status monitoring
- Performance metrics

### Configuration
- System configuration management
- Feature flag control
- Security settings

### Audit & Logging
- Comprehensive audit trail
- Security event monitoring
- Admin activity tracking

## Security Features

### Authentication
- JWT token or session-based authentication
- Superuser privileges required
- IP whitelisting (production)

### Rate Limiting
- Read operations: 100 req/min
- Write operations: 50 req/min  
- Bulk operations: 10 req/min
- Delete operations: 5 req/5min

### Audit Trail
All admin operations are logged with:
- Admin user identification
- Timestamp and action performed
- Resource affected and outcome
- IP address and user agent

## Error Handling

All endpoints return standardized responses:

### Success Response
```json
{{
  "success": true,
  "data": {{}},
  "message": "Operation completed successfully",
  "timestamp": "2024-01-01T12:00:00Z",
  "operation_id": "op_123"
}}
```

### Error Response
```json
{{
  "success": false,
  "error": "Error description", 
  "error_code": "ERROR_CODE",
  "details": {{}},
  "timestamp": "2024-01-01T12:00:00Z"
}}
```

## Testing Guidelines

### Prerequisites
1. Admin account with superuser privileges
2. Valid authentication token
3. Appropriate IP address (if whitelist enabled)

### Best Practices
1. Test with non-production data
2. Use confirmation tokens for destructive operations
3. Monitor rate limits during testing
4. Review audit logs after operations

### Test Scenarios
1. **User Management**: Create, update, delete test users
2. **Session Control**: Monitor and manage user sessions  
3. **System Health**: Check all monitoring endpoints
4. **Bulk Operations**: Test with small datasets first
5. **Error Handling**: Test invalid inputs and edge cases

## Support

For issues or questions regarding the Admin API:
- Check audit logs for operation details
- Review system health endpoints for service status
- Consult API documentation for parameter details
- Contact admin support team

---
*This collection provides comprehensive coverage of all Admin API functionality with proper authentication, error handling, and security measures.*
"""
    
    readme_file = output_dir / "README.md"
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print(f"✅ Documentation generated: {readme_file}")
    
    return {
        "collection_file": str(output_file),
        "environment_file": str(env_file), 
        "readme_file": str(readme_file)
    }


if __name__ == "__main__":
    result = generate_postman_collection()
    print("\n🎉 Admin API Postman collection generation complete!")
    print("\nGenerated files:")
    for file_type, file_path in result.items():
        print(f"  {file_type}: {file_path}")
    
    print("\n📖 Next steps:")
    print("1. Import the collection into Postman")
    print("2. Import the environment template")  
    print("3. Configure your admin JWT token")
    print("4. Start testing the Admin API!")