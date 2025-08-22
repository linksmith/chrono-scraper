#!/usr/bin/env python3
"""
Diagnostic script to check project 110 and understand why scraping isn't working.
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select
from app.models.project import Project, Domain
from app.models.project import ScrapeSession, ScrapeSessionStatus
from app.core.config import settings

async def diagnose_project_110():
    """Diagnose what's wrong with project 110"""
    print("🔍 Diagnosing Project 110 Issues")
    print("=" * 50)

    try:
        # Create database connection
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            print("📊 Database Connection: ✅")

            # Check if project exists
            result = await session.execute(
                select(Project).where(Project.id == 110)
            )
            project = result.scalar_one_or_none()

            if not project:
                print("❌ Project 110 not found!")
                return

            print(f"📁 Project: {project.name} (ID: {project.id})")
            print(f"   Status: {project.status}")
            print(f"   Process Documents: {project.process_documents}")

            # Check domains for this project
            result = await session.execute(
                select(Domain).where(Domain.project_id == 110)
            )
            domains = result.all()

            print(f"🌐 Domains: {len(domains)} found")
            for domain in domains:
                print(f"   - {domain.domain} (Status: {domain.status}, Active: {getattr(domain, 'active', True)})")

            # Check scrape sessions
            result = await session.execute(
                select(ScrapeSession).where(ScrapeSession.project_id == 110)
            )
            sessions = result.all()

            print(f"⚡ Scrape Sessions: {len(sessions)} found")
            for session in sessions:
                print(f"   - Session {session.id}: Status={session.status}, Started={session.created_at}")

            # Check if there are any scrape pages
            from app.models.scraping import ScrapePage
            result = await session.execute(
                text("SELECT COUNT(*) FROM scrape_pages WHERE domain_id IN (SELECT id FROM domains WHERE project_id = 110)")
            )
            scrape_pages_count = result.scalar()

            print(f"📄 Scrape Pages: {scrape_pages_count} found")

            # Check Celery task queue
            print("\n🔄 Checking Celery Tasks...")
            try:
                from app.tasks.celery_app import celery_app
                # Check active tasks
                inspect = celery_app.control.inspect()
                active_tasks = inspect.active()
                scheduled_tasks = inspect.scheduled()
                reserved_tasks = inspect.reserved()

                print(f"   Active Tasks: {len(active_tasks) if active_tasks else 0}")
                print(f"   Scheduled Tasks: {len(scheduled_tasks) if scheduled_tasks else 0}")
                print(f"   Reserved Tasks: {len(reserved_tasks) if reserved_tasks else 0}")

                # Look for scraping tasks specifically
                if active_tasks:
                    for worker, tasks in active_tasks.items():
                        for task in tasks:
                            if 'scrape' in task.get('name', '').lower():
                                print(f"   📊 Active Scraping Task: {task.get('name')}")

            except Exception as e:
                print(f"   ❌ Celery inspection failed: {e}")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Database URL: {settings.DATABASE_URL}")
        print("   Make sure the database is accessible")

    print("\n💡 Diagnosis Complete")
    print("If no domains or scrape sessions exist, the scraping wasn't properly initiated.")
    print("If domains exist but no scraping tasks are running, there might be a Celery configuration issue.")

if __name__ == "__main__":
    asyncio.run(diagnose_project_110())
