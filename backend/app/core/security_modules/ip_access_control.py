"""
IP-based access control and whitelisting for admin panel
Implements geo-location restrictions, VPN/proxy detection, and dynamic IP blocking
"""
import ipaddress
from typing import Optional, List, Dict, Set, Tuple
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status
import aiohttp
import json
from redis.asyncio import Redis

from app.core.config import settings
from app.models.audit_log import create_audit_log, AuditCategory, SeverityLevel, AuditActions


class IPAccessControl:
    """
    Advanced IP-based access control system with:
    - IP whitelisting/blacklisting
    - Geo-location based restrictions
    - VPN/Proxy/Tor detection
    - Dynamic IP blocking based on suspicious activity
    - Rate limiting per IP
    """
    
    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client
        self.whitelist = self._parse_ip_list(settings.ADMIN_IP_WHITELIST)
        self.blacklist = self._parse_ip_list(settings.ADMIN_IP_BLACKLIST + settings.BLOCKED_IPS)
        self.trusted_proxies = self._parse_ip_list(settings.TRUSTED_PROXIES)
        self.vpn_ranges = self._parse_ip_list(settings.ADMIN_ALLOWED_VPN_RANGES)
        
        # Cache for IP reputation checks
        self.ip_cache_ttl = 3600  # 1 hour cache
        self.suspicious_activity_cache: Dict[str, int] = {}
        
    def _parse_ip_list(self, ip_list: List[str]) -> Set[ipaddress.IPv4Network]:
        """Parse IP addresses and CIDR ranges into network objects"""
        networks = set()
        for ip_str in ip_list:
            try:
                # Handle single IPs and CIDR notation
                if '/' in ip_str:
                    networks.add(ipaddress.IPv4Network(ip_str))
                else:
                    networks.add(ipaddress.IPv4Network(f"{ip_str}/32"))
            except (ipaddress.AddressValueError, ValueError):
                print(f"Invalid IP address or CIDR: {ip_str}")
        return networks
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP considering proxy headers"""
        # Check for proxy headers in order of preference
        headers_to_check = [
            'CF-Connecting-IP',  # Cloudflare
            'X-Real-IP',
            'X-Forwarded-For',
            'X-Client-IP',
            'X-Cluster-Client-IP',
            'Forwarded'
        ]
        
        for header in headers_to_check:
            ip = request.headers.get(header)
            if ip:
                # Handle X-Forwarded-For with multiple IPs
                if header == 'X-Forwarded-For':
                    # Get first IP (original client)
                    ip = ip.split(',')[0].strip()
                    
                    # Validate it's not from a trusted proxy
                    if self._is_trusted_proxy(ip):
                        continue
                        
                return ip
        
        # Fallback to direct connection IP
        return request.client.host if request.client else "unknown"
    
    def _is_trusted_proxy(self, ip: str) -> bool:
        """Check if IP is from a trusted proxy"""
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            return any(ip_addr in network for network in self.trusted_proxies)
        except ipaddress.AddressValueError:
            return False
    
    async def check_admin_access(self, request: Request, user_email: Optional[str] = None) -> Tuple[bool, str]:
        """
        Comprehensive admin access check
        Returns: (allowed, reason)
        """
        client_ip = self._get_client_ip(request)
        
        # Check explicit blacklist first
        if await self._is_blacklisted(client_ip):
            await self._log_blocked_access(client_ip, user_email, "IP blacklisted")
            return False, "Access denied: IP address is blacklisted"
        
        # Check if IP has been dynamically blocked
        if await self._is_dynamically_blocked(client_ip):
            await self._log_blocked_access(client_ip, user_email, "Dynamically blocked")
            return False, "Access denied: IP temporarily blocked due to suspicious activity"
        
        # If whitelist is configured, check it
        if settings.ADMIN_IP_WHITELIST:
            if not self._is_whitelisted(client_ip):
                await self._log_blocked_access(client_ip, user_email, "Not in whitelist")
                return False, "Access denied: IP not in admin whitelist"
        
        # Check geo-location restrictions
        if settings.ENABLE_GEO_BLOCKING:
            country_code = await self._get_country_code(client_ip)
            if country_code not in settings.ALLOWED_COUNTRIES:
                await self._log_blocked_access(client_ip, user_email, f"Geo-blocked: {country_code}")
                return False, f"Access denied: Country {country_code} not allowed"
        
        # Check VPN/Proxy/Tor detection
        if await self._is_suspicious_connection(client_ip):
            threat_type = await self._get_threat_type(client_ip)
            
            if threat_type == "tor" and settings.BLOCK_TOR_CONNECTIONS:
                await self._log_blocked_access(client_ip, user_email, "Tor exit node")
                return False, "Access denied: Tor connections not allowed"
            
            if threat_type == "vpn" and settings.BLOCK_VPN_CONNECTIONS:
                # Check if it's an allowed VPN range
                if not self._is_allowed_vpn(client_ip):
                    await self._log_blocked_access(client_ip, user_email, "VPN detected")
                    return False, "Access denied: VPN connections not allowed"
            
            if threat_type == "proxy" and settings.BLOCK_PROXY_CONNECTIONS:
                await self._log_blocked_access(client_ip, user_email, "Proxy detected")
                return False, "Access denied: Proxy connections not allowed"
        
        # Check for brute force attempts
        if await self._check_brute_force(client_ip):
            await self._log_blocked_access(client_ip, user_email, "Brute force detected")
            await self._add_to_dynamic_blocklist(client_ip, 3600)  # Block for 1 hour
            return False, "Access denied: Too many failed attempts"
        
        # All checks passed
        await self._log_allowed_access(client_ip, user_email)
        return True, "Access allowed"
    
    def _is_whitelisted(self, ip: str) -> bool:
        """Check if IP is in whitelist"""
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            return any(ip_addr in network for network in self.whitelist)
        except ipaddress.AddressValueError:
            return False
    
    async def _is_blacklisted(self, ip: str) -> bool:
        """Check if IP is in blacklist (static or dynamic)"""
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            # Check static blacklist
            if any(ip_addr in network for network in self.blacklist):
                return True
            
            # Check dynamic blacklist in Redis
            if self.redis_client:
                key = f"security:blacklist:{ip}"
                return await self.redis_client.exists(key) > 0
                
        except ipaddress.AddressValueError:
            return True  # Invalid IPs are considered blacklisted
        
        return False
    
    async def _is_dynamically_blocked(self, ip: str) -> bool:
        """Check if IP has been dynamically blocked"""
        if not self.redis_client:
            return False
        
        key = f"security:dynamic_block:{ip}"
        return await self.redis_client.exists(key) > 0
    
    async def _add_to_dynamic_blocklist(self, ip: str, duration_seconds: int):
        """Add IP to dynamic blocklist for specified duration"""
        if not self.redis_client:
            return
        
        key = f"security:dynamic_block:{ip}"
        await self.redis_client.setex(key, duration_seconds, "blocked")
        
        # Also add to permanent blacklist if threshold exceeded
        count_key = f"security:block_count:{ip}"
        count = await self.redis_client.incr(count_key)
        await self.redis_client.expire(count_key, 86400 * 30)  # 30 days
        
        if count >= 3:  # After 3 blocks, add to permanent blacklist
            blacklist_key = f"security:blacklist:{ip}"
            await self.redis_client.set(blacklist_key, json.dumps({
                "added_at": datetime.now(timezone.utc).isoformat(),
                "reason": "Multiple security violations",
                "permanent": True
            }))
    
    def _is_allowed_vpn(self, ip: str) -> bool:
        """Check if IP is in allowed VPN ranges"""
        if not settings.ADMIN_ALLOWED_VPN_RANGES:
            return False
        
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            return any(ip_addr in network for network in self.vpn_ranges)
        except ipaddress.AddressValueError:
            return False
    
    async def _get_country_code(self, ip: str) -> Optional[str]:
        """Get country code for IP using GeoIP service"""
        if not self.redis_client:
            return None
        
        # Check cache first
        cache_key = f"geoip:country:{ip}"
        cached = await self.redis_client.get(cache_key)
        if cached:
            return cached.decode()
        
        try:
            # Use ip-api.com free service (limited to 45 requests per minute)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://ip-api.com/json/{ip}?fields=countryCode,proxy,hosting",
                    timeout=5
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        country_code = data.get('countryCode', 'XX')
                        
                        # Cache the result
                        await self.redis_client.setex(cache_key, self.ip_cache_ttl, country_code)
                        
                        # Also cache proxy/hosting info
                        if data.get('proxy') or data.get('hosting'):
                            threat_key = f"threat:proxy:{ip}"
                            await self.redis_client.setex(threat_key, self.ip_cache_ttl, "1")
                        
                        return country_code
        except Exception as e:
            print(f"GeoIP lookup failed for {ip}: {e}")
        
        return None
    
    async def _is_suspicious_connection(self, ip: str) -> bool:
        """Check if connection is from VPN/Proxy/Tor"""
        if not settings.ENABLE_VPN_DETECTION and not settings.ENABLE_TOR_DETECTION and not settings.ENABLE_PROXY_DETECTION:
            return False
        
        # Check cache
        if self.redis_client:
            threat_key = f"threat:check:{ip}"
            cached = await self.redis_client.get(threat_key)
            if cached:
                return cached.decode() == "1"
        
        # Check known Tor exit nodes
        if settings.ENABLE_TOR_DETECTION and await self._is_tor_exit_node(ip):
            return True
        
        # Check VPN/Proxy databases
        if (settings.ENABLE_VPN_DETECTION or settings.ENABLE_PROXY_DETECTION) and await self._check_vpn_proxy_database(ip):
            return True
        
        return False
    
    async def _get_threat_type(self, ip: str) -> Optional[str]:
        """Determine the type of threat (tor, vpn, proxy)"""
        if await self._is_tor_exit_node(ip):
            return "tor"
        
        # Check cached threat type
        if self.redis_client:
            vpn_key = f"threat:vpn:{ip}"
            proxy_key = f"threat:proxy:{ip}"
            
            if await self.redis_client.exists(vpn_key):
                return "vpn"
            if await self.redis_client.exists(proxy_key):
                return "proxy"
        
        return None
    
    async def _is_tor_exit_node(self, ip: str) -> bool:
        """Check if IP is a known Tor exit node"""
        if not self.redis_client:
            return False
        
        # Check cache
        tor_key = f"threat:tor:{ip}"
        cached = await self.redis_client.get(tor_key)
        if cached is not None:
            return cached.decode() == "1"
        
        try:
            # Check against Tor exit node list
            # In production, you would fetch this from https://check.torproject.org/exit-addresses
            # For now, we'll check against known patterns
            
            # Reverse IP for DNS lookup
            octets = ip.split('.')
            reversed_ip = '.'.join(reversed(octets))
            
            # DNS-based Tor exit node check
            import socket
            try:
                # Query format: reversed_ip.dnsel.torproject.org
                socket.gethostbyname(f"{reversed_ip}.dnsel.torproject.org")
                # If it resolves, it's a Tor exit node
                await self.redis_client.setex(tor_key, self.ip_cache_ttl, "1")
                return True
            except socket.gaierror:
                # Not a Tor exit node
                await self.redis_client.setex(tor_key, self.ip_cache_ttl, "0")
                return False
                
        except Exception as e:
            print(f"Tor check failed for {ip}: {e}")
        
        return False
    
    async def _check_vpn_proxy_database(self, ip: str) -> bool:
        """Check IP against VPN/Proxy databases"""
        # In production, integrate with services like:
        # - IPQualityScore
        # - ProxyCheck.io
        # - VPNBlocker
        # - IP2Proxy
        
        # For now, check against known VPN provider ranges
        known_vpn_ranges = [
            "104.200.0.0/13",  # Example VPN range
            "45.32.0.0/11",    # Example hosting provider often used for VPNs
        ]
        
        try:
            ip_addr = ipaddress.IPv4Address(ip)
            for range_str in known_vpn_ranges:
                if ip_addr in ipaddress.IPv4Network(range_str):
                    if self.redis_client:
                        vpn_key = f"threat:vpn:{ip}"
                        await self.redis_client.setex(vpn_key, self.ip_cache_ttl, "1")
                    return True
        except Exception:
            pass
        
        return False
    
    async def _check_brute_force(self, ip: str) -> bool:
        """Check for brute force attempts from IP"""
        if not self.redis_client:
            return False
        
        # Check failed login attempts
        key = f"security:failed_logins:{ip}"
        count = await self.redis_client.get(key)
        
        if count and int(count) >= settings.ADMIN_MAX_LOGIN_ATTEMPTS:
            return True
        
        # Check general suspicious activity
        suspicious_key = f"security:suspicious:{ip}"
        suspicious_count = await self.redis_client.get(suspicious_key)
        
        if suspicious_count and int(suspicious_count) >= settings.SUSPICIOUS_IP_THRESHOLD:
            return True
        
        return False
    
    async def record_failed_login(self, ip: str):
        """Record a failed login attempt from IP"""
        if not self.redis_client:
            return
        
        key = f"security:failed_logins:{ip}"
        count = await self.redis_client.incr(key)
        await self.redis_client.expire(key, 3600)  # Reset after 1 hour
        
        # Auto-block if threshold exceeded
        if count >= settings.ADMIN_MAX_LOGIN_ATTEMPTS and settings.AUTO_BLOCK_THREATS:
            await self._add_to_dynamic_blocklist(
                ip, 
                settings.ADMIN_LOCKOUT_DURATION_MINUTES * 60
            )
    
    async def record_suspicious_activity(self, ip: str, activity_type: str):
        """Record suspicious activity from IP"""
        if not self.redis_client:
            return
        
        key = f"security:suspicious:{ip}"
        count = await self.redis_client.incr(key)
        await self.redis_client.expire(key, 86400)  # Reset after 24 hours
        
        # Log the activity
        detail_key = f"security:suspicious:detail:{ip}:{datetime.now(timezone.utc).timestamp()}"
        await self.redis_client.setex(detail_key, 86400, activity_type)
        
        # Auto-block if threshold exceeded
        if count >= settings.SUSPICIOUS_IP_THRESHOLD and settings.AUTO_BLOCK_SUSPICIOUS_IPS:
            await self._add_to_dynamic_blocklist(
                ip,
                settings.THREAT_BLOCK_DURATION_HOURS * 3600
            )
    
    async def _log_blocked_access(self, ip: str, user_email: Optional[str], reason: str):
        """Log blocked admin access attempt"""
        print(f"SECURITY: Admin access blocked - IP: {ip}, User: {user_email}, Reason: {reason}")
        
        # Record in audit log
        create_audit_log(
            action=AuditActions.UNAUTHORIZED_ACCESS,
            resource_type="admin_panel",
            category=AuditCategory.SECURITY_EVENT,
            severity=SeverityLevel.HIGH,
            ip_address=ip,
            details={
                "reason": reason,
                "user_email": user_email,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            success=False,
            error_message=reason
        )
        
        # In production, save to database
        # await save_audit_log(audit_entry)
    
    async def _log_allowed_access(self, ip: str, user_email: Optional[str]):
        """Log allowed admin access"""
        print(f"SECURITY: Admin access allowed - IP: {ip}, User: {user_email}")
    
    async def get_ip_reputation(self, ip: str) -> Dict[str, any]:
        """Get comprehensive IP reputation data"""
        reputation = {
            "ip": ip,
            "is_whitelisted": self._is_whitelisted(ip),
            "is_blacklisted": await self._is_blacklisted(ip),
            "is_dynamically_blocked": await self._is_dynamically_blocked(ip),
            "country_code": await self._get_country_code(ip),
            "is_tor": False,
            "is_vpn": False,
            "is_proxy": False,
            "threat_score": 0,
            "failed_login_count": 0,
            "suspicious_activity_count": 0
        }
        
        if self.redis_client:
            # Get threat type
            threat_type = await self._get_threat_type(ip)
            if threat_type:
                reputation[f"is_{threat_type}"] = True
                reputation["threat_score"] += 50
            
            # Get failed login count
            login_key = f"security:failed_logins:{ip}"
            login_count = await self.redis_client.get(login_key)
            if login_count:
                reputation["failed_login_count"] = int(login_count)
                reputation["threat_score"] += int(login_count) * 10
            
            # Get suspicious activity count
            suspicious_key = f"security:suspicious:{ip}"
            suspicious_count = await self.redis_client.get(suspicious_key)
            if suspicious_count:
                reputation["suspicious_activity_count"] = int(suspicious_count)
                reputation["threat_score"] += int(suspicious_count) * 5
        
        # Cap threat score at 100
        reputation["threat_score"] = min(reputation["threat_score"], 100)
        
        return reputation


class AdminIPWhitelistMiddleware:
    """FastAPI middleware for IP-based admin access control"""
    
    def __init__(self, redis_client: Optional[Redis] = None):
        self.access_control = IPAccessControl(redis_client)
    
    async def __call__(self, request: Request, call_next):
        """Check IP access for admin routes"""
        # Only check admin routes
        if request.url.path.startswith("/admin") or request.url.path.startswith("/api/v1/admin"):
            # Get user email from session if available
            user_email = None
            if hasattr(request.state, "user"):
                user_email = getattr(request.state.user, "email", None)
            
            # Check access
            allowed, reason = await self.access_control.check_admin_access(request, user_email)
            
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=reason
                )
        
        response = await call_next(request)
        return response