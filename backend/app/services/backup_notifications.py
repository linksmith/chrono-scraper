"""
Backup notification service supporting multiple channels.

Provides comprehensive notification support for backup operations including:
- Email notifications (SMTP/Mailgun)
- Slack notifications
- Discord notifications
- Custom webhooks
- PagerDuty integration
- SMS notifications (Twilio)
"""

import json
import logging
import aiohttp
from datetime import datetime
from typing import Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass

from app.core.config import settings
from app.models.backup import BackupExecution


logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of backup notifications."""
    BACKUP_STARTED = "backup_started"
    BACKUP_COMPLETED = "backup_completed"
    BACKUP_FAILED = "backup_failed"
    BACKUP_WARNING = "backup_warning"
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_COMPLETED = "recovery_completed"
    RECOVERY_FAILED = "recovery_failed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    STORAGE_SPACE_WARNING = "storage_space_warning"
    STORAGE_SPACE_CRITICAL = "storage_space_critical"
    VERIFICATION_FAILED = "verification_failed"


class NotificationChannel(str, Enum):
    """Supported notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    SMS = "sms"


class NotificationPriority(str, Enum):
    """Notification priorities."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class NotificationMessage:
    """Structure for notification messages."""
    type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    details: Dict[str, Any] = None
    backup_id: Optional[str] = None
    recovery_id: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.details is None:
            self.details = {}


class BackupNotificationService:
    """Comprehensive backup notification service."""
    
    def __init__(self):
        self.enabled = getattr(settings, 'BACKUP_NOTIFICATIONS_ENABLED', False)
        self.notify_on_success = getattr(settings, 'BACKUP_NOTIFY_ON_SUCCESS', False)
        self.notify_on_failure = getattr(settings, 'BACKUP_NOTIFY_ON_FAILURE', True)
        self.notify_on_warning = getattr(settings, 'BACKUP_NOTIFY_ON_WARNING', True)
        
        # Initialize channels
        self.channels = {}
        self._initialize_channels()
    
    def _initialize_channels(self):
        """Initialize notification channels based on configuration."""
        # Email notifications
        if getattr(settings, 'BACKUP_EMAIL_ENABLED', False):
            self.channels[NotificationChannel.EMAIL] = {
                'enabled': True,
                'recipients': getattr(settings, 'BACKUP_EMAIL_RECIPIENTS', '').split(','),
                'from_email': getattr(settings, 'BACKUP_EMAIL_FROM', ''),
                'smtp_host': getattr(settings, 'BACKUP_EMAIL_SMTP_HOST', ''),
                'smtp_port': getattr(settings, 'BACKUP_EMAIL_SMTP_PORT', 587),
                'smtp_username': getattr(settings, 'BACKUP_EMAIL_SMTP_USERNAME', ''),
                'smtp_password': getattr(settings, 'BACKUP_EMAIL_SMTP_PASSWORD', ''),
                'use_tls': getattr(settings, 'BACKUP_EMAIL_SMTP_USE_TLS', True),
            }
        
        # Slack notifications
        if getattr(settings, 'BACKUP_SLACK_ENABLED', False):
            self.channels[NotificationChannel.SLACK] = {
                'enabled': True,
                'webhook_url': getattr(settings, 'BACKUP_SLACK_WEBHOOK_URL', ''),
                'channel': getattr(settings, 'BACKUP_SLACK_CHANNEL', '#backups'),
                'username': getattr(settings, 'BACKUP_SLACK_USERNAME', 'BackupBot'),
                'icon_emoji': getattr(settings, 'BACKUP_SLACK_ICON_EMOJI', ':floppy_disk:'),
            }
        
        # Discord notifications
        if getattr(settings, 'BACKUP_DISCORD_ENABLED', False):
            self.channels[NotificationChannel.DISCORD] = {
                'enabled': True,
                'webhook_url': getattr(settings, 'BACKUP_DISCORD_WEBHOOK_URL', ''),
            }
        
        # Custom webhook
        if getattr(settings, 'BACKUP_WEBHOOK_ENABLED', False):
            self.channels[NotificationChannel.WEBHOOK] = {
                'enabled': True,
                'url': getattr(settings, 'BACKUP_WEBHOOK_URL', ''),
                'secret': getattr(settings, 'BACKUP_WEBHOOK_SECRET', ''),
                'timeout': getattr(settings, 'BACKUP_WEBHOOK_TIMEOUT', 30),
            }
        
        # PagerDuty integration
        if getattr(settings, 'BACKUP_PAGERDUTY_ENABLED', False):
            self.channels[NotificationChannel.PAGERDUTY] = {
                'enabled': True,
                'integration_key': getattr(settings, 'BACKUP_PAGERDUTY_INTEGRATION_KEY', ''),
                'severity': getattr(settings, 'BACKUP_PAGERDUTY_SEVERITY', 'error'),
            }
    
    async def send_notification(self, notification: NotificationMessage) -> Dict[str, bool]:
        """Send notification through all enabled channels."""
        if not self.enabled:
            logger.debug("Backup notifications disabled")
            return {}
        
        # Filter based on notification type and settings
        if not self._should_send_notification(notification):
            logger.debug(f"Notification filtered: {notification.type}")
            return {}
        
        results = {}
        tasks = []
        
        for channel, config in self.channels.items():
            if config.get('enabled', False):
                task = self._send_channel_notification(channel, notification, config)
                tasks.append((channel, task))
        
        # Send notifications concurrently
        for channel, task in tasks:
            try:
                success = await task
                results[channel.value] = success
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {e}")
                results[channel.value] = False
        
        return results
    
    def _should_send_notification(self, notification: NotificationMessage) -> bool:
        """Determine if notification should be sent based on settings."""
        if notification.type == NotificationType.BACKUP_COMPLETED and not self.notify_on_success:
            return False
        
        if notification.type in [
            NotificationType.BACKUP_FAILED,
            NotificationType.RECOVERY_FAILED,
            NotificationType.VERIFICATION_FAILED
        ] and not self.notify_on_failure:
            return False
        
        if notification.type in [
            NotificationType.BACKUP_WARNING,
            NotificationType.STORAGE_SPACE_WARNING
        ] and not self.notify_on_warning:
            return False
        
        return True
    
    async def _send_channel_notification(self, channel: NotificationChannel, 
                                       notification: NotificationMessage,
                                       config: Dict[str, Any]) -> bool:
        """Send notification through specific channel."""
        try:
            if channel == NotificationChannel.EMAIL:
                return await self._send_email_notification(notification, config)
            elif channel == NotificationChannel.SLACK:
                return await self._send_slack_notification(notification, config)
            elif channel == NotificationChannel.DISCORD:
                return await self._send_discord_notification(notification, config)
            elif channel == NotificationChannel.WEBHOOK:
                return await self._send_webhook_notification(notification, config)
            elif channel == NotificationChannel.PAGERDUTY:
                return await self._send_pagerduty_notification(notification, config)
            else:
                logger.warning(f"Unsupported notification channel: {channel}")
                return False
        except Exception as e:
            logger.error(f"Error sending {channel} notification: {e}")
            return False
    
    async def _send_email_notification(self, notification: NotificationMessage,
                                     config: Dict[str, Any]) -> bool:
        """Send email notification."""
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        if not config.get('recipients'):
            logger.warning("No email recipients configured")
            return False
        
        # Create email content
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[Chrono Scraper] {notification.title}"
        msg['From'] = config['from_email']
        msg['To'] = ', '.join(config['recipients'])
        
        # Create HTML and text versions
        text_body = self._create_email_text(notification)
        html_body = self._create_email_html(notification)
        
        text_part = MIMEText(text_body, 'plain')
        html_part = MIMEText(html_body, 'html')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        # Send email
        try:
            smtp = aiosmtplib.SMTP(
                hostname=config['smtp_host'],
                port=config['smtp_port'],
                use_tls=config.get('use_tls', True)
            )
            
            await smtp.connect()
            
            if config.get('smtp_username') and config.get('smtp_password'):
                await smtp.login(config['smtp_username'], config['smtp_password'])
            
            await smtp.send_message(msg)
            await smtp.quit()
            
            logger.info(f"Email notification sent: {notification.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False
    
    async def _send_slack_notification(self, notification: NotificationMessage,
                                     config: Dict[str, Any]) -> bool:
        """Send Slack notification."""
        webhook_url = config.get('webhook_url')
        if not webhook_url:
            logger.warning("Slack webhook URL not configured")
            return False
        
        # Create Slack payload
        payload = {
            "channel": config.get('channel', '#backups'),
            "username": config.get('username', 'BackupBot'),
            "icon_emoji": config.get('icon_emoji', ':floppy_disk:'),
            "attachments": [
                {
                    "color": self._get_notification_color(notification),
                    "title": notification.title,
                    "text": notification.message,
                    "fields": [
                        {
                            "title": "Type",
                            "value": notification.type.value.replace('_', ' ').title(),
                            "short": True
                        },
                        {
                            "title": "Priority",
                            "value": notification.priority.value.title(),
                            "short": True
                        },
                        {
                            "title": "Timestamp",
                            "value": notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'),
                            "short": True
                        }
                    ],
                    "footer": "Chrono Scraper Backup System",
                    "ts": int(notification.timestamp.timestamp())
                }
            ]
        }
        
        # Add backup/recovery ID if available
        if notification.backup_id:
            payload["attachments"][0]["fields"].append({
                "title": "Backup ID",
                "value": notification.backup_id,
                "short": True
            })
        
        if notification.recovery_id:
            payload["attachments"][0]["fields"].append({
                "title": "Recovery ID",
                "value": notification.recovery_id,
                "short": True
            })
        
        # Send to Slack
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Slack notification sent: {notification.title}")
                        return True
                    else:
                        logger.error(f"Slack notification failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False
    
    async def _send_discord_notification(self, notification: NotificationMessage,
                                       config: Dict[str, Any]) -> bool:
        """Send Discord notification."""
        webhook_url = config.get('webhook_url')
        if not webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False
        
        # Create Discord embed
        embed = {
            "title": notification.title,
            "description": notification.message,
            "color": self._get_discord_color(notification),
            "timestamp": notification.timestamp.isoformat(),
            "footer": {
                "text": "Chrono Scraper Backup System"
            },
            "fields": [
                {
                    "name": "Type",
                    "value": notification.type.value.replace('_', ' ').title(),
                    "inline": True
                },
                {
                    "name": "Priority",
                    "value": notification.priority.value.title(),
                    "inline": True
                }
            ]
        }
        
        # Add backup/recovery ID if available
        if notification.backup_id:
            embed["fields"].append({
                "name": "Backup ID",
                "value": notification.backup_id,
                "inline": True
            })
        
        if notification.recovery_id:
            embed["fields"].append({
                "name": "Recovery ID",
                "value": notification.recovery_id,
                "inline": True
            })
        
        payload = {
            "embeds": [embed]
        }
        
        # Send to Discord
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 204:
                        logger.info(f"Discord notification sent: {notification.title}")
                        return True
                    else:
                        logger.error(f"Discord notification failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False
    
    async def _send_webhook_notification(self, notification: NotificationMessage,
                                       config: Dict[str, Any]) -> bool:
        """Send custom webhook notification."""
        webhook_url = config.get('url')
        if not webhook_url:
            logger.warning("Webhook URL not configured")
            return False
        
        # Create webhook payload
        payload = {
            "type": notification.type.value,
            "priority": notification.priority.value,
            "title": notification.title,
            "message": notification.message,
            "timestamp": notification.timestamp.isoformat(),
            "backup_id": notification.backup_id,
            "recovery_id": notification.recovery_id,
            "details": notification.details
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Chrono-Scraper-Backup/1.0"
        }
        
        # Add webhook secret if configured
        webhook_secret = config.get('secret')
        if webhook_secret:
            import hmac
            import hashlib
            
            payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
            signature = hmac.new(
                webhook_secret.encode('utf-8'),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            headers['X-Backup-Signature'] = f"sha256={signature}"
        
        # Send webhook
        try:
            timeout = aiohttp.ClientTimeout(total=config.get('timeout', 30))
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook notification sent: {notification.title}")
                        return True
                    else:
                        logger.error(f"Webhook notification failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send webhook notification: {e}")
            return False
    
    async def _send_pagerduty_notification(self, notification: NotificationMessage,
                                         config: Dict[str, Any]) -> bool:
        """Send PagerDuty notification."""
        integration_key = config.get('integration_key')
        if not integration_key:
            logger.warning("PagerDuty integration key not configured")
            return False
        
        # Only send critical notifications to PagerDuty
        if notification.priority != NotificationPriority.CRITICAL:
            return True
        
        # Create PagerDuty event
        event = {
            "routing_key": integration_key,
            "event_action": "trigger",
            "payload": {
                "summary": notification.title,
                "source": "chrono-scraper-backup",
                "severity": config.get('severity', 'error'),
                "component": "backup-system",
                "group": "infrastructure",
                "class": notification.type.value,
                "custom_details": {
                    "message": notification.message,
                    "backup_id": notification.backup_id,
                    "recovery_id": notification.recovery_id,
                    "timestamp": notification.timestamp.isoformat(),
                    "details": notification.details
                }
            }
        }
        
        # Send to PagerDuty
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=event,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 202:
                        logger.info(f"PagerDuty notification sent: {notification.title}")
                        return True
                    else:
                        logger.error(f"PagerDuty notification failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send PagerDuty notification: {e}")
            return False
    
    def _get_notification_color(self, notification: NotificationMessage) -> str:
        """Get color for Slack notifications."""
        if notification.priority == NotificationPriority.CRITICAL:
            return "danger"
        elif notification.priority == NotificationPriority.HIGH:
            return "warning"
        elif notification.type in [
            NotificationType.BACKUP_COMPLETED,
            NotificationType.RECOVERY_COMPLETED
        ]:
            return "good"
        else:
            return "#439FE0"  # Default blue
    
    def _get_discord_color(self, notification: NotificationMessage) -> int:
        """Get color for Discord embeds."""
        if notification.priority == NotificationPriority.CRITICAL:
            return 0xFF0000  # Red
        elif notification.priority == NotificationPriority.HIGH:
            return 0xFFA500  # Orange
        elif notification.type in [
            NotificationType.BACKUP_COMPLETED,
            NotificationType.RECOVERY_COMPLETED
        ]:
            return 0x00FF00  # Green
        else:
            return 0x0099FF  # Blue
    
    def _create_email_text(self, notification: NotificationMessage) -> str:
        """Create plain text email content."""
        lines = [
            "Chrono Scraper Backup System Notification",
            "=" * 50,
            "",
            f"Title: {notification.title}",
            f"Type: {notification.type.value.replace('_', ' ').title()}",
            f"Priority: {notification.priority.value.title()}",
            f"Timestamp: {notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "Message:",
            f"{notification.message}",
        ]
        
        if notification.backup_id:
            lines.extend(["", f"Backup ID: {notification.backup_id}"])
        
        if notification.recovery_id:
            lines.extend(["", f"Recovery ID: {notification.recovery_id}"])
        
        if notification.details:
            lines.extend(["", "Additional Details:"])
            for key, value in notification.details.items():
                lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)
    
    def _create_email_html(self, notification: NotificationMessage) -> str:
        """Create HTML email content."""
        priority_color = {
            NotificationPriority.LOW: "#28a745",
            NotificationPriority.NORMAL: "#007bff",
            NotificationPriority.HIGH: "#ffc107",
            NotificationPriority.CRITICAL: "#dc3545"
        }
        
        color = priority_color.get(notification.priority, "#007bff")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8f9fa;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div style="background-color: {color}; color: white; padding: 20px;">
                    <h1 style="margin: 0; font-size: 24px;">Chrono Scraper Backup System</h1>
                    <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">Notification</p>
                </div>
                
                <div style="padding: 20px;">
                    <h2 style="color: #333; margin-top: 0;">{notification.title}</h2>
                    <p style="color: #666; font-size: 16px; line-height: 1.5;">{notification.message}</p>
                    
                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Type:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{notification.type.value.replace('_', ' ').title()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Priority:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee; color: {color}; font-weight: bold;">{notification.priority.value.title()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Timestamp:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;">{notification.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                        </tr>
        """
        
        if notification.backup_id:
            html += f"""
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Backup ID:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee; font-family: monospace;">{notification.backup_id}</td>
                        </tr>
            """
        
        if notification.recovery_id:
            html += f"""
                        <tr>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Recovery ID:</strong></td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #eee; font-family: monospace;">{notification.recovery_id}</td>
                        </tr>
            """
        
        html += """
                    </table>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 15px 20px; border-top: 1px solid #dee2e6;">
                    <p style="margin: 0; color: #6c757d; font-size: 12px;">
                        This is an automated notification from the Chrono Scraper backup system.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    # Convenience methods for common notifications
    async def notify_backup_started(self, backup: BackupExecution):
        """Send backup started notification."""
        notification = NotificationMessage(
            type=NotificationType.BACKUP_STARTED,
            priority=NotificationPriority.NORMAL,
            title=f"Backup Started: {backup.backup_id}",
            message=f"Backup operation has started for {backup.backup_type.value} backup.",
            backup_id=backup.backup_id,
            details={
                "backup_type": backup.backup_type.value,
                "storage_backend": backup.storage_backend_id,
                "started_at": backup.started_at.isoformat()
            }
        )
        
        return await self.send_notification(notification)
    
    async def notify_backup_completed(self, backup: BackupExecution):
        """Send backup completed notification."""
        duration = None
        if backup.completed_at and backup.started_at:
            duration = str(backup.completed_at - backup.started_at)
        
        notification = NotificationMessage(
            type=NotificationType.BACKUP_COMPLETED,
            priority=NotificationPriority.NORMAL,
            title=f"Backup Completed: {backup.backup_id}",
            message=f"Backup operation completed successfully. Size: {backup.size_bytes / (1024**3):.2f} GB",
            backup_id=backup.backup_id,
            details={
                "backup_type": backup.backup_type.value,
                "size_bytes": backup.size_bytes,
                "compressed_size_bytes": backup.compressed_size_bytes,
                "compression_ratio": backup.compression_ratio,
                "duration": duration,
                "storage_location": backup.storage_location,
                "components": backup.included_components
            }
        )
        
        return await self.send_notification(notification)
    
    async def notify_backup_failed(self, backup: BackupExecution):
        """Send backup failed notification."""
        notification = NotificationMessage(
            type=NotificationType.BACKUP_FAILED,
            priority=NotificationPriority.HIGH,
            title=f"Backup Failed: {backup.backup_id}",
            message=f"Backup operation failed: {backup.error_message}",
            backup_id=backup.backup_id,
            details={
                "backup_type": backup.backup_type.value,
                "error_message": backup.error_message,
                "started_at": backup.started_at.isoformat(),
                "failed_at": backup.completed_at.isoformat() if backup.completed_at else None
            }
        )
        
        return await self.send_notification(notification)


# Global notification service instance
notification_service = BackupNotificationService()