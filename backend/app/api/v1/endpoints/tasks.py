"""
Task management endpoints
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from celery.result import AsyncResult

from app.api.deps import get_current_approved_user, require_permission
from app.models.user import User
from app.models.rbac import PermissionType
from app.core.celery_app import celery_app
from app.tasks.project_tasks import (
    create_project_index,
    delete_project_index,
    rebuild_project_index,
    bulk_update_project_status,
    generate_project_report
)
from app.tasks.index_tasks import (
    add_documents_to_index,
    update_documents_in_index,
    delete_documents_from_index,
    reindex_project_documents
)

router = APIRouter()


@router.post("/projects/{project_id}/index/create")
async def create_project_index_task(
    project_id: int,
    current_user: User = Depends(require_permission(PermissionType.PROJECT_MANAGE))
) -> Dict[str, Any]:
    """
    Start task to create project index
    """
    task = create_project_index.delay(project_id)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "status": "started",
        "message": "Index creation task started"
    }


@router.delete("/projects/{project_id}/index")
async def delete_project_index_task(
    project_id: int,
    current_user: User = Depends(require_permission(PermissionType.PROJECT_MANAGE))
) -> Dict[str, Any]:
    """
    Start task to delete project index
    """
    task = delete_project_index.delay(project_id)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "status": "started",
        "message": "Index deletion task started"
    }


@router.post("/projects/{project_id}/index/rebuild")
async def rebuild_project_index_task(
    project_id: int,
    current_user: User = Depends(require_permission(PermissionType.PROJECT_MANAGE))
) -> Dict[str, Any]:
    """
    Start task to rebuild project index
    """
    task = rebuild_project_index.delay(project_id)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "status": "started",
        "message": "Index rebuild task started"
    }


@router.post("/projects/{project_id}/documents/reindex")
async def reindex_project_documents_task(
    project_id: int,
    current_user: User = Depends(require_permission(PermissionType.PROJECT_MANAGE))
) -> Dict[str, Any]:
    """
    Start task to reindex all project documents
    """
    task = reindex_project_documents.delay(project_id)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "status": "started",
        "message": "Document reindexing task started"
    }


@router.post("/projects/{project_id}/documents/add")
async def add_documents_task(
    project_id: int,
    documents: List[Dict[str, Any]],
    current_user: User = Depends(require_permission(PermissionType.PROJECT_UPDATE))
) -> Dict[str, Any]:
    """
    Start task to add documents to project index
    """
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No documents provided"
        )
    
    task = add_documents_to_index.delay(project_id, documents)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "document_count": len(documents),
        "status": "started",
        "message": f"Adding {len(documents)} documents to index"
    }


@router.put("/projects/{project_id}/documents/update")
async def update_documents_task(
    project_id: int,
    documents: List[Dict[str, Any]],
    current_user: User = Depends(require_permission(PermissionType.PROJECT_UPDATE))
) -> Dict[str, Any]:
    """
    Start task to update documents in project index
    """
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No documents provided"
        )
    
    task = update_documents_in_index.delay(project_id, documents)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "document_count": len(documents),
        "status": "started",
        "message": f"Updating {len(documents)} documents in index"
    }


@router.delete("/projects/{project_id}/documents")
async def delete_documents_task(
    project_id: int,
    document_ids: List[str],
    current_user: User = Depends(require_permission(PermissionType.PROJECT_UPDATE))
) -> Dict[str, Any]:
    """
    Start task to delete documents from project index
    """
    if not document_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No document IDs provided"
        )
    
    task = delete_documents_from_index.delay(project_id, document_ids)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "document_count": len(document_ids),
        "status": "started",
        "message": f"Deleting {len(document_ids)} documents from index"
    }


@router.post("/projects/bulk-status-update")
async def bulk_update_project_status_task(
    project_ids: List[int],
    status: str,
    current_user: User = Depends(require_permission(PermissionType.ADMIN_MANAGE))
) -> Dict[str, Any]:
    """
    Start task to bulk update project status
    """
    if not project_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No project IDs provided"
        )
    
    task = bulk_update_project_status.delay(project_ids, status)
    
    return {
        "task_id": task.id,
        "project_count": len(project_ids),
        "new_status": status,
        "status": "started",
        "message": f"Bulk updating {len(project_ids)} projects"
    }


@router.post("/projects/{project_id}/report/generate")
async def generate_project_report_task(
    project_id: int,
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Start task to generate project report
    """
    task = generate_project_report.delay(project_id, current_user.id)
    
    return {
        "task_id": task.id,
        "project_id": project_id,
        "status": "started",
        "message": "Project report generation started"
    }


# Task monitoring endpoints
@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get task status and result
    """
    try:
        task_result = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": task_result.status,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
            "failed": task_result.failed() if task_result.ready() else None
        }
        
        if task_result.ready():
            if task_result.successful():
                response["result"] = task_result.result
            else:
                response["error"] = str(task_result.result)
        else:
            # Get progress info if available
            if hasattr(task_result, 'info') and task_result.info:
                response["progress"] = task_result.info
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting task status: {str(e)}"
        )


@router.delete("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Cancel a running task
    """
    try:
        celery_app.control.revoke(task_id, terminate=True)
        
        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": "Task cancellation requested"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error cancelling task: {str(e)}"
        )


@router.get("/active")
async def get_active_tasks(
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get list of active tasks
    """
    try:
        # Get active tasks from Celery
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        
        if not active_tasks:
            return {"active_tasks": {}, "total_active": 0}
        
        # Count total active tasks
        total_active = sum(len(tasks) for tasks in active_tasks.values())
        
        return {
            "active_tasks": active_tasks,
            "total_active": total_active
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting active tasks: {str(e)}"
        )


@router.get("/stats")
async def get_task_stats(
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get Celery task statistics
    """
    try:
        inspect = celery_app.control.inspect()
        
        stats = inspect.stats()
        active = inspect.active()
        scheduled = inspect.scheduled()
        reserved = inspect.reserved()
        
        return {
            "stats": stats or {},
            "active_count": sum(len(tasks) for tasks in (active or {}).values()),
            "scheduled_count": sum(len(tasks) for tasks in (scheduled or {}).values()),
            "reserved_count": sum(len(tasks) for tasks in (reserved or {}).values())
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting task stats: {str(e)}"
        )