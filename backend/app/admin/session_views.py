"""
Session management views for SQLAdmin
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs
from sqladmin import ModelView, BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from redis.exceptions import ConnectionError, RedisError

from app.core.database import get_db
from app.services.session_store import SessionStore, get_session_store
from app.services.auth import get_user_by_id
from app.models.user import User

logger = logging.getLogger(__name__)


class SessionManagementView(BaseView):
    """Custom view for session management"""
    
    name = "Session Management"
    icon = "fas fa-lock"
    identity = "session_management"  # Explicit identity for SQLAdmin routing
    
    @expose("/", methods=["GET"])
    async def index(self, request: Request) -> Response:
        """Default entry point - redirect to sessions list"""
        return await self.sessions_list(request)
    
    @expose("/sessions", methods=["GET"])
    async def sessions_list(self, request: Request) -> Response:
        """List all active sessions with filtering support"""
        try:
            session_store = await get_session_store()
            
            # Parse query parameters for filtering
            query_params = dict(request.query_params)
            user_filter = query_params.get('user', '').strip()
            status_filter = query_params.get('status', 'all').strip()
            role_filter = query_params.get('role', 'all').strip()
            
            sessions = await self._get_filtered_sessions(
                session_store, user_filter, status_filter, role_filter
            )
            
            html_content = self._render_sessions_html(sessions)
            return Response(content=html_content, media_type="text/html")
            
        except ConnectionError as e:
            logger.error(f"Redis connection error in sessions_list: {str(e)}")
            return self._render_error_page(
                "Redis Connection Error",
                "Unable to connect to Redis server. Please check the Redis service status.",
                "/admin/sessions"
            )
        except RedisError as e:
            logger.error(f"Redis error in sessions_list: {str(e)}")
            return self._render_error_page(
                "Redis Error",
                f"Redis operation failed: {str(e)}",
                "/admin/sessions"
            )
        except Exception as e:
            logger.error(f"Unexpected error in sessions_list: {str(e)}")
            return self._render_error_page(
                "System Error",
                f"An unexpected error occurred: {str(e)}",
                "/admin/sessions"
            )
    
    @expose("/sessions/revoke/{session_id:str}", methods=["POST"])
    async def revoke_session(self, request: Request) -> Response:
        """Revoke a specific session"""
        session_id = request.path_params["session_id"]
        
        try:
            session_store = await get_session_store()
            success = await session_store.delete_session(session_id)
            
            if success:
                logger.info(f"Session {session_id[:8]}... revoked successfully")
                return JSONResponse({
                    "success": True,
                    "message": f"Session {session_id[:8]}... revoked successfully"
                })
            else:
                return JSONResponse({
                    "success": False,
                    "message": "Session not found or already expired"
                }, status_code=404)
                
        except ConnectionError as e:
            logger.error(f"Redis connection error in revoke_session: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": "Redis connection error. Please try again."
            }, status_code=503)
        except RedisError as e:
            logger.error(f"Redis error in revoke_session: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Redis operation failed: {str(e)}"
            }, status_code=500)
        except Exception as e:
            logger.error(f"Unexpected error in revoke_session: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Error revoking session: {str(e)}"
            }, status_code=500)
    
    @expose("/sessions/revoke-user/{user_id:int}", methods=["POST"])
    async def revoke_user_sessions(self, request: Request) -> Response:
        """Revoke all sessions for a specific user"""
        user_id = request.path_params["user_id"]
        
        try:
            session_store = await get_session_store()
            revoked_count = await session_store.delete_user_sessions(user_id)
            
            logger.info(f"Revoked {revoked_count} sessions for user {user_id}")
            return JSONResponse({
                "success": True,
                "message": f"Revoked {revoked_count} sessions for user {user_id}"
            })
            
        except ConnectionError as e:
            logger.error(f"Redis connection error in revoke_user_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": "Redis connection error. Please try again."
            }, status_code=503)
        except RedisError as e:
            logger.error(f"Redis error in revoke_user_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Redis operation failed: {str(e)}"
            }, status_code=500)
        except Exception as e:
            logger.error(f"Unexpected error in revoke_user_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Error revoking user sessions: {str(e)}"
            }, status_code=500)
    
    @expose("/sessions/bulk-revoke", methods=["POST"])
    async def bulk_revoke_sessions(self, request: Request) -> Response:
        """Revoke multiple sessions at once"""
        try:
            form = await request.form()
            session_ids_str = form.get('session_ids', '')
            
            if not session_ids_str:
                return JSONResponse({
                    "success": False,
                    "message": "No sessions selected for revocation"
                }, status_code=400)
            
            # Parse session IDs (comma-separated)
            session_ids = [sid.strip() for sid in session_ids_str.split(',') if sid.strip()]
            
            if not session_ids:
                return JSONResponse({
                    "success": False,
                    "message": "No valid session IDs provided"
                }, status_code=400)
            
            session_store = await get_session_store()
            revoked_count = 0
            failed_count = 0
            
            for session_id in session_ids:
                try:
                    success = await session_store.delete_session(session_id)
                    if success:
                        revoked_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"Failed to revoke session {session_id[:8]}...: {str(e)}")
                    failed_count += 1
            
            message = f"Revoked {revoked_count} sessions"
            if failed_count > 0:
                message += f" ({failed_count} failed)"
            
            logger.info(f"Bulk revoke: {message}")
            return JSONResponse({
                "success": True,
                "message": message,
                "revoked_count": revoked_count,
                "failed_count": failed_count
            })
            
        except ConnectionError as e:
            logger.error(f"Redis connection error in bulk_revoke_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": "Redis connection error. Please try again."
            }, status_code=503)
        except Exception as e:
            logger.error(f"Unexpected error in bulk_revoke_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Error during bulk revocation: {str(e)}"
            }, status_code=500)
    
    @expose("/sessions/cleanup-expired", methods=["POST"])
    async def cleanup_expired_sessions(self, request: Request) -> Response:
        """Clean up expired sessions"""
        try:
            session_store = await get_session_store()
            cleaned_count = await session_store.cleanup_expired_sessions()
            
            logger.info(f"Cleaned up {cleaned_count} expired sessions")
            return JSONResponse({
                "success": True,
                "message": f"Cleaned up {cleaned_count} expired sessions"
            })
            
        except ConnectionError as e:
            logger.error(f"Redis connection error in cleanup_expired_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": "Redis connection error. Please try again."
            }, status_code=503)
        except Exception as e:
            logger.error(f"Unexpected error in cleanup_expired_sessions: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Error during cleanup: {str(e)}"
            }, status_code=500)
    
    @expose("/sessions/stats", methods=["GET"])
    async def session_stats(self, request: Request) -> Response:
        """Get session statistics"""
        session_store = await get_session_store()
        
        try:
            keys = await session_store.redis.keys("session:*")
            total_sessions = len(keys)
            
            admin_sessions = 0
            user_sessions = 0
            active_users = set()
            
            for key in keys:
                session_data = await session_store.redis.get(key)
                if session_data:
                    try:
                        data = json.loads(session_data)
                        user_id = data.get('id')
                        if user_id:
                            active_users.add(user_id)
                        
                        if data.get('is_admin') or data.get('is_superuser'):
                            admin_sessions += 1
                        else:
                            user_sessions += 1
                    except json.JSONDecodeError:
                        continue
            
            stats = {
                'total_sessions': total_sessions,
                'admin_sessions': admin_sessions,
                'user_sessions': user_sessions,
                'unique_active_users': len(active_users),
                'redis_info': await self._get_redis_stats(session_store)
            }
            
            html_content = self._render_stats_html(stats)
            return Response(content=html_content, media_type="text/html")
            
        except ConnectionError as e:
            logger.error(f"Redis connection error in session_stats: {str(e)}")
            return self._render_error_page(
                "Redis Connection Error",
                "Unable to connect to Redis server. Please check the Redis service status.",
                "/admin/sessions"
            )
        except Exception as e:
            logger.error(f"Unexpected error in session_stats: {str(e)}")
            return self._render_error_page(
                "System Error",
                f"An unexpected error occurred while loading statistics: {str(e)}",
                "/admin/sessions"
            )
    
    def _render_error_page(self, title: str, message: str, return_url: str) -> Response:
        """Render error page for session management"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{title} - Chrono Scraper Admin</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        </head>
        <body class="bg-light">
            <div class="container-fluid mt-4">
                <div class="row">
                    <div class="col-12">
                        <div class="alert alert-danger">
                            <h4 class="alert-heading"><i class="fas fa-exclamation-triangle me-2"></i>{title}</h4>
                            <p>{message}</p>
                            <hr>
                            <a href="{return_url}" class="btn btn-outline-danger">
                                <i class="fas fa-arrow-left me-1"></i>Return to Sessions
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return Response(content=html_content, media_type="text/html")
    
    async def _get_filtered_sessions(self, session_store: SessionStore, user_filter: str, status_filter: str, role_filter: str) -> List[Dict[str, Any]]:
        """Get filtered sessions based on criteria"""
        try:
            keys = await session_store.redis.keys("session:*")
            sessions = []
            
            for key in keys:
                session_data = await session_store.redis.get(key)
                if session_data:
                    try:
                        data = json.loads(session_data)
                        session_id = key.decode('utf-8').replace('session:', '')
                        
                        # Get session expiry
                        ttl = await session_store.redis.ttl(key)
                        expires_in = max(0, ttl)
                        
                        session_info = {
                            'session_id': session_id,
                            'email': data.get('email', 'Unknown'),
                            'is_admin': data.get('is_admin', False),
                            'is_superuser': data.get('is_superuser', False),
                            'is_active': expires_in > 0,
                            'expires_in': expires_in,
                            'created_at': data.get('created_at', 'Unknown')
                        }
                        
                        # Apply filters
                        if user_filter and user_filter.lower() not in session_info['email'].lower():
                            continue
                            
                        if status_filter == 'active' and not session_info['is_active']:
                            continue
                        elif status_filter == 'expired' and session_info['is_active']:
                            continue
                            
                        if role_filter == 'admin' and not (session_info['is_admin'] or session_info['is_superuser']):
                            continue
                        elif role_filter == 'user' and (session_info['is_admin'] or session_info['is_superuser']):
                            continue
                        
                        sessions.append(session_info)
                        
                    except json.JSONDecodeError:
                        continue
            
            return sorted(sessions, key=lambda x: x['expires_in'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error getting filtered sessions: {str(e)}")
            return []
    
    def _render_sessions_html(self, sessions: List[Dict[str, Any]]) -> str:
        """Render sessions as HTML table"""
        rows = ""
        for session in sessions:
            status_badge = "success" if session['is_active'] else "secondary"
            status_text = "Active" if session['is_active'] else "Expired"
            
            user_badge = ""
            if session.get('is_superuser'):
                user_badge = '<span class="badge badge-danger">Superuser</span>'
            elif session.get('is_admin'):
                user_badge = '<span class="badge badge-warning">Admin</span>'
            else:
                user_badge = '<span class="badge badge-primary">User</span>'
            
            expires_text = f"{session['expires_in']}s" if session['expires_in'] > 0 else "Expired"
            
            revoke_button = f"""
                <button class="btn btn-sm btn-outline-danger" 
                        onclick="revokeSession('{session['session_id']}')"
                        {'disabled' if not session['is_active'] else ''}>
                    Revoke
                </button>
            """ if session['is_active'] else ""
            
            rows += f"""
                <tr>
                    <td><code>{session['session_id'][:12]}...</code></td>
                    <td>{session.get('email', 'Unknown')}</td>
                    <td>{user_badge}</td>
                    <td><span class="badge badge-{status_badge}">{status_text}</span></td>
                    <td>{expires_text}</td>
                    <td>{session.get('created_at', 'Unknown')}</td>
                    <td>{revoke_button}</td>
                </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Session Management - Chrono Scraper Admin</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        </head>
        <body class="bg-light">
            <div class="container-fluid mt-4">
                <div class="row">
                    <div class="col-12">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h2><i class="fas fa-lock me-2"></i>Active Sessions</h2>
                            <div>
                                <a href="/admin/sessions/stats" class="btn btn-outline-primary me-2">
                                    <i class="fas fa-chart-bar me-1"></i>Statistics
                                </a>
                                <button class="btn btn-outline-secondary" onclick="location.reload()">
                                    <i class="fas fa-sync-alt me-1"></i>Refresh
                                </button>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-body">
                                <div class="table-responsive">
                                    <table class="table table-hover">
                                        <thead class="table-dark">
                                            <tr>
                                                <th>Session ID</th>
                                                <th>User Email</th>
                                                <th>Role</th>
                                                <th>Status</th>
                                                <th>Expires In</th>
                                                <th>Created</th>
                                                <th>Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {rows}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                async function revokeSession(sessionId) {{
                    if (!confirm('Are you sure you want to revoke this session?')) return;
                    
                    try {{
                        const response = await fetch(`/admin/sessions/revoke/${{sessionId}}`, {{
                            method: 'POST'
                        }});
                        
                        const result = await response.json();
                        
                        if (result.success) {{
                            alert(result.message);
                            location.reload();
                        }} else {{
                            alert('Error: ' + result.message);
                        }}
                    }} catch (error) {{
                        alert('Network error: ' + error.message);
                    }}
                }}
            </script>
        </body>
        </html>
        """
    
    def _render_stats_html(self, stats: Dict[str, Any]) -> str:
        """Render session statistics as HTML"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Session Statistics - Chrono Scraper Admin</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        </head>
        <body class="bg-light">
            <div class="container-fluid mt-4">
                <div class="row">
                    <div class="col-12">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h2><i class="fas fa-chart-bar me-2"></i>Session Statistics</h2>
                            <a href="/admin/sessions" class="btn btn-outline-primary">
                                <i class="fas fa-arrow-left me-1"></i>Back to Sessions
                            </a>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-3 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-users fa-3x text-primary mb-3"></i>
                                        <h3 class="card-title">{stats['total_sessions']}</h3>
                                        <p class="card-text">Total Sessions</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-user-shield fa-3x text-danger mb-3"></i>
                                        <h3 class="card-title">{stats['admin_sessions']}</h3>
                                        <p class="card-text">Admin Sessions</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-user fa-3x text-success mb-3"></i>
                                        <h3 class="card-title">{stats['user_sessions']}</h3>
                                        <p class="card-text">User Sessions</p>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-3 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-user-check fa-3x text-info mb-3"></i>
                                        <h3 class="card-title">{stats['unique_active_users']}</h3>
                                        <p class="card-text">Active Users</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-12">
                                <div class="card">
                                    <div class="card-header">
                                        <h5><i class="fas fa-database me-2"></i>Redis Information</h5>
                                    </div>
                                    <div class="card-body">
                                        <div class="row">
                                            <div class="col-md-4">
                                                <strong>Connected Clients:</strong> {stats['redis_info'].get('connected_clients', 'N/A')}
                                            </div>
                                            <div class="col-md-4">
                                                <strong>Used Memory:</strong> {stats['redis_info'].get('used_memory_human', 'N/A')}
                                            </div>
                                            <div class="col-md-4">
                                                <strong>Total Keys:</strong> {stats['redis_info'].get('total_keys', 'N/A')}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
    
    async def _get_redis_stats(self, session_store: SessionStore) -> Dict[str, Any]:
        """Get Redis statistics"""
        try:
            info = await session_store.redis.info()
            
            return {
                'connected_clients': info.get('connected_clients'),
                'used_memory_human': info.get('used_memory_human'),
                'total_keys': info.get('keyspace', {}).get('db0', {}).get('keys', 0)
            }
        except Exception:
            return {
                'connected_clients': 'N/A',
                'used_memory_human': 'N/A',
                'total_keys': 'N/A'
            }


class UserAnalyticsView(BaseView):
    """User analytics and activity monitoring"""
    
    name = "User Analytics"
    icon = "fas fa-analytics"
    identity = "user_analytics"  # Explicit identity for SQLAdmin routing
    
    @expose("/", methods=["GET"])
    async def index(self, request: Request) -> Response:
        """Default entry point - redirect to analytics dashboard"""
        return await self.analytics_dashboard(request)
    
    @expose("/analytics", methods=["GET"])
    async def analytics_dashboard(self, request: Request) -> Response:
        """Show user analytics dashboard"""
        
        try:
            async for db in get_db():
                # Get user statistics
                from sqlalchemy import func, text
                from app.models.user import User
                
                # Total users
                total_users_stmt = select(func.count(User.id))
                total_users = await db.scalar(total_users_stmt)
                
                # Users by approval status
                pending_users_stmt = select(func.count(User.id)).where(User.approval_status == 'pending')
                pending_users = await db.scalar(pending_users_stmt)
                
                approved_users_stmt = select(func.count(User.id)).where(User.approval_status == 'approved')
                approved_users = await db.scalar(approved_users_stmt)
                
                denied_users_stmt = select(func.count(User.id)).where(User.approval_status == 'denied')
                denied_users = await db.scalar(denied_users_stmt)
                
                # Verified users
                verified_users_stmt = select(func.count(User.id)).where(User.is_verified == True)
                verified_users = await db.scalar(verified_users_stmt)
                
                unverified_users_stmt = select(func.count(User.id)).where(User.is_verified == False)
                unverified_users = await db.scalar(unverified_users_stmt)
                
                stats = {
                    'total_users': total_users or 0,
                    'pending_users': pending_users or 0,
                    'approved_users': approved_users or 0,
                    'denied_users': denied_users or 0,
                    'verified_users': verified_users or 0,
                    'unverified_users': unverified_users or 0
                }
                
                html_content = self._render_analytics_html(stats)
                return Response(content=html_content, media_type="text/html")
                
        except Exception as e:
            return Response(
                content=f"<div class='alert alert-danger'>Error loading analytics: {str(e)}</div>",
                media_type="text/html"
            )
    
    def _render_analytics_html(self, stats: Dict[str, Any]) -> str:
        """Render analytics dashboard as HTML"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>User Analytics - Chrono Scraper Admin</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body class="bg-light">
            <div class="container-fluid mt-4">
                <div class="row">
                    <div class="col-12">
                        <h2><i class="fas fa-analytics me-2"></i>User Analytics Dashboard</h2>
                        
                        <div class="row mt-4">
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-users fa-2x text-primary mb-2"></i>
                                        <h4>{stats['total_users']}</h4>
                                        <small>Total Users</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-clock fa-2x text-warning mb-2"></i>
                                        <h4>{stats['pending_users']}</h4>
                                        <small>Pending Approval</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-check fa-2x text-success mb-2"></i>
                                        <h4>{stats['approved_users']}</h4>
                                        <small>Approved</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-times fa-2x text-danger mb-2"></i>
                                        <h4>{stats['denied_users']}</h4>
                                        <small>Denied</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-envelope-check fa-2x text-info mb-2"></i>
                                        <h4>{stats['verified_users']}</h4>
                                        <small>Email Verified</small>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-2 mb-3">
                                <div class="card text-center">
                                    <div class="card-body">
                                        <i class="fas fa-envelope fa-2x text-secondary mb-2"></i>
                                        <h4>{stats['unverified_users']}</h4>
                                        <small>Unverified</small>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <div class="card">
                                    <div class="card-header">
                                        <h5>Approval Status Distribution</h5>
                                    </div>
                                    <div class="card-body">
                                        <canvas id="approvalChart" width="400" height="200"></canvas>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6 mb-3">
                                <div class="card">
                                    <div class="card-header">
                                        <h5>Email Verification Status</h5>
                                    </div>
                                    <div class="card-body">
                                        <canvas id="verificationChart" width="400" height="200"></canvas>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                // Approval Status Chart
                const approvalCtx = document.getElementById('approvalChart').getContext('2d');
                new Chart(approvalCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['Pending', 'Approved', 'Denied'],
                        datasets: [{{
                            data: [{stats['pending_users']}, {stats['approved_users']}, {stats['denied_users']}],
                            backgroundColor: ['#ffc107', '#28a745', '#dc3545']
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false
                    }}
                }});
                
                // Verification Status Chart
                const verificationCtx = document.getElementById('verificationChart').getContext('2d');
                new Chart(verificationCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['Verified', 'Unverified'],
                        datasets: [{{
                            data: [{stats['verified_users']}, {stats['unverified_users']}],
                            backgroundColor: ['#17a2b8', '#6c757d']
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false
                    }}
                }});
            </script>
        </body>
        </html>
        """