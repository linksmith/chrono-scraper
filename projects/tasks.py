import random
from datetime import datetime
from time import sleep
from typing import Any

from asgiref.sync import async_to_sync
from celery import chain, group, states
from celery.utils.log import get_task_logger
from channels.layers import get_channel_layer

from config import celery_app
from projects.enums import DomainStatusChoices, ProjectStatusChoices
from projects.wayback_machine_utils import (
    WaybackMachineException,
    create_page_from_wayback_machine,
    fetch_cdx_pages,
    get_wayback_machine_url,
)

# Get an instance of a logger
logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="projects.tasks.start_rebuild_project_index_task")
def start_rebuild_project_index_task(self, project_id: int):
    channel_layer = get_channel_layer()
    self.task_id = self.request.id
    logger.info(f"{project_id} with task_id: {self.task_id}")

    random_number = random.randint(1, 10)
    sleep(random_number)
    async_to_sync(channel_layer.group_send)(
        self.task_id,
        {
            "type": "celery_task_update",
            "message": {"progress": 0.1, "status": "Processing"},
        },
    )

    random_number = random.randint(1, 10)
    sleep(random_number)
    async_to_sync(channel_layer.group_send)(
        self.task_id,
        {
            "type": "celery_task_update",
            "message": {"progress": 0.3, "status": "Processing"},
        },
    )

    random_number = random.randint(1, 10)
    sleep(random_number)
    async_to_sync(channel_layer.group_send)(
        self.task_id,
        {
            "type": "celery_task_update",
            "message": {"progress": 0.5, "status": "Processing"},
        },
    )

    # Chain the tasks
    rebuild_project_index_task_chain = chain(
        set_project_status.si(project_id, ProjectStatusChoices.IN_PROGRESS),
        load_pages_from_wayback_machine_task.si(project_id),
        set_project_status_x.s(project_id),
    )

    rebuild_project_index_task_chain.apply_async()


@celery_app.task(bind=True, name="projects.tasks.load_pages_from_wayback_machine_task")
def load_pages_from_wayback_machine_task(self, project_id: int):
    from projects.models import Project

    project = Project.objects.get(id=project_id)
    project_domains = project.domains.filter(active=True, status=DomainStatusChoices.NO_INDEX)

    logger.info(f"Loading pages from project_id {project_id} - {project.name} with {len(project_domains)} domains...")

    load_pages_from_wayback_machine_task_group = group(
        start_load_pages_from_wayback_machine_task.s(
            domain.id, domain.domain_name, project.index_name, domain.from_date, domain.to_date
        )
        for domain in project_domains
    )

    load_pages_from_wayback_machine_task_group()

    return True


@celery_app.task(bind=True, name="projects.tasks.start_load_pages_from_wayback_machine_task")
def start_load_pages_from_wayback_machine_task(self, domain_id, domain_name, index_name, from_date, to_date):
    # convert from_date and to_date to string YYYYMMDD
    if from_date is not None and isinstance(from_date, datetime):
        from_date = from_date.strftime("%Y%m%d")
    else:
        # if to_date is None, use 01/01/1990
        from_date = "19900101"

    if to_date is not None and isinstance(from_date, datetime):
        to_date = to_date.strftime("%Y%m%d")
    else:
        # if to_date is None, use today
        to_date = datetime.now().strftime("%Y%m%d")

    logger.info(
        f"Loading pages from domain_id {domain_id} - {domain_name} "
        f"with index_name {index_name} and from_date {from_date} to_date {to_date}"
    )

    load_pages_from_wayback_machine_task_chain = chain(
        set_domain_status.si(domain_id, DomainStatusChoices.IN_PROGRESS),
        get_cdx_pages_and_filter_results.si(domain_id, domain_name, from_date, to_date),
        create_and_index_pages.s(domain_id, index_name),
        set_domain_status_x.s(domain_id),
    )

    load_pages_from_wayback_machine_task_chain()


@celery_app.task(bind=True, name="projects.tasks.create_and_index_pages")
def create_and_index_pages(self, cdx_pages, domain_id, index_name):
    if cdx_pages:
        create_and_index_pages_group = group(
            get_and_create_and_index_page.s(domain_id, cdx_page, index_name) for cdx_page in cdx_pages
        )
        create_and_index_pages_group()

        return True
    else:
        return False


@celery_app.task(bind=True, name="projects.tasks.get_cdx_pages_and_filter_results")
def get_cdx_pages_and_filter_results(
    self, domain_id: int, domain_name: str, from_date: str, to_date: str, batch_size: int = 1000
) -> list[tuple[Any, ...]] | None:
    logger.info("Fetching pages...")
    try:
        cdx_pages, resume_key = fetch_cdx_pages(domain_id, domain_name, from_date, to_date, batch_size)
    except WaybackMachineException as exc:
        self.update_state(
            state=states.FAILURE,
            meta={
                "exc_type": type(exc).__name__,
                "message": f"Error fetching pages for domain_id {domain_id}, domain_name {domain_name}",
                "domain_id": domain_id,
                "domain_name": domain_name,
                "from_date": from_date,
                "to_date": to_date,
                "batch_size": batch_size,
            },
        )
        return None

    if cdx_pages is None or resume_key is None:
        return None

    logger.info("Filtering out existing pages...")

    from projects.models import Page

    database_page_wayback_machine_urls = (
        Page.objects.filter(domain_id=domain_id).values_list("wayback_machine_url", flat=True).all()
    )

    filtered_pages = []
    for cdx_page in cdx_pages:
        wayback_machine_url = get_wayback_machine_url(cdx_page[0], cdx_page[1])
        if wayback_machine_url not in database_page_wayback_machine_urls:
            filtered_pages.append(cdx_page)

    fetched_page_count = len(cdx_pages)
    database_page_count = len(database_page_wayback_machine_urls)
    skipped_page_count = fetched_page_count - database_page_count
    filtered_page_count = len(filtered_pages)

    logger.info(f"Fetched pages: {fetched_page_count}")
    logger.info(f"Existing pages: {database_page_count}")
    logger.info(f"Skipped pages: {skipped_page_count}")
    logger.info(f"New (filtered) pages: {filtered_page_count}")

    self.update_state(
        state=states.SUCCESS,
        meta={
            # write message summarizing the results
            "message": "Pages fetched and filtered",  # write message summarizing the results
            "domain_id": domain_id,
            "domain_name": domain_name,
            "from_date": from_date,
            "to_date": to_date,
            "fetched_page_count": fetched_page_count,
            "database_page_count": database_page_count,
            "skipped_page_count": skipped_page_count,
            "filtered_page_count": filtered_page_count,
        },
    )

    return filtered_pages


@celery_app.task(bind=True, name="projects.tasks.get_and_create_and_index_page")
def get_and_create_and_index_page(self, domain_id: int, cdx_page, index_name: str):
    try:
        page, title, text = create_page_from_wayback_machine(domain_id, cdx_page)
        logger.info(f"Fetched and saved page {page.wayback_machine_url} for domain {domain_id}")
        page.add_to_index(index_name, title, text)

        self.update_state(
            state=states.SUCCESS, meta={"domain_id": domain_id, "wayback_machine_url": page.wayback_machine_url}
        )
    except WaybackMachineException:
        unix_timestamp = cdx_page[0]
        original_url = cdx_page[1]
        wayback_machine_url = get_wayback_machine_url(unix_timestamp, original_url)
        logger.error(f"Skipped page {wayback_machine_url} for domain {domain_id}")

        self.update_state(
            state=states.REJECTED,
            meta={"message": "SKIPPED page", "domain_id": domain_id, "wayback_machine_url": wayback_machine_url},
        )
    except Exception as exc:
        unix_timestamp = cdx_page[0]
        original_url = cdx_page[1]
        wayback_machine_url = get_wayback_machine_url(unix_timestamp, original_url)
        logger.exception(f"Skipped page due to error {wayback_machine_url} for domain {domain_id}")
        self.update_state(
            state=states.FAILURE,
            meta={
                "exc_type": type(exc).__name__,
                "message": "Error fetching page",
                "domain_id": domain_id,
                "wayback_machine_url": wayback_machine_url,
            },
        )


@celery_app.task(bind=True, name="projects.tasks.set_project_status")
def set_project_status(self, project_id: int, status: ProjectStatusChoices):
    logger.info(f"Set project {project_id} status to {status}...")

    if not project_id:
        logger.error("project_id is required")

    if not status:
        logger.error("status is required")

    from projects.models import Project

    project = Project.objects.get(id=project_id)
    old_status = project.status
    project.status = status
    project.save()

    self.update_state(
        state=states.SUCCESS,
        meta={
            "project_id": project_id,
            "project_name": project.name,
            "old_status": old_status,
            "new_status": project.status,
        },
    )

    return f"Status updated to {status} for project {project.name}"


@celery_app.task(bind=True, name="projects.tasks.set_project_status_x")
def set_project_status_x(self, project_indexed, project_id: int):
    if not project_indexed:
        logger.error("domain_indexed is required")

    if not project_id:
        logger.error("project_id is required")

    logger.info(f"Set status of project {project_id}...")

    from projects.models import Project

    project = Project.objects.get(id=project_id)
    old_status = project.status

    if project_indexed:
        project.status = ProjectStatusChoices.INDEXED
    else:
        project.status = ProjectStatusChoices.NO_INDEX

    project.save()

    self.update_state(
        state=states.SUCCESS,
        meta={
            "project_id": project_id,
            "project_name": project.name,
            "old_status": old_status,
            "new_status": project.status,
        },
    )

    return f"Status updated to {project.status} for project {project.name}"


@celery_app.task(bind=True, name="projects.tasks.set_domain_status")
def set_domain_status(self, domain_id: int, status: DomainStatusChoices):
    logger.info(f"Set domain {domain_id} status to {status}...")

    if not domain_id:
        logger.error("domain_id is required")

    if not status:
        logger.error("status is required")

    from projects.models import Domain

    domain = Domain.objects.get(id=domain_id)
    old_status = domain.status
    domain.status = status
    domain.save()

    self.update_state(
        state=states.SUCCESS,
        meta={
            "domain_id": domain_id,
            "domain_name": domain.domain_name,
            "old_status": old_status,
            "new_status": domain.status,
        },
    )

    return f"Status updated to {status} for project {domain.domain_name}"


@celery_app.task(bind=True, name="projects.tasks.set_domain_status_x")
def set_domain_status_x(self, domain_indexed, domain_id: int):
    if not domain_indexed:
        logger.error("domain_indexed is required")

    if not domain_id:
        logger.error("domain_id is required")

    logger.info(f"Set status of domain {domain_id}...")

    from projects.models import Domain

    domain = Domain.objects.get(id=domain_id)
    old_status = domain.status

    if domain_indexed:
        domain.status = DomainStatusChoices.INDEXED
    else:
        domain.status = DomainStatusChoices.NO_INDEX

    domain.save()

    self.update_state(
        state=states.SUCCESS,
        meta={
            "domain_id": domain_id,
            "domain_name": domain.domain_name,
            "old_status": old_status,
            "new_status": domain.status,
        },
    )

    return f"Status updated to {domain.status} for project {domain.domain_name}"
