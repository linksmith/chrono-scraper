"""
Admin dashboard API endpoints
"""

from app.admin.views.dashboard import router as dashboard_router

# Re-export the dashboard router
router = dashboard_router