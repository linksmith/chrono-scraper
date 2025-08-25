"""
Admin dashboard API endpoints
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_superuser, get_db
from app.admin.views.dashboard import router as dashboard_router

# Re-export the dashboard router
router = dashboard_router