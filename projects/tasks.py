import logging
from datetime import datetime
from typing import Any

from celery import chain, group

from config import celery_app
from projects.wayback_machine_utils import (
    WaybackMachineException,
    create_page_from_wayback_machine,
    fetch_cdx_pages,
    filter_out_existing_pages,
)

# Get an instance of a logger
logger = logging.getLogger(__name__)


def start_rebuild_project_index(project):
    from projects.models import StatusChoices

    project.status = StatusChoices.IN_PROGRESS
    project.save()

    for domain in project.domains.all():
        start_load_pages_from_wayback_machine(
            domain.id, domain.domain_name, project.index_name, domain.active, domain.from_date, domain.to_date
        )

    project.status = StatusChoices.INDEXED
    project.save()

    # from projects.models import StatusChoices, Domain
    #
    # domains = Domain.objects.filter(project=project, active=True)
    #
    # if not domains:
    #     logger.error(f"No domains found for project {project.name}")
    #     return
    #
    # project.status = StatusChoices.IN_PROGRESS
    # project.save()
    #
    # domains_dict = []
    # from projects.serializers import DomainSerializer
    # for domain in domains:
    #     domains_dict.append(DomainSerializer(domain).data)
    #
    # domain_index_task_group = on_domain_index_task_group.s(domains_dict)
    #
    # workflow = chain(
    #     domain_index_task_group,
    #     set_project_status.s(project.id, StatusChoices.INDEXED),
    # )
    #
    # workflow()


@celery_app.task()
def on_domain_index_task_group(domains):
    domain_index_task_group_tasks = group(
        start_load_pages_from_wayback_machine_task.s(
            domain["id"],
            domain["domain_name"],
            domain["index_name"],
            domain["from_date"],
            domain["to_date"],
        )
        for domain in domains
    )
    return domain_index_task_group_tasks()


def start_load_pages_from_wayback_machine(domain_id, domain_name, index_name, active, from_date, to_date):
    if not active:
        logger.debug(f"Skipping rebuild index for domain {domain_name} because it is not active")
        return

    start_load_pages_from_wayback_machine_task(domain_id, domain_name, index_name, from_date, to_date)


@celery_app.task()
def set_project_status(task_results, project_id: int, status):
    from projects.models import Project

    project = Project.objects.get(id=project_id)
    project.status = status
    project.save()


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

    get_pages_task = get_pages.s(domain_id, domain_name, from_date, to_date)
    get_and_create_and_index_pages_task_group = on_got_pages.s(domain_id, index_name)
    workflow = chain(get_pages_task, get_and_create_and_index_pages_task_group)
    workflow()


@celery_app.task()
def on_got_pages(cdx_pages, domain_id, index_name):
    if cdx_pages:
        get_and_create_and_index_page_tasks = group(
            get_and_create_and_index_page.s(domain_id, cdx_page, index_name) for cdx_page in cdx_pages
        )
        return get_and_create_and_index_page_tasks()


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
    except WaybackMachineException as error:
        original_url = cdx_page[1]
        logger.debug(f"Error creating page {original_url}, ERROR: {error}")
        return

    page.add_to_index(index_name, title, text)
