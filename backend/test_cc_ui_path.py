#!/usr/bin/env python3
"""
Programmatic test to create a Common Crawl project and start a scrape using the
same code path the UI triggers (firecrawl_scraping task), bypassing the API.
"""
import asyncio
import logging
from typing import Optional

from sqlmodel import select


async def get_async_session():
    from app.core.database import get_db

    async for db in get_db():
        yield db
        break


async def ensure_test_user(db, email: str) -> Optional[int]:
    from app.models.user import User
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    return user.id if user else None


async def create_cc_project_with_domain(db, user_id: int) -> tuple[int, int]:
    """Create a Common Crawl project and add hetstoerwoud.nl domain. Returns (project_id, domain_id)."""
    from app.models.project import ProjectCreate, ArchiveSource, Project, Domain, DomainStatus

    # Create project via service (applies defaults/consistency)
    from app.services.projects import ProjectService

    project_create = ProjectCreate(
        name="Stoerwoud CC via UI Path",
        description="Programmatic CC project to mirror UI path.",
        process_documents=True,
        archive_source=ArchiveSource.COMMON_CRAWL,
        fallback_enabled=True,
    )
    project: Project = await ProjectService.create_project(db, project_create, user_id)

    # Add domain
    domain = Domain(
        project_id=project.id,
        domain_name="hetstoerwoud.nl",
        active=True,
        status=DomainStatus.ACTIVE,
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)

    return project.id, domain.id


async def create_scrape_session(db, project_id: int) -> int:
    from app.models.project import ScrapeSession, ScrapeSessionStatus

    session = ScrapeSession(
        project_id=project_id,
        status=ScrapeSessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session.id


def run_scrape(domain_id: int, session_id: int):
    """Queue the same Celery task (UI path) so it runs with a proper task_id/context."""
    from app.tasks.firecrawl_scraping import scrape_domain_with_intelligent_extraction

    logging.info(f"Queueing scrape task for domain_id={domain_id}, session_id={session_id}")
    # Queue via Celery so update_state works and worker picks it up
    async_result = scrape_domain_with_intelligent_extraction.apply_async(args=[domain_id, session_id])
    logging.info(f"Queued task id: {async_result.id}")
    return async_result.id


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.info("Starting CC UI-path test")

    # Prepare DB
    async for db in get_async_session():
        user_id = await ensure_test_user(db, "playwright@test.com")
        if not user_id:
            raise RuntimeError("Test user 'playwright@test.com' not found. Run the quick user creation from CLAUDE.md.")

        project_id, domain_id = await create_cc_project_with_domain(db, user_id)
        session_id = await create_scrape_session(db, project_id)

        logging.info(f"Created project_id={project_id}, domain_id={domain_id}, session_id={session_id}")

    # Run the scrape task synchronously (same path as UI queues)
    task_id = run_scrape(domain_id, session_id)
    logging.info(f"Scrape task queued with id={task_id}")


if __name__ == "__main__":
    asyncio.run(main())


