"""
Health check endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any

from app.core.database import get_db
from app.core.config import settings

router = APIRouter()


@router.get("/")
async def root_health() -> dict[str, Any]:
	return {"status": "ok", "version": settings.VERSION}


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
		await db.execute("SELECT 1")
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