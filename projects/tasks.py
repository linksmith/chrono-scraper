import logging
from datetime import datetime
from typing import Any

from celery import chain, chord, group

from config import celery_app
from projects.wayback_machine_utils import (
    NotEnoughContentException,
    WaybackMachineException,
    create_page_from_wayback_machine,
    fetch_cdx_pages,
    filter_out_existing_pages,
)

# Get an instance of a logger
logger = logging.getLogger(__name__)


def start_rebuild_project_index(project):
    from projects.models import StatusChoices

    set_project_status_in_progress(project.id)

    project_domains = project.domains.filter(active=True, status=StatusChoices.NO_INDEX)

    on_load_all_pages = group(
        start_load_pages_from_wayback_machine_task.s(
            domain.id, domain.domain_name, project.index_name, domain.from_date, domain.to_date
        )
        for domain in project_domains
    )

    # Create a chord with the group as the body and set_project_status_indexed as the callback
    workflow_chord = chord(on_load_all_pages)(set_project_status_indexed.s(project.id))

    # Run the chord
    result = workflow_chord.delay()

    return result


@celery_app.task()
def start_load_pages_from_wayback_machine_task(domain_id, domain_name, index_name, from_date, to_date):
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

    set_domain_status_in_progress(domain_id)

    get_pages_task = get_pages.s(domain_id, domain_name, from_date, to_date)
    get_and_create_and_index_pages_task_group = on_got_pages.s(domain_id, index_name)

    chain(get_pages_task, get_and_create_and_index_pages_task_group)()


@celery_app.task()
def on_got_pages(cdx_pages, domain_id, index_name):
    if cdx_pages:
        get_and_create_and_index_page_tasks = group(
            get_and_create_and_index_page.s(domain_id, cdx_page, index_name) for cdx_page in cdx_pages
        )
        chord(get_and_create_and_index_page_tasks)(set_domain_status_indexed.s(domain_id))


@celery_app.task()
def get_pages(domain_id: int, domain_name: str, from_date: str, to_date: str) -> list[tuple[Any, ...]] | None:
    try:
        cdx_pages = fetch_cdx_pages(domain_id, domain_name, from_date, to_date)
    except WaybackMachineException as error:
        logger.error(f"Error fetching pages for domain_id {domain_id}, ERROR: {error}")
        return None

    return filter_out_existing_pages(cdx_pages, domain_id)


@celery_app.task()
def get_and_create_and_index_page(domain_id: int, cdx_page, index_name: str):
    try:
        page, title, text = create_page_from_wayback_machine(domain_id, cdx_page)
        page.add_to_index(index_name, title, text)
    except NotEnoughContentException as error:
        logger.info(f"{error}")
    except WaybackMachineException as error:
        logger.debug(f"{error}")
    except Exception as error:
        logger.error(f"{error}")


@celery_app.task()
def set_domain_status_in_progress(domain_id: int):
    if not domain_id:
        logger.error("domain_id is required")

    from projects.models import Domain, StatusChoices

    domain = Domain.objects.get(id=domain_id)
    domain.status = StatusChoices.IN_PROGRESS
    domain.save()


@celery_app.task()
def set_domain_status_indexed(previous_task, domain_id: int):
    logger.info(previous_task)

    if not domain_id:
        logger.error("domain_id is required")

    from projects.models import Domain, StatusChoices

    domain = Domain.objects.get(id=domain_id)
    domain.status = StatusChoices.INDEXED
    domain.save()


def set_project_status_in_progress(project_id: int):
    if not project_id:
        logger.error("project_id is required")

    from projects.models import Project, StatusChoices

    project = Project.objects.get(id=project_id)
    project.status = StatusChoices.IN_PROGRESS
    project.save()


@celery_app.task()
def set_project_status_indexed(previous_task, project_id: int):
    logger.info(previous_task)
    if not project_id:
        logger.error("project_id is required")

    from projects.models import Project, StatusChoices

    project = Project.objects.get(id=project_id)
    project.status = StatusChoices.INDEXED
    project.save()
