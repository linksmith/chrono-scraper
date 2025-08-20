"""
WebSocket endpoints for real-time updates
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_from_websocket
from app.core.websocket import connection_manager
from app.models.user import User
from app.models.project import Project
from app.services.projects import ProjectService
from app.services.session_store import get_session_store
from sqlmodel import select

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/dashboard/{user_id}")
async def dashboard_websocket(
    websocket: WebSocket,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time dashboard updates
    """
    try:
        # Verify user exists and get user info
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Connect to dashboard
        await connection_manager.connect_dashboard(websocket, user_id)
        
        # Send initial dashboard data
        await send_dashboard_update(user_id, db)
        
        try:
            while True:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                message_type = message.get("type")
                if message_type == "request_update":
                    await send_dashboard_update(user_id, db)
                elif message_type == "subscribe_project":
                    project_id = message.get("project_id")
                    if project_id:
                        await send_project_status(user_id, project_id, db)
                
        except WebSocketDisconnect:
            logger.info(f"Dashboard WebSocket disconnected for user {user_id}")
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Invalid JSON format"
            }))
        except Exception as e:
            logger.error(f"Error in dashboard WebSocket for user {user_id}: {e}")
            
    finally:
        connection_manager.disconnect(websocket)


@router.websocket("/project/{project_id}/user/{user_id}")
async def project_websocket(
    websocket: WebSocket,
    project_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time project progress updates
    """
    try:
        # Verify user exists
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Verify user has access to project
        project = await ProjectService.get_project(db, project_id, user_id)
        if not project:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Connect to project
        await connection_manager.connect_project(websocket, user_id, project_id)
        
        # Send initial project status
        await send_project_status(user_id, project_id, db)
        
        try:
            while True:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                message_type = message.get("type")
                if message_type == "request_status":
                    await send_project_status(user_id, project_id, db)
                elif message_type == "request_url_progress":
                    await send_url_progress(user_id, project_id, db)
                
        except WebSocketDisconnect:
            logger.info(f"Project WebSocket disconnected for user {user_id}, project {project_id}")
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Invalid JSON format"
            }))
        except Exception as e:
            logger.error(f"Error in project WebSocket for user {user_id}, project {project_id}: {e}")
            
    finally:
        connection_manager.disconnect(websocket)


@router.websocket("/scrape/{scrape_session_id}")
async def scraping_progress_websocket(
    websocket: WebSocket,
    scrape_session_id: int,
    token: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time scraping progress updates.
    Delegates connection management to the central WebSocket manager so that
    CDX discovery, page progress, processing stages, and session stats are
    broadcast properly from background tasks.
    """
    try:
        # Authenticate user
        session_store = await get_session_store()
        current_user = await get_current_user_from_websocket(
            websocket, token, session_id, db, session_store
        )
        if not current_user:
            logger.warning(
                f"WebSocket auth failed for session {scrape_session_id} - token: {bool(token)}, session_id: {bool(session_id)}"
            )
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Verify access to scrape session
        from app.models.project import ScrapeSession
        session_result = await db.execute(
            select(ScrapeSession).where(ScrapeSession.id == scrape_session_id)
        )
        session = session_result.scalar_one_or_none()
        if not session:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Verify project ownership
        project = await ProjectService.get_project_by_id(db, session.project_id, current_user.id)
        if not project:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Delegate to WebSocket manager that is used by Celery broadcast helpers
        from app.services.websocket_service import handle_websocket_connection
        await handle_websocket_connection(websocket, current_user.id, scrape_session_id)

    except Exception as e:
        logger.error(
            f"Failed to establish scraping progress WebSocket for session {scrape_session_id}: {e}"
        )
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_SERVER_ERROR)
        except Exception:
            pass


async def send_scraping_status(scrape_session_id: int, websocket: WebSocket, db: AsyncSession):
    """Send current scraping status to WebSocket client"""
    try:
        from app.models.project import ScrapeSession
        from app.models.scraping import ScrapePage
        
        # Get scrape session
        session_result = await db.execute(
            select(ScrapeSession).where(ScrapeSession.id == scrape_session_id)
        )
        session = session_result.scalar_one_or_none()
        
        if not session:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Scrape session not found"
            }))
            return
        
        # Get scrape pages statistics
        pages_result = await db.execute(
            select(ScrapePage).where(ScrapePage.scrape_session_id == scrape_session_id)
        )
        pages = pages_result.scalars().all()
        
        # Calculate statistics
        total_pages = len(pages)
        completed_pages = sum(1 for p in pages if p.status == 'completed')
        failed_pages = sum(1 for p in pages if p.status == 'failed')
        in_progress_pages = sum(1 for p in pages if p.status == 'in_progress')
        pending_pages = sum(1 for p in pages if p.status == 'pending')
        
        progress_percentage = (completed_pages / total_pages * 100) if total_pages > 0 else 0
        
        status_data = {
            "type": "session_stats",
            "data": {
                "scrape_session_id": scrape_session_id,
                "total_urls": total_pages,
                "pending_urls": pending_pages,
                "in_progress_urls": in_progress_pages,
                "completed_urls": completed_pages,
                "failed_urls": failed_pages,
                "skipped_urls": 0,  # Calculate if needed
                "progress_percentage": progress_percentage,
                "active_domains": 1,  # Simplified for now
                "completed_domains": 1 if session.status == 'completed' else 0,
                "failed_domains": 1 if session.status == 'failed' else 0,
                "session_status": session.status.value if hasattr(session.status, 'value') else str(session.status),
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "completed_at": session.completed_at.isoformat() if session.completed_at else None
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await websocket.send_text(json.dumps(status_data))
        
    except Exception as e:
        logger.error(f"Error sending scraping status for session {scrape_session_id}: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Failed to get session status: {str(e)}"
        }))


async def send_dashboard_update(user_id: int, db: AsyncSession):
    """Send dashboard update to user"""
    try:
        # Get user's projects
        projects_result = await db.execute(
            select(Project).where(Project.user_id == user_id)
        )
        projects = projects_result.scalars().all()
        
        # Calculate metrics
        total_projects = len(projects)
        active_scrapes = sum(1 for p in projects if p.status == "running")
        
        # Get recent activity (placeholder for now)
        recent_activity = []  # TODO: Implement activity log
        
        dashboard_data = {
            "type": "dashboard_update",
            "data": {
                "metrics": {
                    "total_projects": total_projects,
                    "active_scrapes": active_scrapes,
                },
                "recent_activity": recent_activity,
            }
        }
        
        await connection_manager.send_to_user(user_id, dashboard_data)
        
    except Exception as e:
        logger.error(f"Error sending dashboard update to user {user_id}: {e}")


async def send_project_status(user_id: int, project_id: int, db: AsyncSession):
    """Send project status update"""
    try:
        project = await ProjectService.get_project(db, project_id, user_id)
        if not project:
            return
        
        # Get project statistics
        stats = await ProjectService.get_project_stats(db, project_id)
        
        project_data = {
            "type": "project_status",
            "project_id": project_id,
            "data": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "total_pages": stats.get("total_pages", 0),
                "completed_pages": stats.get("completed_pages", 0),
                "failed_pages": stats.get("failed_pages", 0),
                "progress_percentage": stats.get("progress_percentage", 0),
                "last_updated": project.updated_at.isoformat() if project.updated_at else None
            }
        }
        
        await connection_manager.send_to_project(project_id, project_data)
        
    except Exception as e:
        logger.error(f"Error sending project status for project {project_id}: {e}")


async def send_url_progress(user_id: int, project_id: int, db: AsyncSession):
    """Send URL progress update"""
    try:
        # Get recent pages for project (placeholder)
        url_progress = []  # TODO: Implement page tracking
        
        progress_data = {
            "type": "url_progress",
            "project_id": project_id,
            "data": url_progress
        }
        
        await connection_manager.send_to_project(project_id, progress_data)
        
    except Exception as e:
        logger.error(f"Error sending URL progress for project {project_id}: {e}")


# Utility functions for broadcasting updates from other parts of the application
async def broadcast_project_update(project_id: int, update_data: Dict[str, Any]):
    """Broadcast project update to all connected clients"""
    message = {
        "type": "project_update",
        "project_id": project_id,
        "data": update_data
    }
    await connection_manager.send_to_project(project_id, message)


async def broadcast_scrape_progress(project_id: int, progress_data: Dict[str, Any]):
    """Broadcast scrape progress update"""
    message = {
        "type": "scrape_progress",
        "project_id": project_id,
        "progress": progress_data
    }
    await connection_manager.send_to_project(project_id, message)


async def broadcast_url_completed(project_id: int, url_data: Dict[str, Any]):
    """Broadcast URL completion"""
    message = {
        "type": "url_completed",
        "project_id": project_id,
        "url_data": url_data
    }
    await connection_manager.send_to_project(project_id, message)


async def broadcast_session_completed(project_id: int, session_data: Dict[str, Any]):
    """Broadcast scraping session completion"""
    message = {
        "type": "session_completed",
        "project_id": project_id,
        "session_data": session_data
    }
    await connection_manager.send_to_project(project_id, message)