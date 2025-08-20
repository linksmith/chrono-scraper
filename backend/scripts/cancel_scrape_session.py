#!/usr/bin/env python3
"""
Utility: Cancel a running scrape session by ID.

Actions performed:
- Revoke Celery tasks for Firecrawl scraping whose args reference the given session ID
- Mark the ScrapeSession as CANCELLED in the database
"""

import sys
import ast
from datetime import datetime

from app.tasks.celery_app import celery_app
from app.tasks.firecrawl_scraping import get_sync_session
from app.models.project import ScrapeSession, ScrapeSessionStatus, Project, ProjectStatus


def extract_args(arg_str):
    """Safely parse Celery args string into a tuple."""
    if not isinstance(arg_str, str):
        return ()
    try:
        value = ast.literal_eval(arg_str)
        if isinstance(value, tuple):
            return value
        return (value,)
    except Exception:
        return ()


def maybe_revoke(tasks_dict, session_id: int) -> int:
    """Revoke relevant tasks from a Celery inspect dictionary; return count revoked."""
    if not tasks_dict:
        return 0
    revoked = 0
    for _worker, tasks in tasks_dict.items():
        for t in tasks:
            name = t.get("name") or t.get("type") or ""
            args_str = t.get("args") or ""
            task_id = t.get("id") or (t.get("request") or {}).get("id")
            args_tuple = extract_args(args_str)

            try:
                # Firecrawl scraping task signature: (domain_id, scrape_session_id)
                if name.endswith("firecrawl_scraping.scrape_domain_with_firecrawl"):
                    if len(args_tuple) >= 2 and args_tuple[1] == session_id and task_id:
                        celery_app.control.revoke(task_id, terminate=True)
                        revoked += 1
            except Exception:
                # Best-effort; ignore per-task errors
                pass
    return revoked


def main():
    if len(sys.argv) < 2:
        print("Usage: cancel_scrape_session.py <session_id>")
        sys.exit(1)

    try:
        session_id = int(sys.argv[1])
    except ValueError:
        print("Session ID must be an integer")
        sys.exit(1)

    inspect = celery_app.control.inspect()
    total_revoked = 0
    try:
        total_revoked += maybe_revoke(getattr(inspect, "active")(), session_id)
        total_revoked += maybe_revoke(getattr(inspect, "scheduled")(), session_id)
        total_revoked += maybe_revoke(getattr(inspect, "reserved")(), session_id)
    except Exception:
        # Continue to DB update even if inspect fails
        pass

    db = get_sync_session()
    try:
        session = db.get(ScrapeSession, session_id)
        if session:
            session.status = ScrapeSessionStatus.CANCELLED
            session.completed_at = session.completed_at or datetime.utcnow()
            if not getattr(session, "error_message", None):
                session.error_message = "Cancelled by admin request"

            # Also set the parent project's status to PAUSED for clear UI feedback
            project = db.get(Project, session.project_id)
            if project:
                project.status = ProjectStatus.PAUSED

            db.commit()
        print(f"Cancelled session {session_id}. Revoked {total_revoked} tasks.")
    finally:
        db.close()


if __name__ == "__main__":
    main()


