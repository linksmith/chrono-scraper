"""
Health check endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.core.database import get_db

router = APIRouter()


@router.get("/status")
async def health_status() -> dict[str, Any]:
    """
    Basic health check
    """
    return {
        "status": "healthy",
        "service": "chrono-scraper-api"
    }


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Database health check
    """
    try:
        # Simple query to check database connection
        result = await db.execute("SELECT 1")
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }