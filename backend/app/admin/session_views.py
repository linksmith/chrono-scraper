"""
Session management views for SQLAdmin
"""
import json
from datetime import datetime
from typing import Any, Dict, List
from sqladmin import ModelView, BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.session_store import SessionStore, get_session_store
from app.services.auth import get_user_by_id


class SessionManagementView(BaseView):
    """Custom view for session management"""
    
    name = "Session Management"
    icon = "fas fa-lock"
    
    @expose("/sessions", methods=["GET"])
    async def sessions_list(self, request: Request) -> Response:
        """List all active sessions"""
        session_store = await get_session_store()
        
        try:
            # Get all session keys from Redis
            keys = await session_store.redis.keys("session:*")
            sessions = []
            
            for key in keys:
                session_data = await session_store.redis.get(key)
                if session_data:
                    try:
                        data = json.loads(session_data)
                        session_id = key.decode('utf-8').replace('session:', '')
                        
                        # Get TTL (time to live)
                        ttl = await session_store.redis.ttl(key)
                        
                        sessions.append({
                            'session_id': session_id,
                            'user_id': data.get('id'),
                            'email': data.get('email'),
                            'is_admin': data.get('is_admin', False),
                            'is_superuser': data.get('is_superuser', False),
                            'created_at': data.get('created_at', 'Unknown'),
                            'expires_in': ttl if ttl > 0 else 0,
                            'is_active': ttl > 0
                        })
                    except json.JSONDecodeError:
                        continue
            
            # Sort by creation time (newest first)
            sessions.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            html_content = self._render_sessions_html(sessions)
            return Response(content=html_content, media_type="text/html")
            
        except Exception as e:
            return Response(
                content=f"<div class='alert alert-danger'>Error loading sessions: {str(e)}</div>",
                media_type="text/html"
            )
    
    @expose("/sessions/revoke/{session_id:str}", methods=["POST"])
    async def revoke_session(self, request: Request) -> Response:
        """Revoke a specific session"""
        session_id = request.path_params["session_id"]
        session_store = await get_session_store()
        
        try:
            success = await session_store.delete_session(session_id)
            
            if success:
                return JSONResponse({
                    "success": True,
                    "message": f"Session {session_id[:8]}... revoked successfully"
                })
            else:
                return JSONResponse({
                    "success": False,
                    "message": "Session not found or already expired"
                }, status_code=404)
                
        except Exception as e:
            return JSONResponse({
                "success": False,
                "message": f"Error revoking session: {str(e)}"
            }, status_code=500)
    
    @expose("/sessions/revoke-user/{user_id:int}", methods=["POST"])
    async def revoke_user_sessions(self, request: Request) -> Response:
        """Revoke all sessions for a specific user"""
        user_id = request.path_params["user_id"]
        session_store = await get_session_store()
        
        try:
            # Get all session keys
            keys = await session_store.redis.keys("session:*")
            revoked_count = 0
            
            for key in keys:
                session_data = await session_store.redis.get(key)
                if session_data:
                    try:
                        data = json.loads(session_data)
                        if data.get('id') == user_id:
                            session_id = key.decode('utf-8').replace('session:', '')
                            await session_store.delete_session(session_id)
                            revoked_count += 1
                    except json.JSONDecodeError:
                        continue
            
            return JSONResponse({
                "success": True,
                "message": f"Revoked {revoked_count} sessions for user {user_id}"
            })
            
        except Exception as e:
            return JSONResponse({
                "success": False,
                "message": f"Error revoking user sessions: {str(e)}"
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
            
        except Exception as e:
            return Response(
                content=f"<div class='alert alert-danger'>Error loading stats: {str(e)}</div>",
                media_type="text/html"
            )
    
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
    
    @expose("/analytics", methods=["GET"])
    async def analytics_dashboard(self, request: Request) -> Response:
        """Show user analytics dashboard"""
        
        try:
            async for db in get_db():
                # Get user statistics
                from sqlalchemy import func, text
                from app.models.user import User
                
                # Total users
                total_users = await db.scalar(
                    func.count(User.id)
                )
                
                # Users by approval status
                pending_users = await db.scalar(
                    func.count(User.id).filter(User.approval_status == 'pending')
                )
                
                approved_users = await db.scalar(
                    func.count(User.id).filter(User.approval_status == 'approved')
                )
                
                denied_users = await db.scalar(
                    func.count(User.id).filter(User.approval_status == 'denied')
                )
                
                # Verified users
                verified_users = await db.scalar(
                    func.count(User.id).filter(User.is_verified == True)
                )
                
                unverified_users = await db.scalar(
                    func.count(User.id).filter(User.is_verified == False)
                )
                
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