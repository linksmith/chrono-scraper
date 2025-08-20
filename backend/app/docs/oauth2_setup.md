# OAuth2 Integration Setup Guide

This guide explains how to configure and use OAuth2 authentication with Google and GitHub providers in Chrono Scraper v2.

## Overview

The OAuth2 system provides secure authentication using external providers (Google, GitHub) while maintaining session-based authentication for the application. Key features:

- **Secure State Management**: OAuth2 states stored in Redis with TTL
- **Provider Abstraction**: Unified interface for different OAuth2 providers  
- **Session Integration**: OAuth2 authentication creates standard user sessions
- **Error Handling**: Comprehensive error handling with user-friendly redirects
- **Security**: CSRF protection, state validation, and secure cookie handling

## Architecture Components

### Core Components

1. **OAuth2Provider Classes**: Abstract base class with Google/GitHub implementations
2. **OAuth2StateManager**: Redis-based state management for security
3. **OAuth2ProviderManager**: Central manager for provider instances
4. **OAuth2 API Endpoints**: RESTful endpoints for OAuth2 flow
5. **Session Integration**: Creates standard sessions after OAuth2 success

### Security Features

- **State Parameter Validation**: Prevents CSRF attacks
- **Redis State Storage**: Secure, TTL-based state management
- **Session Security**: HttpOnly, SameSite, and Secure cookies
- **Provider Verification**: Validates OAuth2 responses
- **Error Handling**: Secure error responses without information leakage

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# OAuth2 Configuration
OAUTH2_ENABLED=true

# Google OAuth2
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# GitHub OAuth2  
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret

# URLs for OAuth2 redirects
BACKEND_URL=http://localhost:8000  # Your backend URL
FRONTEND_URL=http://localhost:5173 # Your frontend URL
```

### Provider Setup

#### Google OAuth2 Setup

1. **Google Cloud Console**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable "Google+ API" and "Google OAuth2 API"
   
2. **Create OAuth2 Credentials**:
   - Go to "Credentials" → "Create Credentials" → "OAuth2 Client ID"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8000/api/v1/auth/oauth2/google/callback` (development)
     - `https://yourdomain.com/api/v1/auth/oauth2/google/callback` (production)

3. **Configure Scopes**:
   - The application requests: `openid email profile`
   - This provides: User ID, email, full name, profile picture

#### GitHub OAuth2 Setup

1. **GitHub Developer Settings**:
   - Go to GitHub → Settings → Developer settings → OAuth Apps
   - Click "New OAuth App"
   
2. **Application Configuration**:
   - **Application name**: Chrono Scraper v2
   - **Homepage URL**: `http://localhost:5173` (development)
   - **Authorization callback URL**: `http://localhost:8000/api/v1/auth/oauth2/github/callback`
   
3. **Configure Scopes**:
   - The application requests: `user:email`
   - This provides: User profile and email addresses

## API Endpoints

### List Available Providers

```http
GET /api/v1/auth/oauth2/providers
```

**Response**:
```json
{
  "providers": ["google", "github"],
  "enabled": true
}
```

### Initiate OAuth2 Login

```http
GET /api/v1/auth/oauth2/{provider}/login
```

**Parameters**:
- `provider`: `google` or `github`

**Response**: Redirects to OAuth2 provider authorization URL

### OAuth2 Callback (Internal)

```http
GET /api/v1/auth/oauth2/{provider}/callback?code=...&state=...
```

**Parameters**:
- `provider`: `google` or `github`  
- `code`: Authorization code from provider
- `state`: Security state parameter

**Response**: Redirects to frontend with authentication result

## Frontend Integration

### Initiate OAuth2 Login

```javascript
// Redirect to OAuth2 provider
const initiateOAuth2Login = (provider) => {
  window.location.href = `/api/v1/auth/oauth2/${provider}/login`;
};

// Usage
initiateOAuth2Login('google');  // For Google
initiateOAuth2Login('github');  // For GitHub
```

### Handle OAuth2 Results

The OAuth2 callback redirects to frontend routes:

- **Success**: `/auth/oauth2-success?provider={provider}`
- **Error**: `/auth/login?error={error_code}&provider={provider}`
- **Pending Approval**: `/auth/pending-approval?provider={provider}`

```javascript
// Handle OAuth2 success
const handleOAuth2Success = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const provider = urlParams.get('provider');
  
  if (provider) {
    // User is now authenticated
    // Redirect to dashboard or show success message
    window.location.href = '/dashboard';
  }
};

// Handle OAuth2 errors
const handleOAuth2Error = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const error = urlParams.get('error');
  const provider = urlParams.get('provider');
  
  switch (error) {
    case 'oauth2_denied':
      showError('OAuth2 authorization denied');
      break;
    case 'oauth2_invalid_request':
      showError('Invalid OAuth2 request');
      break;
    case 'oauth2_server_error':
      showError('OAuth2 server error');
      break;
  }
};
```

### Check OAuth2 Status

```javascript
// Check if OAuth2 is enabled and get providers
const getOAuth2Config = async () => {
  try {
    const response = await fetch('/api/v1/auth/oauth2/providers');
    const config = await response.json();
    
    return config; // { providers: [...], enabled: true/false }
  } catch (error) {
    console.error('Failed to get OAuth2 config:', error);
    return { providers: [], enabled: false };
  }
};
```

## User Flow

### New User Registration via OAuth2

1. User clicks "Login with Google/GitHub" button
2. Redirected to OAuth2 provider for authorization  
3. User grants permissions
4. Provider redirects back with authorization code
5. Backend exchanges code for access token
6. Backend fetches user profile from provider
7. New user account created with OAuth2 information
8. User session created and cookies set
9. User redirected to pending approval page (if approval required)

### Existing User Login via OAuth2

1. Same flow as new user through step 6
2. Existing user found by email address
3. OAuth2 information linked to existing account (if not already)
4. User session created and cookies set
5. User redirected to dashboard (if approved)

### User Approval Process

OAuth2 users still require admin approval:

- **Automatic Email Verification**: OAuth2 emails are pre-verified
- **Pending Approval Status**: Users wait for admin approval
- **Admin Notification**: Admins notified of new OAuth2 registrations
- **Approval Required**: Users cannot access application until approved

## Security Considerations

### State Parameter Security

- **Random Generation**: 256-bit random state parameters
- **Redis Storage**: States stored in Redis with 10-minute TTL
- **One-Time Use**: States consumed after successful validation
- **Provider Validation**: State tied to specific OAuth2 provider

### Session Security

- **HttpOnly Cookies**: Prevents XSS access to session cookies
- **SameSite Protection**: CSRF protection via SameSite=Lax
- **Secure Cookies**: HTTPS-only cookies in production
- **Session Expiry**: Configurable session timeout

### Error Handling

- **No Information Leakage**: Generic error messages to prevent enumeration
- **Secure Redirects**: All redirects validate destination URLs
- **Logging**: Security events logged for monitoring
- **Rate Limiting**: OAuth2 endpoints protected by rate limiting

## Development Testing

### Mock OAuth2 Providers

For development, you can mock OAuth2 responses:

```python
# test_oauth2_mock.py
@patch('app.core.oauth2.GoogleOAuth2Provider.get_user_info')
async def test_mock_google_login(mock_get_user_info):
    mock_get_user_info.return_value = {
        "id": "123456789",
        "email": "test@example.com", 
        "name": "Test User",
        "verified_email": True
    }
    
    # Test OAuth2 flow with mocked response
```

### Local Testing

1. **Use ngrok for HTTPS** (required for some providers):
   ```bash
   ngrok http 8000
   # Use ngrok URL as BACKEND_URL
   ```

2. **Configure Test Apps**:
   - Use `localhost` URLs for development
   - Set up separate OAuth2 apps for testing
   - Use test credentials in `.env.test`

## Troubleshooting

### Common Issues

1. **Redirect URI Mismatch**:
   - Ensure OAuth2 app redirect URIs match exactly
   - Check for trailing slashes or protocol mismatches
   - Verify BACKEND_URL environment variable

2. **Invalid State Parameter**:
   - Check Redis connectivity
   - Verify state TTL (10 minutes default)
   - Ensure single browser session (no parallel logins)

3. **User Not Found After OAuth2**:
   - Check email address from OAuth2 provider
   - Verify user creation logic
   - Check approval status and email verification

4. **Session Not Created**:
   - Check Redis session store connectivity
   - Verify cookie settings (SameSite, Secure)
   - Check session store configuration

### Debug Mode

Enable OAuth2 debugging:

```python
# In development
import logging
logging.getLogger('app.services.oauth2').setLevel(logging.DEBUG)
logging.getLogger('app.api.v1.endpoints.oauth2').setLevel(logging.DEBUG)
```

### Testing Checklist

- [ ] OAuth2 providers configured correctly
- [ ] Redirect URIs match exactly
- [ ] Environment variables set
- [ ] Redis connection working
- [ ] Session cookies set correctly
- [ ] User approval workflow functioning
- [ ] Error handling working
- [ ] Frontend integration complete

## Production Deployment

### Security Configuration

```bash
# Production environment variables
ENVIRONMENT=production
OAUTH2_ENABLED=true
BACKEND_URL=https://api.yourdomain.com
FRONTEND_URL=https://yourdomain.com

# Secure Redis connection
REDIS_URL=rediss://your-redis-instance:6380

# SSL/HTTPS enforcement
FORCE_HTTPS=true
```

### Monitoring

Monitor OAuth2 authentication:

- **Success Rates**: Track successful OAuth2 logins
- **Error Rates**: Monitor authentication failures  
- **State Validation**: Track state validation failures
- **Session Creation**: Monitor session creation success
- **User Approval**: Track approval workflow completion

### Maintenance

- **Rotate OAuth2 Secrets**: Regularly update client secrets
- **Monitor Provider Changes**: Stay updated with provider API changes
- **Update Scopes**: Adjust requested scopes as needed
- **Clear Expired States**: Redis automatically handles TTL cleanup

## Advanced Configuration

### Custom OAuth2 Providers

To add additional OAuth2 providers:

1. **Create Provider Class**:
   ```python
   class CustomOAuth2Provider(OAuth2Provider):
       def get_authorization_url(self, state: str) -> str:
           # Implementation
       
       async def get_access_token(self, code: str, state: str):
           # Implementation
       
       async def get_user_info(self, access_token: str):
           # Implementation
   ```

2. **Register Provider**:
   ```python
   # In oauth2_providers.py
   def _initialize_providers(self):
       # Existing providers...
       
       if settings.CUSTOM_CLIENT_ID and settings.CUSTOM_CLIENT_SECRET:
           self.providers["custom"] = CustomOAuth2Provider(
               client_id=settings.CUSTOM_CLIENT_ID,
               client_secret=settings.CUSTOM_CLIENT_SECRET,
               redirect_uri=f"{base_redirect_uri}/custom/callback"
           )
   ```

### Custom User Data Mapping

Customize OAuth2 user data mapping:

```python
# In normalize_oauth2_user_data function
elif provider == "custom":
    return {
        "email": user_data.get("email_address"),
        "full_name": f"{user_data.get('first_name')} {user_data.get('last_name')}",
        "oauth2_provider": provider,
        "oauth2_id": str(user_data.get("user_id")),
        "is_verified": user_data.get("email_verified", False),
        # Custom fields
        "custom_field": user_data.get("custom_field")
    }
```

This completes the OAuth2 integration setup guide for Chrono Scraper v2.