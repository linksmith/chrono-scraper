#!/usr/bin/env python3
"""
Script to fix project 110 by ensuring it has proper domains and scraping configuration.
"""

import sys
import os

# Add backend to path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, text
from app.models.project import Project, Domain, ScrapeSession
from app.models.project import DomainStatus
from app.core.config import settings

async def fix_project_110():
    """Fix project 110 configuration"""
    print("🔧 Fixing Project 110 Configuration")
    print("=" * 50)

    try:
        # Create database connection
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            print("📊 Database Connection: ✅")

            # Check current project status
            result = await session.execute(
                select(Project).where(Project.id == 110)
            )
            project = result.scalar_one_or_none()

            if not project:
                print("❌ Project 110 not found!")
                return

            print(f"📁 Project: {project.name}")
            print(f"   Status: {project.status}")
            print(f"   Process Documents: {project.process_documents}")

            # Check existing domains
            result = await session.execute(
                select(Domain).where(Domain.project_id == 110)
            )
            domains = result.all()

            print(f"🌐 Existing Domains: {len(domains)}")
            for domain in domains:
                print(f"   - {domain.domain} (Status: {domain.status}, Active: {getattr(domain, 'active', True)})")

            # If no domains exist, we need to add one
            if len(domains) == 0:
                print("⚠️  No domains found, adding example.com...")

                # Add a test domain
                new_domain = Domain(
                    project_id=110,
                    domain="example.com",
                    match_type="domain",
                    status=DomainStatus.ACTIVE,
                    active=True
                )

                session.add(new_domain)
                await session.commit()
                await session.refresh(new_domain)

                print(f"✅ Added domain: {new_domain.domain} (ID: {new_domain.id})")

            # Check if there are any scrape sessions
            result = await session.execute(
                select(ScrapeSession).where(ScrapeSession.project_id == 110)
            )
            sessions = result.all()

            print(f"⚡ Existing Scrape Sessions: {len(sessions)}")
            for session in sessions:
                print(f"   - Session {session.id}: Status={session.status}")

            # If no sessions exist, the scraping wasn't initiated properly
            if len(sessions) == 0:
                print("⚠️  No scrape sessions found. The scraping initiation may have failed.")
                print("   This could be due to the Meilisearch error we saw earlier.")

            # Check if we can manually trigger a scraping task
            print("\n🔄 Testing Manual Scraping Task...")

            try:
                from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
                from app.tasks.celery_app import celery_app

                # Get the first domain
                domains = [d for d in domains if d.status == DomainStatus.ACTIVE and getattr(d, 'active', True)]

                if domains:
                    domain = domains[0]

                    # Create a scrape session if needed
                    if len(sessions) == 0:
                        from app.services.scrape_session_service import ScrapeSessionService
                        from datetime import datetime

                        # Create a session manually
                        session_obj = ScrapeSession(
                            project_id=110,
                            status="running",
                            created_at=datetime.utcnow()
                        )
                        session.add(session_obj)
                        await session.commit()
                        await session.refresh(session_obj)

                        print(f"✅ Created scrape session: {session_obj.id}")

                    # Try to manually queue a scraping task
                    print(f"🚀 Manually queuing scraping task for domain {domain.id}...")

                    # This would normally be done with .delay() but let's check if the task is available
                    task = scrape_domain_with_firecrawl.delay(domain.id, session_obj.id if 'session_obj' in locals() else sessions[0].id)

                    print(f"✅ Task queued with ID: {task.id}")
                    print("   Check Celery worker logs to see if it's being processed.")

                else:
                    print("❌ No active domains found to scrape")

            except Exception as e:
                print(f"❌ Error with manual task: {e}")

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Database URL: {settings.DATABASE_URL}")

    print("\n💡 Next Steps:")
    print("1. Check if domains were added successfully")
    print("2. Monitor Celery worker logs for scraping tasks")
    print("3. Check if the Meilisearch error is blocking scraping")

if __name__ == "__main__":
    asyncio.run(fix_project_110())
