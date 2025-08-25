"""
OpenAPI documentation configuration for Admin API
"""
from typing import Dict, Any

# Admin API OpenAPI Tags
ADMIN_API_TAGS = [
    {
        "name": "User Management",
        "description": "Comprehensive user account management operations including creation, updates, deletion, and bulk operations"
    },
    {
        "name": "Session Management", 
        "description": "Real-time session monitoring and management with bulk revocation capabilities"
    },
    {
        "name": "Content Management",
        "description": "Page and entity content management with filtering and bulk operations"
    },
    {
        "name": "System Monitoring",
        "description": "System health checks, metrics, and service status monitoring"
    },
    {
        "name": "Configuration",
        "description": "System configuration management and feature flag control"
    },
    {
        "name": "Audit & Logging",
        "description": "Comprehensive audit trail and security event monitoring"
    },
    {
        "name": "Backup & Recovery",
        "description": "Data backup creation, management, and restoration operations"
    },
    {
        "name": "Bulk Operations",
        "description": "High-performance bulk operations for users, content, and system data"
    },
    {
        "name": "Analytics & Reporting",
        "description": "Advanced analytics, metrics, and comprehensive reporting"
    }
]

# Admin API Documentation Configuration
ADMIN_API_OPENAPI_CONFIG = {
    "title": "Chrono Scraper Admin API",
    "description": """
## Chrono Scraper Admin API

The comprehensive administrative API for Chrono Scraper, providing full programmatic access to all admin functionality.

### Features

🔐 **Security First**
- JWT token authentication
- Role-based access control (superuser required)
- IP address whitelisting
- Rate limiting per operation type
- Comprehensive audit logging
- CSRF protection

📊 **Comprehensive Management**
- User account management with bulk operations
- Real-time session monitoring and control
- Content management and moderation
- System health monitoring and metrics
- Configuration management
- Backup and recovery operations

🚀 **Performance & Scalability**
- Optimized database queries
- Pagination for all list endpoints
- Background task processing
- Rate limiting to prevent abuse
- Efficient bulk operations

### Authentication

All admin API endpoints require:
1. Valid JWT session token or API key
2. Superuser (admin) privileges
3. IP address in allowed list (production)

### Rate Limits

Different rate limits apply based on operation sensitivity:
- **Read operations**: 100 requests/minute
- **Write operations**: 50 requests/minute  
- **Bulk operations**: 10 requests/minute
- **Delete operations**: 5 requests/5 minutes
- **Export/backup**: 5 requests/5 minutes

### Error Handling

All endpoints return standardized error responses with:
- Clear error messages and codes
- Request tracking IDs
- Detailed error context
- Proper HTTP status codes

### Audit Trail

All admin operations are automatically logged with:
- Admin user identification
- Action performed and timestamp
- Resource type and ID affected
- IP address and user agent
- Success/failure status
- Detailed operation context

### Security Headers

All responses include comprehensive security headers:
- Content Security Policy
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- Cache-Control: no-cache, no-store
- Admin-specific security markers
""",
    "version": "1.0.0",
    "contact": {
        "name": "Admin API Support",
        "email": "admin@chrono-scraper.com"
    },
    "license": {
        "name": "Proprietary",
        "identifier": "Proprietary"
    }
}

# Common API Response Examples
ADMIN_API_EXAMPLES = {
    "success_response": {
        "summary": "Successful Operation",
        "value": {
            "success": True,
            "data": {"id": 123, "status": "updated"},
            "message": "Operation completed successfully",
            "timestamp": "2024-01-01T12:00:00Z",
            "operation_id": "op_abc123"
        }
    },
    "error_response": {
        "summary": "Error Response",
        "value": {
            "success": False,
            "error": "Resource not found",
            "error_code": "USER_NOT_FOUND",
            "details": {"user_id": 123},
            "timestamp": "2024-01-01T12:00:00Z",
            "request_id": "req_xyz789"
        }
    },
    "pagination_response": {
        "summary": "Paginated Results",
        "value": {
            "items": [{"id": 1, "name": "Item 1"}],
            "total": 100,
            "page": 1,
            "per_page": 20,
            "pages": 5,
            "has_next": True,
            "has_prev": False
        }
    },
    "bulk_operation_result": {
        "summary": "Bulk Operation Result",
        "value": {
            "success": True,
            "message": "Bulk operation completed",
            "affected_count": 15,
            "operation_id": "bulk_op_456",
            "data": {
                "successful_ids": [1, 2, 3],
                "failed_ids": [],
                "failed_reasons": {}
            },
            "timestamp": "2024-01-01T12:00:00Z"
        }
    }
}

# Security Scheme Configuration
ADMIN_API_SECURITY_SCHEMES = {
    "AdminBearerAuth": {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "JWT token obtained from login endpoint"
    },
    "AdminAPIKey": {
        "type": "apiKey", 
        "in": "header",
        "name": "Authorization",
        "description": "API key with 'Bearer' prefix (e.g., 'Bearer cs_your_api_key')"
    },
    "AdminSessionAuth": {
        "type": "apiKey",
        "in": "cookie", 
        "name": "session_id",
        "description": "Session cookie for web-based admin interface"
    }
}

# Common HTTP Status Code Documentation
ADMIN_API_STATUS_CODES = {
    200: {"description": "Operation successful"},
    201: {"description": "Resource created successfully"},
    400: {"description": "Bad request - invalid parameters or missing required fields"},
    401: {"description": "Unauthorized - authentication required"},
    403: {"description": "Forbidden - insufficient admin privileges or IP not allowed"},
    404: {"description": "Resource not found"},
    409: {"description": "Conflict - resource already exists or operation not allowed"},
    422: {"description": "Validation error - request data failed validation"},
    429: {"description": "Rate limit exceeded - too many requests"},
    500: {"description": "Internal server error"}
}

def get_admin_endpoint_documentation(operation_name: str, operation_type: str = "read") -> Dict[str, Any]:
    """
    Generate standardized documentation for admin endpoints
    
    Args:
        operation_name: Name of the operation (e.g., "list_users")
        operation_type: Type of operation for rate limiting info
    
    Returns:
        Dictionary with OpenAPI documentation elements
    """
    
    rate_limits = {
        "read": "100 requests/minute",
        "write": "50 requests/minute", 
        "bulk": "10 requests/minute",
        "delete": "5 requests/5 minutes",
        "export": "5 requests/5 minutes",
        "config": "10 requests/5 minutes"
    }
    
    return {
        "security": [
            {"AdminBearerAuth": []},
            {"AdminAPIKey": []}, 
            {"AdminSessionAuth": []}
        ],
        "responses": {
            **ADMIN_API_STATUS_CODES,
            200: {
                **ADMIN_API_STATUS_CODES[200],
                "headers": {
                    "X-Admin-API": {
                        "description": "Admin API marker",
                        "schema": {"type": "string", "example": "true"}
                    },
                    "X-Rate-Limit": {
                        "description": "Current rate limit status",
                        "schema": {"type": "string", "example": rate_limits.get(operation_type, "100 requests/minute")}
                    }
                }
            }
        },
        "tags": [operation_type.replace("_", " ").title() + " Operations"],
        "summary": f"Admin {operation_name.replace('_', ' ').title()}",
        "operationId": f"admin_{operation_name}"
    }

# Admin API Postman Collection Template
ADMIN_POSTMAN_COLLECTION = {
    "info": {
        "name": "Chrono Scraper Admin API",
        "description": "Comprehensive admin API collection for Chrono Scraper with all endpoints and examples",
        "version": "1.0.0",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "auth": {
        "type": "bearer",
        "bearer": [
            {
                "key": "token",
                "value": "{{admin_jwt_token}}",
                "type": "string"
            }
        ]
    },
    "event": [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "// Set base URL if not already set",
                    "if (!pm.variables.get('baseUrl')) {",
                    "    pm.variables.set('baseUrl', 'http://localhost:8000');",
                    "}",
                    "",
                    "// Add admin API prefix",
                    "const adminApiBase = pm.variables.get('baseUrl') + '/api/v1/admin/api';",
                    "pm.variables.set('adminApiBase', adminApiBase);"
                ]
            }
        }
    ],
    "variable": [
        {
            "key": "baseUrl",
            "value": "http://localhost:8000",
            "description": "Base URL for the API"
        },
        {
            "key": "admin_jwt_token",
            "value": "",
            "description": "JWT token for admin authentication"
        },
        {
            "key": "adminApiBase",
            "value": "http://localhost:8000/api/v1/admin/api",
            "description": "Base URL for admin API endpoints"
        }
    ],
    "item": [
        {
            "name": "User Management",
            "description": "User account management endpoints",
            "item": [
                {
                    "name": "List Users",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/users?page=1&per_page=20&search=&approval_status=&is_active=&sort_by=created_at&sort_order=desc",
                            "host": ["{{adminApiBase}}"],
                            "path": ["users"],
                            "query": [
                                {"key": "page", "value": "1", "description": "Page number (starting from 1)"},
                                {"key": "per_page", "value": "20", "description": "Items per page (1-100)"},
                                {"key": "search", "value": "", "description": "Search in email, name, research fields"},
                                {"key": "approval_status", "value": "", "description": "Filter by approval status"},
                                {"key": "is_active", "value": "", "description": "Filter by active status"},
                                {"key": "sort_by", "value": "created_at", "description": "Sort field"},
                                {"key": "sort_order", "value": "desc", "description": "Sort order"}
                            ]
                        },
                        "description": "Get paginated list of all users with filtering options"
                    }
                },
                {
                    "name": "Get User",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/users/:userId",
                            "host": ["{{adminApiBase}}"],
                            "path": ["users", ":userId"],
                            "variable": [
                                {"key": "userId", "value": "1", "description": "User ID"}
                            ]
                        },
                        "description": "Get detailed information for a specific user"
                    }
                },
                {
                    "name": "Create User", 
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"email\": \"admin.created@example.com\",\n  \"full_name\": \"Admin Created User\",\n  \"password\": \"SecurePassword123!\",\n  \"is_active\": true,\n  \"is_verified\": true,\n  \"is_superuser\": false,\n  \"approval_status\": \"approved\",\n  \"research_interests\": \"Admin created account\",\n  \"research_purpose\": \"Administrative purposes\",\n  \"expected_usage\": \"Standard platform usage\",\n  \"send_welcome_email\": true\n}"
                        },
                        "url": {
                            "raw": "{{adminApiBase}}/users",
                            "host": ["{{adminApiBase}}"],
                            "path": ["users"]
                        },
                        "description": "Create a new user account with admin privileges"
                    }
                },
                {
                    "name": "Update User",
                    "request": {
                        "method": "PUT",
                        "header": [
                            {
                                "key": "Content-Type", 
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"full_name\": \"Updated Full Name\",\n  \"is_active\": true,\n  \"approval_status\": \"approved\"\n}"
                        },
                        "url": {
                            "raw": "{{adminApiBase}}/users/:userId",
                            "host": ["{{adminApiBase}}"],
                            "path": ["users", ":userId"],
                            "variable": [
                                {"key": "userId", "value": "1", "description": "User ID"}
                            ]
                        },
                        "description": "Update user account details and status"
                    }
                },
                {
                    "name": "Delete User",
                    "request": {
                        "method": "DELETE",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/users/:userId?confirmation_token=REQUIRED_TOKEN",
                            "host": ["{{adminApiBase}}"],
                            "path": ["users", ":userId"],
                            "query": [
                                {"key": "confirmation_token", "value": "REQUIRED_TOKEN", "description": "Required confirmation token"}
                            ],
                            "variable": [
                                {"key": "userId", "value": "1", "description": "User ID"}
                            ]
                        },
                        "description": "Delete a user account permanently (requires confirmation)"
                    }
                }
            ]
        },
        {
            "name": "Session Management", 
            "description": "User session monitoring and management",
            "item": [
                {
                    "name": "List Sessions",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/sessions?page=1&per_page=50&user_id=&active_only=true",
                            "host": ["{{adminApiBase}}"],
                            "path": ["sessions"],
                            "query": [
                                {"key": "page", "value": "1"},
                                {"key": "per_page", "value": "50"},
                                {"key": "user_id", "value": "", "description": "Filter by user ID"},
                                {"key": "active_only", "value": "true", "description": "Show only active sessions"}
                            ]
                        },
                        "description": "List active user sessions with filtering"
                    }
                },
                {
                    "name": "Revoke Session",
                    "request": {
                        "method": "DELETE",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/sessions/:sessionId",
                            "host": ["{{adminApiBase}}"],
                            "path": ["sessions", ":sessionId"],
                            "variable": [
                                {"key": "sessionId", "value": "session_123", "description": "Session ID"}
                            ]
                        },
                        "description": "Revoke a specific user session"
                    }
                },
                {
                    "name": "Bulk Revoke Sessions",
                    "request": {
                        "method": "POST",
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"user_ids\": [1, 2, 3],\n  \"revoke_all_except_current\": true,\n  \"reason\": \"Security maintenance\"\n}"
                        },
                        "url": {
                            "raw": "{{adminApiBase}}/sessions/bulk-revoke",
                            "host": ["{{adminApiBase}}"],
                            "path": ["sessions", "bulk-revoke"]
                        },
                        "description": "Revoke multiple sessions in bulk"
                    }
                }
            ]
        },
        {
            "name": "System Monitoring",
            "description": "System health and monitoring endpoints",
            "item": [
                {
                    "name": "System Health",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/system/health",
                            "host": ["{{adminApiBase}}"],
                            "path": ["system", "health"]
                        },
                        "description": "Get comprehensive system health status"
                    }
                },
                {
                    "name": "System Metrics",
                    "request": {
                        "method": "GET", 
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/system/metrics",
                            "host": ["{{adminApiBase}}"],
                            "path": ["system", "metrics"]
                        },
                        "description": "Get detailed system metrics and statistics"
                    }
                },
                {
                    "name": "Celery Status",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/celery/status",
                            "host": ["{{adminApiBase}}"],
                            "path": ["celery", "status"]
                        },
                        "description": "Get Celery task queue status and statistics"
                    }
                }
            ]
        },
        {
            "name": "Configuration",
            "description": "System configuration management",
            "item": [
                {
                    "name": "Get System Config",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/config", 
                            "host": ["{{adminApiBase}}"],
                            "path": ["config"]
                        },
                        "description": "Get system configuration information"
                    }
                }
            ]
        },
        {
            "name": "Audit & Logging",
            "description": "Audit trail and security monitoring",
            "item": [
                {
                    "name": "Get Audit Logs",
                    "request": {
                        "method": "GET",
                        "header": [],
                        "url": {
                            "raw": "{{adminApiBase}}/audit/logs?page=1&per_page=50&action=&resource_type=&success=&start_date=&end_date=",
                            "host": ["{{adminApiBase}}"],
                            "path": ["audit", "logs"],
                            "query": [
                                {"key": "page", "value": "1"},
                                {"key": "per_page", "value": "50"},
                                {"key": "action", "value": "", "description": "Filter by action"},
                                {"key": "resource_type", "value": "", "description": "Filter by resource type"},
                                {"key": "success", "value": "", "description": "Filter by success status"},
                                {"key": "start_date", "value": "", "description": "Start date filter"},
                                {"key": "end_date", "value": "", "description": "End date filter"}
                            ]
                        },
                        "description": "Get audit logs with advanced filtering"
                    }
                }
            ]
        }
    ]
}