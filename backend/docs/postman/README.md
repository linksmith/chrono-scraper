# Chrono Scraper Admin API - Postman Collections

Generated on: 2025-08-24T10:31:44.008741Z

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
{
  "success": true,
  "data": {},
  "message": "Operation completed successfully",
  "timestamp": "2024-01-01T12:00:00Z",
  "operation_id": "op_123"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error description", 
  "error_code": "ERROR_CODE",
  "details": {},
  "timestamp": "2024-01-01T12:00:00Z"
}
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
