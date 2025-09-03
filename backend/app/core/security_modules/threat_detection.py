"""
Advanced threat detection system with real-time monitoring and automated response
Implements pattern recognition, anomaly detection, and threat intelligence
"""
import re
import json
import time
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from dataclasses import asdict
from collections import defaultdict, deque
from redis.asyncio import Redis
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.models.audit_log import create_audit_log, AuditCategory, SeverityLevel, AuditActions
from app.core.security_modules.types import ThreatType, ThreatSeverity, ThreatEvent


class ThreatDetectionEngine:
    """
    Advanced threat detection engine with multiple detection algorithms:
    - Pattern-based detection (SQL injection, XSS, etc.)
    - Statistical anomaly detection
    - Behavioral analysis
    - Machine learning-based classification (future enhancement)
    """
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        
        # Pattern-based detection rules
        self.sql_injection_patterns = [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"('|(\\')|(;)|(\-\-)|(\|)|(\*|\%|\?))",
            r"(\b(OR|AND)\b\s+[\w\s]*\s*=\s*[\w\s]*)",
            r"(\b(CONCAT|SUBSTRING|LENGTH|ASCII|CHAR)\b\s*\()",
            r"(WAITFOR\s+DELAY|BENCHMARK\s*\()",
            r"(\b(INFORMATION_SCHEMA|SYSOBJECTS|SYSCOLUMNS)\b)",
            r"(@@\w+|sp_\w+)",
            r"(\bUNION\b.*(SELECT|ALL))",
            r"(\b(LOAD_FILE|INTO\s+OUTFILE|DUMPFILE)\b)"
        ]
        
        self.xss_patterns = [
            r"<\s*script[^>]*>.*?</\s*script\s*>",
            r"javascript\s*:",
            r"on\w+\s*=",
            r"<\s*iframe[^>]*>.*?</\s*iframe\s*>",
            r"<\s*object[^>]*>.*?</\s*object\s*>",
            r"<\s*embed[^>]*>.*?</\s*embed\s*>",
            r"<\s*link[^>]*>",
            r"<\s*meta[^>]*>",
            r"expression\s*\(",
            r"@import",
            r"alert\s*\(",
            r"confirm\s*\(",
            r"prompt\s*\(",
            r"document\.(cookie|write|writeln)",
            r"window\.(location|open)",
            r"eval\s*\("
        ]
        
        self.path_traversal_patterns = [
            r"(\.\./){2,}",
            r"(\.\.\\/){2,}",
            r"(\.\.\\){2,}",
            r"(%2e%2e[/\\]){2,}",
            r"(\.\.%2f){2,}",
            r"(\.\.%5c){2,}",
            r"/etc/passwd",
            r"/etc/shadow",
            r"/proc/self/environ",
            r"\\windows\\system32",
            r"\\boot\.ini"
        ]
        
        self.command_injection_patterns = [
            r";.*?(rm|del|rmdir|format|fdisk)",
            r"\|.*?(cat|type|more|less|head|tail)",
            r"`.*?(whoami|id|uname|pwd|ls|dir)",
            r"\$\(.*?(curl|wget|nc|netcat|telnet)",
            r"&&.*?(ping|nslookup|dig|host)",
            r"exec\s*\(",
            r"system\s*\(",
            r"shell_exec\s*\(",
            r"passthru\s*\(",
            r"eval\s*\(",
            r"assert\s*\("
        ]
        
        # Behavioral analysis thresholds
        self.request_rate_thresholds = {
            "normal": 60,      # requests per minute
            "suspicious": 300,  # requests per minute
            "malicious": 600   # requests per minute
        }
        
        self.error_rate_thresholds = {
            "normal": 0.05,    # 5% error rate
            "suspicious": 0.15, # 15% error rate
            "malicious": 0.3   # 30% error rate
        }
        
        # Compile patterns for performance
        self._compiled_patterns = {
            "sql_injection": [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in self.sql_injection_patterns],
            "xss": [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in self.xss_patterns],
            "path_traversal": [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in self.path_traversal_patterns],
            "command_injection": [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in self.command_injection_patterns]
        }
        
        # Statistical tracking for anomaly detection
        self.baseline_metrics = {}
        self.current_metrics = defaultdict(deque)
        self.window_size = 100  # Number of samples for rolling statistics
    
    async def analyze_request(self, request: Request, response_status: int, response_time: float) -> List[ThreatEvent]:
        """
        Analyze request for threats using multiple detection methods
        Returns list of detected threats
        """
        threats = []
        
        # Extract request data
        request_data = await self._extract_request_data(request)
        client_ip = self._get_client_ip(request)
        user_id = getattr(request.state, "user_id", None) if hasattr(request.state, "user") else None
        
        # Pattern-based detection
        pattern_threats = await self._detect_pattern_based_threats(request_data, client_ip, user_id)
        threats.extend(pattern_threats)
        
        # Behavioral analysis
        behavioral_threats = await self._detect_behavioral_anomalies(
            client_ip, user_id, request_data, response_status, response_time
        )
        threats.extend(behavioral_threats)
        
        # Statistical anomaly detection
        statistical_threats = await self._detect_statistical_anomalies(client_ip, user_id, request_data)
        threats.extend(statistical_threats)
        
        # Account-based threat detection
        if user_id:
            account_threats = await self._detect_account_threats(user_id, request_data, client_ip)
            threats.extend(account_threats)
        
        # Store threats for analysis
        for threat in threats:
            await self._store_threat_event(threat)
        
        return threats
    
    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """Extract relevant data from request for analysis"""
        data = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
            "user_agent": request.headers.get("User-Agent", ""),
            "referer": request.headers.get("Referer", ""),
            "content_type": request.headers.get("Content-Type", ""),
            "content_length": request.headers.get("Content-Length", 0),
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Try to extract body data safely
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                content_type = data["content_type"].lower()
                if "application/json" in content_type:
                    # For JSON data
                    body = await request.body()
                    if body:
                        data["body"] = body.decode("utf-8", errors="ignore")[:1000]  # Limit size
                elif "application/x-www-form-urlencoded" in content_type:
                    # For form data
                    form = await request.form()
                    data["form_data"] = dict(form)
        except Exception:
            # If we can't read the body, that's fine - request has been consumed
            pass
        
        return data
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    async def _detect_pattern_based_threats(self, request_data: Dict, client_ip: str, user_id: Optional[int]) -> List[ThreatEvent]:
        """Detect threats using pattern matching"""
        threats = []
        
        # Combine all text data for pattern matching
        text_data = []
        text_data.append(request_data.get("path", ""))
        text_data.extend(str(v) for v in request_data.get("query_params", {}).values())
        text_data.extend(str(v) for v in request_data.get("headers", {}).values())
        if "body" in request_data:
            text_data.append(request_data["body"])
        if "form_data" in request_data:
            text_data.extend(str(v) for v in request_data["form_data"].values())
        
        combined_text = " ".join(text_data).lower()
        
        # SQL Injection Detection
        sql_matches = []
        for pattern in self._compiled_patterns["sql_injection"]:
            matches = pattern.findall(combined_text)
            sql_matches.extend(matches)
        
        if sql_matches:
            confidence = min(0.9, len(sql_matches) * 0.3)
            threats.append(ThreatEvent(
                threat_type=ThreatType.SQL_INJECTION,
                severity=ThreatSeverity.HIGH,
                source_ip=client_ip,
                user_id=user_id,
                timestamp=datetime.now(timezone.utc),
                details={
                    "matches": sql_matches[:5],  # Limit for storage
                    "pattern_count": len(sql_matches)
                },
                confidence_score=confidence,
                request_data=request_data
            ))
        
        # XSS Detection
        xss_matches = []
        for pattern in self._compiled_patterns["xss"]:
            matches = pattern.findall(combined_text)
            xss_matches.extend(matches)
        
        if xss_matches:
            confidence = min(0.85, len(xss_matches) * 0.25)
            threats.append(ThreatEvent(
                threat_type=ThreatType.XSS_ATTEMPT,
                severity=ThreatSeverity.MEDIUM,
                source_ip=client_ip,
                user_id=user_id,
                timestamp=datetime.now(timezone.utc),
                details={
                    "matches": xss_matches[:5],
                    "pattern_count": len(xss_matches)
                },
                confidence_score=confidence,
                request_data=request_data
            ))
        
        # Path Traversal Detection
        traversal_matches = []
        for pattern in self._compiled_patterns["path_traversal"]:
            matches = pattern.findall(combined_text)
            traversal_matches.extend(matches)
        
        if traversal_matches:
            confidence = min(0.95, len(traversal_matches) * 0.4)
            threats.append(ThreatEvent(
                threat_type=ThreatType.SUSPICIOUS_PATTERN,
                severity=ThreatSeverity.HIGH,
                source_ip=client_ip,
                user_id=user_id,
                timestamp=datetime.now(timezone.utc),
                details={
                    "threat_subtype": "path_traversal",
                    "matches": traversal_matches[:5],
                    "pattern_count": len(traversal_matches)
                },
                confidence_score=confidence,
                request_data=request_data
            ))
        
        # Command Injection Detection
        command_matches = []
        for pattern in self._compiled_patterns["command_injection"]:
            matches = pattern.findall(combined_text)
            command_matches.extend(matches)
        
        if command_matches:
            confidence = min(0.9, len(command_matches) * 0.35)
            threats.append(ThreatEvent(
                threat_type=ThreatType.SUSPICIOUS_PATTERN,
                severity=ThreatSeverity.HIGH,
                source_ip=client_ip,
                user_id=user_id,
                timestamp=datetime.now(timezone.utc),
                details={
                    "threat_subtype": "command_injection",
                    "matches": command_matches[:5],
                    "pattern_count": len(command_matches)
                },
                confidence_score=confidence,
                request_data=request_data
            ))
        
        return threats
    
    async def _detect_behavioral_anomalies(
        self, client_ip: str, user_id: Optional[int], request_data: Dict,
        response_status: int, response_time: float
    ) -> List[ThreatEvent]:
        """Detect behavioral anomalies"""
        threats = []
        
        # Analyze request rate
        rate_threat = await self._analyze_request_rate(client_ip, user_id, request_data)
        if rate_threat:
            threats.append(rate_threat)
        
        # Analyze error patterns
        error_threat = await self._analyze_error_patterns(client_ip, user_id, response_status, request_data)
        if error_threat:
            threats.append(error_threat)
        
        # Analyze user agent patterns
        ua_threat = await self._analyze_user_agent_patterns(client_ip, request_data)
        if ua_threat:
            threats.append(ua_threat)
        
        # Analyze resource access patterns
        resource_threat = await self._analyze_resource_access_patterns(client_ip, user_id, request_data)
        if resource_threat:
            threats.append(resource_threat)
        
        return threats
    
    async def _analyze_request_rate(self, client_ip: str, user_id: Optional[int], request_data: Dict) -> Optional[ThreatEvent]:
        """Analyze request rate for DDoS/brute force detection"""
        current_time = time.time()
        identifier = f"{client_ip}:{user_id or 'anonymous'}"
        
        # Count requests in last minute
        key = f"threat:request_rate:{identifier}"
        
        pipe = self.redis.pipeline()
        pipe.zadd(key, {str(current_time): current_time})
        pipe.zcount(key, current_time - 60, current_time)  # Last minute
        pipe.zremrangebyscore(key, 0, current_time - 300)  # Clean old data (5 minutes)
        pipe.expire(key, 300)
        
        results = await pipe.execute()
        requests_per_minute = results[1]
        
        # Determine threat level based on request rate
        if requests_per_minute > self.request_rate_thresholds["malicious"]:
            severity = ThreatSeverity.CRITICAL
            threat_type = ThreatType.DDOS
            confidence = 0.9
        elif requests_per_minute > self.request_rate_thresholds["suspicious"]:
            severity = ThreatSeverity.HIGH
            threat_type = ThreatType.DDOS
            confidence = 0.7
        elif requests_per_minute > self.request_rate_thresholds["normal"]:
            severity = ThreatSeverity.MEDIUM
            threat_type = ThreatType.SUSPICIOUS_PATTERN
            confidence = 0.5
        else:
            return None
        
        return ThreatEvent(
            threat_type=threat_type,
            severity=severity,
            source_ip=client_ip,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc),
            details={
                "requests_per_minute": requests_per_minute,
                "threshold_exceeded": "malicious" if requests_per_minute > self.request_rate_thresholds["malicious"] else "suspicious"
            },
            confidence_score=confidence,
            request_data=request_data
        )
    
    async def _analyze_error_patterns(
        self, client_ip: str, user_id: Optional[int], response_status: int, request_data: Dict
    ) -> Optional[ThreatEvent]:
        """Analyze error patterns for reconnaissance/brute force detection"""
        if response_status < 400:
            return None
        
        current_time = time.time()
        identifier = f"{client_ip}:{user_id or 'anonymous'}"
        
        # Count errors and total requests in last 5 minutes
        error_key = f"threat:errors:{identifier}"
        total_key = f"threat:total:{identifier}"
        
        pipe = self.redis.pipeline()
        pipe.zadd(error_key, {str(current_time): current_time})
        pipe.zadd(total_key, {str(current_time): current_time})
        pipe.zcount(error_key, current_time - 300, current_time)
        pipe.zcount(total_key, current_time - 300, current_time)
        pipe.expire(error_key, 300)
        pipe.expire(total_key, 300)
        
        results = await pipe.execute()
        error_count = results[2]
        total_count = results[3]
        
        if total_count < 10:  # Need minimum sample size
            return None
        
        error_rate = error_count / total_count
        
        # Determine threat level based on error rate
        if error_rate > self.error_rate_thresholds["malicious"]:
            severity = ThreatSeverity.HIGH
            threat_type = ThreatType.BRUTE_FORCE if response_status == 401 else ThreatType.RECONNAISSANCE
            confidence = 0.8
        elif error_rate > self.error_rate_thresholds["suspicious"]:
            severity = ThreatSeverity.MEDIUM
            threat_type = ThreatType.RECONNAISSANCE
            confidence = 0.6
        else:
            return None
        
        return ThreatEvent(
            threat_type=threat_type,
            severity=severity,
            source_ip=client_ip,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc),
            details={
                "error_rate": error_rate,
                "error_count": error_count,
                "total_count": total_count,
                "status_code": response_status
            },
            confidence_score=confidence,
            request_data=request_data
        )
    
    async def _analyze_user_agent_patterns(self, client_ip: str, request_data: Dict) -> Optional[ThreatEvent]:
        """Analyze user agent for bot/malicious patterns"""
        user_agent = request_data.get("user_agent", "").lower()
        
        # Suspicious user agent patterns
        malicious_patterns = [
            r"sqlmap", r"nmap", r"nikto", r"dirbuster", r"gobuster",
            r"masscan", r"zap", r"burp", r"metasploit", r"w3af",
            r"acunetix", r"nessus", r"openvas", r"qualys", r"rapid7"
        ]
        
        bot_patterns = [
            r"bot", r"crawler", r"scraper", r"spider", r"wget", r"curl"
        ]
        
        # Check for malicious tools
        for pattern in malicious_patterns:
            if re.search(pattern, user_agent):
                return ThreatEvent(
                    threat_type=ThreatType.RECONNAISSANCE,
                    severity=ThreatSeverity.HIGH,
                    source_ip=client_ip,
                    user_id=None,
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "user_agent": user_agent,
                        "detected_tool": pattern,
                        "category": "security_tool"
                    },
                    confidence_score=0.95,
                    request_data=request_data
                )
        
        # Check for suspicious bots
        for pattern in bot_patterns:
            if re.search(pattern, user_agent):
                # Exclude legitimate search engine bots
                legitimate_bots = [
                    "googlebot", "bingbot", "slurp", "duckduckbot",
                    "baiduspider", "yandexbot", "facebookexternalhit"
                ]
                
                if not any(bot in user_agent for bot in legitimate_bots):
                    return ThreatEvent(
                        threat_type=ThreatType.MALICIOUS_BOT,
                        severity=ThreatSeverity.MEDIUM,
                        source_ip=client_ip,
                        user_id=None,
                        timestamp=datetime.now(timezone.utc),
                        details={
                            "user_agent": user_agent,
                            "detected_pattern": pattern,
                            "category": "suspicious_bot"
                        },
                        confidence_score=0.7,
                        request_data=request_data
                    )
        
        return None
    
    async def _analyze_resource_access_patterns(
        self, client_ip: str, user_id: Optional[int], request_data: Dict
    ) -> Optional[ThreatEvent]:
        """Analyze patterns of resource access for privilege escalation/data exfiltration"""
        path = request_data.get("path", "")
        method = request_data.get("method", "")
        
        # Suspicious path patterns
        admin_paths = ["/admin", "/api/v1/admin"]
        sensitive_paths = ["/api/v1/users", "/api/v1/backup", "/api/v1/export"]
        
        # Check for unauthorized admin access attempts
        if any(path.startswith(admin_path) for admin_path in admin_paths):
            if not user_id:  # Unauthenticated admin access
                return ThreatEvent(
                    threat_type=ThreatType.PRIVILEGE_ESCALATION,
                    severity=ThreatSeverity.HIGH,
                    source_ip=client_ip,
                    user_id=user_id,
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "path": path,
                        "method": method,
                        "category": "unauthorized_admin_access"
                    },
                    confidence_score=0.8,
                    request_data=request_data
                )
        
        # Check for bulk data access patterns
        if method == "GET" and any(path.startswith(sensitive_path) for sensitive_path in sensitive_paths):
            # Count recent access to sensitive endpoints
            current_time = time.time()
            key = f"threat:sensitive_access:{client_ip}:{user_id or 'anonymous'}"
            
            pipe = self.redis.pipeline()
            pipe.zadd(key, {str(current_time): current_time})
            pipe.zcount(key, current_time - 300, current_time)  # Last 5 minutes
            pipe.expire(key, 300)
            
            results = await pipe.execute()
            access_count = results[1]
            
            if access_count > 20:  # More than 20 sensitive requests in 5 minutes
                return ThreatEvent(
                    threat_type=ThreatType.DATA_EXFILTRATION,
                    severity=ThreatSeverity.HIGH,
                    source_ip=client_ip,
                    user_id=user_id,
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "path": path,
                        "method": method,
                        "access_count": access_count,
                        "category": "bulk_sensitive_access"
                    },
                    confidence_score=0.85,
                    request_data=request_data
                )
        
        return None
    
    async def _detect_statistical_anomalies(
        self, client_ip: str, user_id: Optional[int], request_data: Dict
    ) -> List[ThreatEvent]:
        """Detect statistical anomalies using baseline metrics"""
        threats = []
        
        # This would implement more sophisticated statistical analysis
        # For now, we'll implement basic anomaly detection
        
        # Analyze request size anomalies
        content_length = int(request_data.get("content_length", 0))
        if content_length > 1024 * 1024:  # 1MB threshold
            threats.append(ThreatEvent(
                threat_type=ThreatType.ANOMALOUS_BEHAVIOR,
                severity=ThreatSeverity.MEDIUM,
                source_ip=client_ip,
                user_id=user_id,
                timestamp=datetime.now(timezone.utc),
                details={
                    "anomaly_type": "large_request_size",
                    "content_length": content_length,
                    "threshold": 1024 * 1024
                },
                confidence_score=0.6,
                request_data=request_data
            ))
        
        # Analyze unusual request timing patterns (future enhancement)
        # This would compare current patterns to baseline behavior
        
        return threats
    
    async def _detect_account_threats(
        self, user_id: int, request_data: Dict, client_ip: str
    ) -> List[ThreatEvent]:
        """Detect account-specific threats"""
        threats = []
        
        # Check for unusual login patterns
        if request_data.get("path") == "/api/v1/auth/login":
            # Count login attempts in last hour
            current_time = time.time()
            key = f"threat:login_attempts:{user_id}"
            
            pipe = self.redis.pipeline()
            pipe.zadd(key, {str(current_time): current_time})
            pipe.zcount(key, current_time - 3600, current_time)
            pipe.expire(key, 3600)
            
            results = await pipe.execute()
            login_attempts = results[1]
            
            if login_attempts > 10:  # More than 10 login attempts in 1 hour
                threats.append(ThreatEvent(
                    threat_type=ThreatType.ACCOUNT_TAKEOVER,
                    severity=ThreatSeverity.HIGH,
                    source_ip=client_ip,
                    user_id=user_id,
                    timestamp=datetime.now(timezone.utc),
                    details={
                        "login_attempts": login_attempts,
                        "time_window": "1_hour"
                    },
                    confidence_score=0.8,
                    request_data=request_data
                ))
        
        return threats
    
    async def _store_threat_event(self, threat: ThreatEvent):
        """Store threat event for analysis and response"""
        # Store in Redis for immediate access
        key = f"threats:{threat.source_ip}:{threat.timestamp.isoformat()}"
        threat_data = asdict(threat)
        # Convert datetime to string for JSON serialization
        threat_data["timestamp"] = threat.timestamp.isoformat()
        
        await self.redis.setex(key, 86400, json.dumps(threat_data, default=str))
        
        # Add to threat count for IP
        count_key = f"threat_count:{threat.source_ip}"
        await self.redis.incr(count_key)
        await self.redis.expire(count_key, 86400)
        
        # Store in audit log (in production, this would go to database)
        create_audit_log(
            action=AuditActions.SECURITY_VULNERABILITY_DETECTED,
            resource_type="security_threat",
            category=AuditCategory.SECURITY_EVENT,
            severity=SeverityLevel.HIGH if threat.severity in [ThreatSeverity.HIGH, ThreatSeverity.CRITICAL] else SeverityLevel.MEDIUM,
            ip_address=threat.source_ip,
            user_id=threat.user_id,
            details={
                "threat_type": threat.threat_type.value,
                "severity": threat.severity.value,
                "confidence_score": threat.confidence_score,
                "threat_details": threat.details
            },
            success=False
        )
    
    async def get_threat_statistics(self, time_range: int = 3600) -> Dict[str, Any]:
        """Get threat statistics for the specified time range (in seconds)"""
        current_time = time.time()
        
        # Get all threat keys in time range
        pattern = "threats:*"
        threat_keys = await self.redis.keys(pattern)
        
        threats_by_type = defaultdict(int)
        threats_by_severity = defaultdict(int)
        threats_by_ip = defaultdict(int)
        total_threats = 0
        
        for key in threat_keys:
            threat_data_json = await self.redis.get(key)
            if threat_data_json:
                try:
                    threat_data = json.loads(threat_data_json)
                    threat_time = datetime.fromisoformat(threat_data["timestamp"]).timestamp()
                    
                    if current_time - threat_time <= time_range:
                        total_threats += 1
                        threats_by_type[threat_data["threat_type"]] += 1
                        threats_by_severity[threat_data["severity"]] += 1
                        threats_by_ip[threat_data["source_ip"]] += 1
                except Exception:
                    continue
        
        # Get top threatening IPs
        top_ips = sorted(threats_by_ip.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "total_threats": total_threats,
            "threats_by_type": dict(threats_by_type),
            "threats_by_severity": dict(threats_by_severity),
            "top_threatening_ips": top_ips,
            "time_range_seconds": time_range
        }


class ThreatResponseEngine:
    """
    Automated threat response and mitigation system
    """
    
    def __init__(self, redis_client: Redis, detection_engine: ThreatDetectionEngine):
        self.redis = redis_client
        self.detection_engine = detection_engine
        
        # Response thresholds
        self.auto_block_thresholds = {
            ThreatType.SQL_INJECTION: 1,      # Block immediately
            ThreatType.XSS_ATTEMPT: 2,        # Block after 2 attempts
            ThreatType.DDOS: 1,               # Block immediately
            ThreatType.BRUTE_FORCE: 1,        # Block immediately
            ThreatType.RECONNAISSANCE: 3,      # Block after 3 attempts
            ThreatType.MALICIOUS_BOT: 2,      # Block after 2 attempts
        }
    
    async def respond_to_threats(self, threats: List[ThreatEvent]) -> List[Dict[str, Any]]:
        """
        Respond to detected threats with appropriate mitigation
        Returns list of actions taken
        """
        actions_taken = []
        
        for threat in threats:
            # Determine appropriate response
            response_actions = await self._determine_response_actions(threat)
            
            for action in response_actions:
                if await self._execute_response_action(threat, action):
                    actions_taken.append({
                        "threat_id": f"{threat.source_ip}:{threat.timestamp.isoformat()}",
                        "action": action,
                        "threat_type": threat.threat_type.value,
                        "severity": threat.severity.value,
                        "executed_at": datetime.now(timezone.utc).isoformat()
                    })
        
        return actions_taken
    
    async def _determine_response_actions(self, threat: ThreatEvent) -> List[str]:
        """Determine appropriate response actions for threat"""
        actions = []
        
        # Always log the threat
        actions.append("log_threat")
        
        # Check if IP should be blocked
        if await self._should_block_ip(threat):
            actions.append("block_ip")
        
        # Check if user account should be locked
        if threat.user_id and await self._should_lock_account(threat):
            actions.append("lock_account")
        
        # Check if alerts should be sent
        if threat.severity in [ThreatSeverity.HIGH, ThreatSeverity.CRITICAL]:
            actions.append("send_alert")
        
        # Check if rate limiting should be increased
        if threat.threat_type in [ThreatType.DDOS, ThreatType.BRUTE_FORCE]:
            actions.append("increase_rate_limit")
        
        return actions
    
    async def _should_block_ip(self, threat: ThreatEvent) -> bool:
        """Check if IP should be automatically blocked"""
        if threat.threat_type in self.auto_block_thresholds:
            # Count recent threats from this IP
            time.time()
            key = f"threat_count:{threat.source_ip}:{threat.threat_type.value}"
            
            count = await self.redis.incr(key)
            await self.redis.expire(key, 3600)  # Reset after 1 hour
            
            threshold = self.auto_block_thresholds[threat.threat_type]
            return count >= threshold
        
        return False
    
    async def _should_lock_account(self, threat: ThreatEvent) -> bool:
        """Check if user account should be locked"""
        if not threat.user_id:
            return False
        
        # Lock account for certain threat types
        lockable_threats = [
            ThreatType.ACCOUNT_TAKEOVER,
            ThreatType.PRIVILEGE_ESCALATION,
            ThreatType.BRUTE_FORCE
        ]
        
        return threat.threat_type in lockable_threats
    
    async def _execute_response_action(self, threat: ThreatEvent, action: str) -> bool:
        """Execute a specific response action"""
        try:
            if action == "log_threat":
                await self._log_threat_action(threat)
                return True
            
            elif action == "block_ip":
                await self._block_ip_action(threat)
                return True
            
            elif action == "lock_account":
                await self._lock_account_action(threat)
                return True
            
            elif action == "send_alert":
                await self._send_alert_action(threat)
                return True
            
            elif action == "increase_rate_limit":
                await self._increase_rate_limit_action(threat)
                return True
            
            return False
            
        except Exception as e:
            print(f"Error executing response action {action}: {e}")
            return False
    
    async def _log_threat_action(self, threat: ThreatEvent):
        """Log threat for security monitoring"""
        print(f"THREAT DETECTED: {threat.threat_type.value} from {threat.source_ip} - Severity: {threat.severity.value}")
    
    async def _block_ip_action(self, threat: ThreatEvent):
        """Block IP address"""
        # Add to Redis blacklist
        key = f"security:blacklist:{threat.source_ip}"
        block_data = {
            "blocked_at": datetime.now(timezone.utc).isoformat(),
            "reason": f"{threat.threat_type.value} - {threat.severity.value}",
            "threat_details": threat.details,
            "auto_blocked": True
        }
        
        # Block for different durations based on severity
        duration_map = {
            ThreatSeverity.CRITICAL: 86400 * 7,  # 7 days
            ThreatSeverity.HIGH: 86400,          # 1 day
            ThreatSeverity.MEDIUM: 3600,         # 1 hour
            ThreatSeverity.LOW: 900              # 15 minutes
        }
        
        duration = duration_map.get(threat.severity, 3600)
        await self.redis.setex(key, duration, json.dumps(block_data))
        
        print(f"IP {threat.source_ip} blocked for {duration} seconds due to {threat.threat_type.value}")
    
    async def _lock_account_action(self, threat: ThreatEvent):
        """Lock user account"""
        if not threat.user_id:
            return
        
        # Store account lock info
        key = f"security:locked_account:{threat.user_id}"
        lock_data = {
            "locked_at": datetime.now(timezone.utc).isoformat(),
            "reason": f"{threat.threat_type.value}",
            "source_ip": threat.source_ip,
            "auto_locked": True
        }
        
        await self.redis.setex(key, 86400, json.dumps(lock_data))  # Lock for 24 hours
        
        print(f"Account {threat.user_id} locked due to {threat.threat_type.value}")
    
    async def _send_alert_action(self, threat: ThreatEvent):
        """Send security alert"""
        # In production, integrate with alerting system (email, Slack, PagerDuty, etc.)
        alert_data = {
            "threat_type": threat.threat_type.value,
            "severity": threat.severity.value,
            "source_ip": threat.source_ip,
            "user_id": threat.user_id,
            "confidence": threat.confidence_score,
            "details": threat.details,
            "timestamp": threat.timestamp.isoformat()
        }
        
        print(f"SECURITY ALERT: {json.dumps(alert_data, indent=2)}")
        
        # Store alert for dashboard
        alert_key = f"security:alerts:{datetime.now(timezone.utc).isoformat()}"
        await self.redis.setex(alert_key, 86400 * 30, json.dumps(alert_data))  # Keep for 30 days
    
    async def _increase_rate_limit_action(self, threat: ThreatEvent):
        """Increase rate limiting for IP/user"""
        # Implement dynamic rate limit adjustment
        rate_limit_key = f"security:rate_limit_boost:{threat.source_ip}"
        
        # Reduce rate limit by 50% for 1 hour
        boost_data = {
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "reason": threat.threat_type.value,
            "reduction_factor": 0.5
        }
        
        await self.redis.setex(rate_limit_key, 3600, json.dumps(boost_data))
        
        print(f"Rate limit increased for {threat.source_ip} due to {threat.threat_type.value}")


class ThreatDetectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for real-time threat detection and response
    """
    
    def __init__(self, app, redis_client: Redis):
        super().__init__(app)
        self.detection_engine = ThreatDetectionEngine(redis_client)
        self.response_engine = ThreatResponseEngine(redis_client, self.detection_engine)
    
    async def dispatch(self, request: Request, call_next):
        """Analyze request and response for threats"""
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate response time
        response_time = time.time() - start_time
        
        # Analyze for threats (don't block the response)
        if settings.ENABLE_THREAT_DETECTION:
            asyncio.create_task(
                self._analyze_and_respond(request, response.status_code, response_time)
            )
        
        return response
    
    async def _analyze_and_respond(self, request: Request, status_code: int, response_time: float):
        """Analyze request for threats and respond accordingly"""
        try:
            # Detect threats
            threats = await self.detection_engine.analyze_request(request, status_code, response_time)
            
            # Respond to threats
            if threats and settings.AUTO_BLOCK_THREATS:
                await self.response_engine.respond_to_threats(threats)
                
        except Exception as e:
            print(f"Error in threat detection: {e}")