"""
Meilisearch index-related Celery tasks
"""
import asyncio
from datetime import datetime
from typing import List, Dict, Any

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.project import Project, ProjectStatus
from app.services.meilisearch_service import MeilisearchService


@celery_app.task(bind=True, name="app.tasks.index_tasks.add_documents_to_index")
def add_documents_to_index(self, project_id: int, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Add documents to project index
    """
    try:
        async def _add_documents():
            async with AsyncSessionLocal() as db:
                # Get project
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": 0,
                        "total": len(documents),
                        "status": f"Adding {len(documents)} documents to index..."
                    }
                )
                
                # Add documents to Meilisearch
                success = await MeilisearchService.add_documents(project, documents)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": len(documents),
                        "total": len(documents),
                        "status": "Documents added successfully"
                    }
                )
                
                return {
                    "project_id": project_id,
                    "documents_added": len(documents),
                    "success": success,
                    "status": "completed"
                }
        
        return asyncio.run(_add_documents())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.index_tasks.update_documents_in_index")
def update_documents_in_index(self, project_id: int, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Update documents in project index
    """
    try:
        async def _update_documents():
            async with AsyncSessionLocal() as db:
                # Get project
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": 0,
                        "total": len(documents),
                        "status": f"Updating {len(documents)} documents in index..."
                    }
                )
                
                # Update documents in Meilisearch
                success = await MeilisearchService.update_documents(project, documents)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": len(documents),
                        "total": len(documents),
                        "status": "Documents updated successfully"
                    }
                )
                
                return {
                    "project_id": project_id,
                    "documents_updated": len(documents),
                    "success": success,
                    "status": "completed"
                }
        
        return asyncio.run(_update_documents())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.index_tasks.delete_documents_from_index")
def delete_documents_from_index(self, project_id: int, document_ids: List[str]) -> Dict[str, Any]:
    """
    Delete documents from project index
    """
    try:
        async def _delete_documents():
            async with AsyncSessionLocal() as db:
                # Get project
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": 0,
                        "total": len(document_ids),
                        "status": f"Deleting {len(document_ids)} documents from index..."
                    }
                )
                
                # Delete documents from Meilisearch
                success = await MeilisearchService.delete_documents(project, document_ids)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={
                        "current": len(document_ids),
                        "total": len(document_ids),
                        "status": "Documents deleted successfully"
                    }
                )
                
                return {
                    "project_id": project_id,
                    "documents_deleted": len(document_ids),
                    "success": success,
                    "status": "completed"
                }
        
        return asyncio.run(_delete_documents())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(name="app.tasks.index_tasks.health_check_indexes")
def health_check_indexes() -> Dict[str, Any]:
    """
    Periodic health check for all project indexes
    """
    try:
        async def _health_check():
            async with AsyncSessionLocal() as db:
                # Get all projects with indexes
                result = await db.execute(
                    select(Project).where(
                        Project.status.in_([ProjectStatus.INDEXED, ProjectStatus.INDEXING])
                    )
                )
                projects = result.scalars().all()
                
                healthy_count = 0
                unhealthy_count = 0
                results = []
                
                for project in projects:
                    try:
                        stats = await MeilisearchService.get_index_stats(project)
                        
                        if stats.get("number_of_documents", 0) >= 0:
                            healthy_count += 1
                            status = "healthy"
                        else:
                            unhealthy_count += 1
                            status = "unhealthy"
                            
                        results.append({
                            "project_id": project.id,
                            "index_name": MeilisearchService.get_index_name(project),
                            "status": status,
                            "document_count": stats.get("number_of_documents", 0)
                        })
                        
                    except Exception as e:
                        unhealthy_count += 1
                        results.append({
                            "project_id": project.id,
                            "index_name": MeilisearchService.get_index_name(project),
                            "status": "error",
                            "error": str(e)
                        })
                
                return {
                    "total_indexes": len(projects),
                    "healthy_count": healthy_count,
                    "unhealthy_count": unhealthy_count,
                    "results": results,
                    "checked_at": datetime.utcnow().isoformat()
                }
        
        return asyncio.run(_health_check())
        
    except Exception as exc:
        raise exc


@celery_app.task(bind=True, name="app.tasks.index_tasks.reindex_project_documents")
def reindex_project_documents(self, project_id: int) -> Dict[str, Any]:
    """
    Reindex all documents for a project from the database
    """
    try:
        async def _reindex_documents():
            async with AsyncSessionLocal() as db:
                # Get project
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                
                if not project:
                    raise Exception(f"Project {project_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 4, "status": "Rebuilding index..."}
                )
                
                # Rebuild index
                success = await MeilisearchService.rebuild_index(project)
                
                if not success:
                    raise Exception("Failed to rebuild index")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 2, "total": 4, "status": "Gathering documents from database..."}
                )
                
                # Get all pages for the project
                from app.models.project import Page, Domain
                
                result = await db.execute(
                    select(Page)
                    .join(Domain)
                    .where(Domain.project_id == project_id)
                    .where(Page.processed == True)
                )
                pages = result.scalars().all()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 3, "total": 4, "status": f"Indexing {len(pages)} documents..."}
                )
                
                # Convert pages to documents
                documents = []
                for page in pages:
                    if page.content:  # Only index pages with content
                        doc = {
                            "id": str(page.id),
                            "title": page.title or "",
                            "content": page.content,
                            "original_url": page.original_url,
                            "wayback_url": page.wayback_url or "",
                            "domain_id": page.domain_id,
                            "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                            "unix_timestamp": page.unix_timestamp,
                            "mime_type": page.mime_type or "",
                            "status_code": page.status_code,
                            "processed": page.processed,
                            "indexed": True
                        }
                        documents.append(doc)
                
                # Add documents to index in batches
                batch_size = 100
                total_added = 0
                
                for i in range(0, len(documents), batch_size):
                    batch = documents[i:i + batch_size]
                    await MeilisearchService.add_documents(project, batch)
                    total_added += len(batch)
                
                # Update pages as indexed
                for page in pages:
                    page.indexed = True
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 4, "total": 4, "status": "Reindexing completed"}
                )
                
                return {
                    "project_id": project_id,
                    "total_documents": len(documents),
                    "documents_indexed": total_added,
                    "status": "completed"
                }
        
        return asyncio.run(_reindex_documents())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc