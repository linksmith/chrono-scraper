# Email Configuration Guide

## Overview

Chrono Scraper v2 supports multiple email providers to handle transactional emails like password resets, email verification, and user notifications.

## Email Providers

### Development: Mailpit
In development, emails are automatically sent to Mailpit, a local email testing tool that captures all outgoing emails.

- **SMTP Host**: `mailpit`
- **SMTP Port**: `1025`
- **Web Interface**: http://localhost:8025
- **No authentication required**

### Production: Mailgun (Recommended)
For production, we recommend using Mailgun for reliable email delivery.

#### Mailgun Setup

1. **Sign up for Mailgun**: https://www.mailgun.com
2. **Verify your domain** in the Mailgun dashboard
3. **Get your API credentials**:
   - API Key: Found in Settings → API Keys
   - Domain: Your verified domain (e.g., `mg.yourdomain.com`)

4. **Configure environment variables**:
```env
# Required for Mailgun
MAILGUN_API_KEY=your-mailgun-api-key
MAILGUN_DOMAIN=mg.yourdomain.com
MAILGUN_EU_REGION=false  # Set to true if using EU region

# Email settings
EMAILS_FROM_EMAIL=noreply@yourdomain.com
EMAILS_FROM_NAME=Your App Name
ENVIRONMENT=production
FRONTEND_URL=https://yourdomain.com
```

### Alternative: SMTP Provider
You can also use any SMTP provider (Gmail, SendGrid, Amazon SES, etc.):

```env
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=true
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
EMAILS_FROM_EMAIL=your-email@gmail.com
EMAILS_FROM_NAME=Your App Name
```

## Environment Variables

### Core Email Settings

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `ENVIRONMENT` | Environment mode (`development` or `production`) | `development` | Yes |
| `EMAILS_FROM_EMAIL` | Sender email address | None | Yes |
| `EMAILS_FROM_NAME` | Sender display name | Project name | No |
| `FRONTEND_URL` | Frontend URL for email links (production) | None | Yes (prod) |

### Mailgun Settings (Production)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `MAILGUN_API_KEY` | Mailgun API key | None | Yes (if using) |
| `MAILGUN_DOMAIN` | Mailgun domain | None | Yes (if using) |
| `MAILGUN_EU_REGION` | Use EU Mailgun region | `false` | No |

### SMTP Settings (Alternative)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SMTP_HOST` | SMTP server hostname | None | Yes (if using) |
| `SMTP_PORT` | SMTP server port | `587` | No |
| `SMTP_TLS` | Enable TLS/STARTTLS | `true` | No |
| `SMTP_USER` | SMTP username | None | Yes (if using) |
| `SMTP_PASSWORD` | SMTP password | None | Yes (if using) |

## Email Templates

The system includes pre-configured email templates for:

1. **Password Reset**: Secure password reset links with expiration
2. **Email Verification**: Verify user email addresses during registration
3. **Account Approval**: Notify users of account approval status
4. **Custom Notifications**: Send custom transactional emails

All templates are responsive and include both HTML and plain text versions.

## Testing Emails

### Development Testing

1. Start the development environment:
```bash
docker compose up
```

2. Run the email test script:
```bash
docker compose exec backend python /app/../test_email.py
```

3. View emails in Mailpit: http://localhost:8025

### Production Testing

1. Configure your production environment variables
2. Run the test script with production settings:
```bash
python test_email.py
```

3. Check your email inbox or Mailgun dashboard

## Monitoring & Debugging

### Mailgun Dashboard
- View delivery status
- Check bounce/complaint rates
- Review email logs
- Set up webhooks for events

### Mailpit (Development)
- View all captured emails
- Check HTML rendering
- Inspect headers and content
- Test without sending real emails

### Application Logs
Check the application logs for email-related events:
```bash
docker compose logs backend | grep -i email
```

## Email Features

### Bulk Email Sending
The system supports efficient bulk email sending with:
- Batch processing for Mailgun (up to 1000 recipients per request)
- Individual sending fallback
- Result tracking per recipient

### Email Validation
In production with Mailgun, the system can validate email addresses before sending:
- Syntax validation
- Domain verification
- Risk assessment
- Typo suggestions

### Automatic Fallback
The email service includes automatic fallback:
1. Try Mailgun API (if configured)
2. Fallback to SMTP (if Mailgun fails)
3. Log errors for debugging

## Security Best Practices

1. **Never commit credentials**: Use environment variables
2. **Use app-specific passwords**: For Gmail and similar providers
3. **Verify sender domains**: Improve deliverability
4. **Monitor bounce rates**: Maintain sender reputation
5. **Implement rate limiting**: Prevent abuse
6. **Use TLS/SSL**: Encrypt email transmission

## Troubleshooting

### Emails not sending in development
- Check if Mailpit is running: `docker compose ps mailpit`
- Verify environment variables are set correctly
- Check application logs for errors

### Emails not sending in production
- Verify Mailgun API key and domain
- Check domain verification status in Mailgun
- Review Mailgun logs for errors
- Ensure `ENVIRONMENT=production` is set
- Check firewall rules for outbound HTTPS

### Email content issues
- Verify `FRONTEND_URL` is set correctly for production
- Check template generation in logs
- Test with the provided test script

## Example Configuration Files

### Development (.env)
```env
ENVIRONMENT=development
# Mailpit is configured automatically in docker-compose.yml
```

### Production (.env)
```env
ENVIRONMENT=production
FRONTEND_URL=https://yourdomain.com

# Mailgun (Recommended)
MAILGUN_API_KEY=key-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MAILGUN_DOMAIN=mg.yourdomain.com
EMAILS_FROM_EMAIL=noreply@yourdomain.com
EMAILS_FROM_NAME=Chrono Scraper

# OR use SMTP
# SMTP_HOST=smtp.sendgrid.net
# SMTP_PORT=587
# SMTP_USER=apikey
# SMTP_PASSWORD=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```