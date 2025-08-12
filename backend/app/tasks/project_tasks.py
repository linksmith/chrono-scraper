"""
Project-related Celery tasks
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.services.projects import ProjectService
from app.services.meilisearch_service import MeilisearchService


@celery_app.task(bind=True, name="app.tasks.project_tasks.create_project_index")
def create_project_index(self, project_id: int) -> Dict[str, Any]:
    """
    Create Meilisearch index for a project
    """
    try:
        async def _create_index():
            async with AsyncSessionLocal() as db:
                project = await ProjectService.get_project_by_id(db, project_id)
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                # Update task status
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 3, "status": "Creating index..."}
                )
                
                # Create Meilisearch index
                index_info = await MeilisearchService.create_project_index(project)
                
                # Update project with index info
                project.index_name = index_info["index_name"]
                project.index_search_key = index_info["search_key"]
                project.index_search_key_uid = index_info["search_key_uid"]
                project.status = ProjectStatus.INDEXED
                
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 3, "total": 3, "status": "Index created successfully"}
                )
                
                return {
                    "project_id": project_id,
                    "index_name": index_info["index_name"],
                    "status": "completed"
                }
        
        return asyncio.run(_create_index())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.project_tasks.delete_project_index")
def delete_project_index(self, project_id: int) -> Dict[str, Any]:
    """
    Delete Meilisearch index for a project
    """
    try:
        async def _delete_index():
            async with AsyncSessionLocal() as db:
                project = await ProjectService.get_project_by_id(db, project_id)
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 2, "status": "Deleting index..."}
                )
                
                # Delete Meilisearch index
                success = await MeilisearchService.delete_project_index(project)
                
                if success:
                    # Update project status
                    project.status = ProjectStatus.NO_INDEX
                    project.index_name = None
                    project.index_search_key = None
                    project.index_search_key_uid = None
                    
                    await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 2, "total": 2, "status": "Index deleted successfully"}
                )
                
                return {
                    "project_id": project_id,
                    "success": success,
                    "status": "completed"
                }
        
        return asyncio.run(_delete_index())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.project_tasks.rebuild_project_index")
def rebuild_project_index(self, project_id: int) -> Dict[str, Any]:
    """
    Rebuild Meilisearch index for a project
    """
    try:
        async def _rebuild_index():
            async with AsyncSessionLocal() as db:
                project = await ProjectService.get_project_by_id(db, project_id)
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 4, "status": "Starting rebuild..."}
                )
                
                # Delete existing index
                await MeilisearchService.delete_project_index(project)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 2, "total": 4, "status": "Creating new index..."}
                )
                
                # Create new index
                index_info = await MeilisearchService.create_project_index(project)
                
                # Update project
                project.index_name = index_info["index_name"]
                project.index_search_key = index_info["search_key"]
                project.index_search_key_uid = index_info["search_key_uid"]
                project.status = ProjectStatus.INDEXED
                
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 4, "total": 4, "status": "Rebuild completed"}
                )
                
                return {
                    "project_id": project_id,
                    "index_name": index_info["index_name"],
                    "status": "completed"
                }
        
        return asyncio.run(_rebuild_index())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(name="app.tasks.project_tasks.cleanup_old_tasks")
def cleanup_old_tasks() -> Dict[str, Any]:
    """
    Cleanup old completed tasks (periodic task)
    """
    try:
        # This would typically clean up old task results from Redis
        # For now, just log that the cleanup ran
        
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        return {
            "status": "completed",
            "cutoff_date": cutoff_date.isoformat(),
            "message": "Old tasks cleanup completed"
        }
        
    except Exception as exc:
        raise exc


@celery_app.task(bind=True, name="app.tasks.project_tasks.bulk_update_project_status")
def bulk_update_project_status(self, project_ids: List[int], status: str) -> Dict[str, Any]:
    """
    Bulk update multiple projects' status
    """
    try:
        async def _bulk_update():
            results = []
            
            async with AsyncSessionLocal() as db:
                for i, project_id in enumerate(project_ids):
                    current_task.update_state(
                        state="PROGRESS",
                        meta={
                            "current": i + 1,
                            "total": len(project_ids),
                            "status": f"Updating project {project_id}..."
                        }
                    )
                    
                    project = await ProjectService.get_project_by_id(db, project_id)
                    if project:
                        project.status = ProjectStatus(status)
                        results.append({"project_id": project_id, "success": True})
                    else:
                        results.append({"project_id": project_id, "success": False, "error": "Not found"})
                
                await db.commit()
            
            return {
                "updated_count": len([r for r in results if r["success"]]),
                "failed_count": len([r for r in results if not r["success"]]),
                "results": results,
                "status": "completed"
            }
        
        return asyncio.run(_bulk_update())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.project_tasks.generate_project_report")
def generate_project_report(self, project_id: int, user_id: int) -> Dict[str, Any]:
    """
    Generate comprehensive project report
    """
    try:
        async def _generate_report():
            async with AsyncSessionLocal() as db:
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 5, "status": "Gathering project data..."}
                )
                
                # Get project
                project = await ProjectService.get_project_by_id(db, project_id, user_id)
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 2, "total": 5, "status": "Gathering statistics..."}
                )
                
                # Get project stats
                stats = await ProjectService.get_project_stats(db, project_id)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 3, "total": 5, "status": "Getting index statistics..."}
                )
                
                # Get Meilisearch stats
                index_stats = await MeilisearchService.get_index_stats(project)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 4, "total": 5, "status": "Compiling report..."}
                )
                
                # Compile report
                report = {
                    "project": {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                        "status": project.status,
                        "created_at": project.created_at.isoformat(),
                        "updated_at": project.updated_at.isoformat()
                    },
                    "statistics": stats,
                    "index_stats": index_stats,
                    "generated_at": datetime.utcnow().isoformat()
                }
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 5, "total": 5, "status": "Report completed"}
                )
                
                return report
        
        return asyncio.run(_generate_report())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc