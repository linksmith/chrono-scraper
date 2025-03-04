from datetime import datetime
from typing import Any

from celery import chain, group, states
from celery.result import AsyncResult
from celery.utils.log import get_task_logger
from django.core.paginator import Paginator

from config import celery_app
from projects.enums import ProjectStatusChoices
from projects.meilisearch_utils import MeiliSearchManager, generate_meilisearch_id
from projects.wayback_machine_utils import (
    CdxQueryPageCollections,
    WaybackMachineException,
    WBMPage,
    fetch_cdx_pages,
    get_wayback_machine_page,
    get_wayback_machine_url,
)

# Get an instance of a logger
logger = get_task_logger(__name__)


def stop_task(task_id):
    """
    Retrieves the current status and result of a Celery task.

    :param task_id: The ID of the task to query.
    :return: A dictionary containing the status and result of the task.
    """
    task = AsyncResult(task_id, app=celery_app)
    task.revoke(terminate=True)

    response = {
        "task_id": task_id,
        "status": task.status,
        "result": task.result,
        "info": task.info,
    }

    return response


def get_task_status(task_id):
    """
    Retrieves the current status and result of a Celery task.

    :param task_id: The ID of the task to query.
    :return: A dictionary containing the status and result of the task.
    """
    task = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "status": task.status,
        "result": task.result,
        "info": task.info,
    }

    # Optionally add more information about the task
    if task.status == "FAILURE":
        response["error"] = str(task.result)  # This is the exception raised

    return response


def run_time_in_seconds(start_time: datetime, now: datetime = None):
    if now is None:
        now = datetime.now()
    return (now - start_time).total_seconds()


def start_time_formatted(start_time: datetime):
    return start_time.strftime("%Y-%m-%d %H:%M:%S")


@celery_app.task(bind=True, name="projects.tasks.start_build_project_index_task")
def start_build_project_index_task(self, project_id: int):
    start_time = datetime.now()

    self.task_id = self.request.id
    progress = 0
    logger.info(f"{project_id} with task_id: {self.task_id}")

    project_status = ProjectStatusChoices.IN_PROGRESS
    # Set the initial state of the task to 'STARTED' with some metadata
    self.update_state(
        state=states.STARTED,
        meta={
            "project_id": project_id,
            "project_status": project_status,
            "task_id": self.task_id,
            "message": "Collecting page URLs from CDX ...",
            "progress": progress,
            "start_time": start_time_formatted(start_time),
            "run_time_in_seconds": run_time_in_seconds(start_time),
        },
    )

    from projects.models import Project

    project = Project.objects.get(id=project_id)
    project.status = project_status
    # project.index_task_status = self.request.state
    project.index_task_id = self.task_id
    project.index_start_time = start_time
    project.save()

    # load pages from wayback machine
    cdx_queries = project.cdx_queries.all()

    total_pages = 0
    cdx_query_page_collections = []
    cdx_query_count = cdx_queries.count()
    cdx_query_total_progress_percentage = 10
    page_batch_size = 100

    # Looping through the list with index and value
    for index, cdx_query in enumerate(cdx_queries):
        cdx_query_pages = load_cdx_query_pages_from_cdx(
            cdx_query.id, cdx_query.url, project.index_name, cdx_query.from_date, cdx_query.to_date
        )

        page_count = len(cdx_query_pages)
        total_pages += total_pages

        # Calculate progress percentage (up to 5%)
        progress = ((index + 1) / cdx_query_count) * cdx_query_total_progress_percentage

        self.update_state(
            state=states.STARTED,
            meta={
                "project_id": project_id,
                "project_status": project_status,
                "task_id": self.task_id,
                "message": f"Collected {page_count} CDX URLs for `{cdx_query}`...",
                "progress": progress,
                "start_time": start_time_formatted(start_time),
                "run_time_in_seconds": run_time_in_seconds(start_time),
            },
        )

        # Split the pages into batches of `page_batch_size`
        for i in range(0, len(cdx_query_pages), page_batch_size):
            cdx_query_page_collections.append(
                CdxQueryPageCollections(cdx_query, cdx_query_pages[i : i + page_batch_size])
            )

    self.update_state(
        state=states.STARTED,
        meta={
            "project_id": project_id,
            "project_status": project_status,
            "task_id": self.task_id,
            "message": f"Total URLs collected for {len(cdx_query_page_collections)} "
            f"CDX Queries: {total_pages}. "
            f"Creating and indexing pages...",
            "progress": progress,
            "batches_done": 0,
            "total_batches": len(cdx_query_page_collections),
            "start_time": start_time_formatted(start_time),
            "run_time_in_seconds": run_time_in_seconds(start_time),
        },
    )

    get_and_create_and_index_pages_task_group = group(
        get_and_create_and_index_pages.si(
            self.task_id,
            cdx_query_page_collection.cdx_query.id,
            cdx_query_page_collection.cdx_query_pages,
            project.index_name,
            start_time,
        )
        for cdx_query_page_collection in cdx_query_page_collections
    )

    get_and_create_and_index_pages_task_group_success_chain = chain(
        get_and_create_and_index_pages_task_group,
        set_project_status.si(self.task_id, ProjectStatusChoices.INDEXED, project_id),
    )

    get_and_create_and_index_pages_task_group_success_chain.apply_async()


def load_cdx_query_pages_from_cdx(cdx_query_id, cdx_query_url, index_name, from_date, to_date):
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
        f"Loading pages from domain_id {cdx_query_id} - {cdx_query_url} "
        f"with index_name {index_name} and from_date {from_date} to_date {to_date}"
    )

    try:
        cdx_pages = get_cdx_query_pages_and_filter_results(cdx_query_id, cdx_query_url, from_date, to_date, 10000)
    except WaybackMachineException as exc:
        raise exc

    return cdx_pages


def get_cdx_pages(cdx_query_id: int, cdx_query_url: str, from_date: str, to_date: str, batch_size: int = 10000):
    resume_key = True
    cdx_pages = []
    while resume_key is not None:
        try:
            fetched_pages, resume_key = fetch_cdx_pages(cdx_query_id, cdx_query_url, from_date, to_date, batch_size)
            cdx_pages.append(fetched_pages)
        except WaybackMachineException as exc:
            raise exc

    return cdx_pages


def chunked_queryset(queryset, chunk_size=1000):
    paginator = Paginator(queryset, chunk_size)
    for page_number in paginator.page_range:
        yield paginator.page(page_number).object_list


def get_cdx_query_pages_and_filter_results(
    cdx_query_id: int, cdx_query_url: str, from_date: str, to_date: str, batch_size
) -> list[tuple[Any, ...]] | None:
    logger.info("Fetching page urls from CDX...")
    cdx_pages = get_cdx_pages(cdx_query_id, cdx_query_url, from_date, to_date, batch_size)
    if cdx_pages is None or cdx_pages == []:
        return None

    logger.info("Filtering out existing pages...")
    from projects.models import Page

    filtered_pages = []
    for chunk in chunked_queryset(Page.objects.values_list("wayback_machine_url", flat=True), 10000):
        existing_original_urls = set(chunk)
        for cdx_page in cdx_pages:
            wayback_machine_url = get_wayback_machine_url(cdx_page[0], cdx_page[1])
            if wayback_machine_url not in existing_original_urls:
                filtered_pages.append(cdx_page)

    fetched_page_count = len(cdx_pages)
    # database_page_count = len(existing_original_urls)
    # skipped_page_count = fetched_page_count - database_page_count
    filtered_page_count = len(filtered_pages)

    logger.info(f"Fetched pages: {fetched_page_count}")
    # logger.info(f"Existing pages: {database_page_count}")
    # logger.info(f"Skipped pages: {skipped_page_count}")
    logger.info(f"New (filtered) pages: {filtered_page_count}")

    return filtered_pages


@celery_app.task(bind=True, name="projects.tasks.get_and_create_and_index_page")
def get_and_create_and_index_pages(
    self, main_task_id: str, cdx_query_id: int, cdx_query_pages, index_name: str, start_time: datetime
):
    main_task = AsyncResult(main_task_id, app=celery_app)

    progress = main_task.info.get("progress", 0)
    batches_done = main_task.info.get("batches_done", 0)
    total_batches = main_task.info.get("total_batches", 0)

    from models import CdxQuery

    cdx_query = CdxQuery.objects.get(id=cdx_query_id)
    main_task.backend.update_state(
        state="PROGRESS",
        meta={
            "progress": progress,
            "batches_done": batches_done,
            "total_batches": total_batches,
            "task_id": self.task_id,
            "message": f"Fetching content from {cdx_query}...",
            "start_time": start_time_formatted(start_time),
            "run_time_in_seconds": run_time_in_seconds(start_time),
        },
    )

    wbm_pages = []
    for cdx_page in cdx_query_pages:
        wbm_page = WBMPage(
            unix_timestamp=cdx_page[0],
            original_url=cdx_page[1],
            mimetype=cdx_page[2],
            status_code=cdx_page[3],
            digest=cdx_page[4],
            length=cdx_page[5],
        )
        try:
            wbm_page = get_wayback_machine_page(cdx_query_id, wbm_page)
            logger.info(f"Fetched and saved page {wbm_page.wayback_machine_url} for cdx_query {cdx_query_id}")
            wbm_pages.append(wbm_page)
        except WaybackMachineException:
            logger.error(f"Skipped page {wbm_page.wayback_machine_url} for cdx_query {cdx_query_id}")

        except Exception:
            unix_timestamp = cdx_page[0]
            original_url = cdx_page[1]
            wayback_machine_url = get_wayback_machine_url(unix_timestamp, original_url)
            logger.exception(f"Skipped page due to error {wayback_machine_url} for cdx_query {cdx_query_id}")

    from models import Page

    wbm_pages_to_index = []
    page_objects = []

    for wbm_page in wbm_pages:
        meilisearch_id = generate_meilisearch_id(wbm_page.wayback_machine_url)

        page = Page(
            meilisearch_id=meilisearch_id,
            wayback_machine_url=wbm_page.wayback_machine_url,
            original_url=wbm_page.original_url,
            mimetype=wbm_page.mimetype,
            status_code=wbm_page.status_code,
            digest=wbm_page.digest,
            length=wbm_page.length,
            unix_timestamp=wbm_page.unix_timestamp,
            raw_content=wbm_page.raw_content,
            title=wbm_page.title,
        )

        meilisearch_document = {
            "meilisearch_id": meilisearch_id,
            "page_title": wbm_page.title,
            "page_text": wbm_page.text,
            "domain_name": cdx_query.domain_name,
            "wayback_machine_url": wbm_page.wayback_machine_url,
            "original_url": wbm_page.original_url,
            "mimetype": wbm_page.mimetype,
            "unix_timestamp": wbm_page.unix_timestamp,
        }

        page_objects.append(page)
        wbm_pages_to_index.append(meilisearch_document)

    # Bulk create all Page instances
    Page.objects.bulk_create(page_objects)

    # Index the pages in MeiliSearch
    meili_search_manager = MeiliSearchManager()
    index = meili_search_manager.get_or_create_project_index(index_name)
    index.add_documents(wbm_pages_to_index)

    batches_done = main_task.info.get("batches_done", 0) + 1  # 1
    total_batches = main_task.info.get("total_batches", 0)  # 25

    # (1 / 25 * 85) + 10 = 13,4
    # (2 / 25 * 85) + 10 = 16,8
    # ...
    # (24 / 25 * 85) + 10 = 91,6
    # (25 / 25 * 85) + 10 = 95
    total_percentage_of_all_batches = 89
    percentage_before_batches = 10
    progress = (batches_done / total_batches * total_percentage_of_all_batches) + percentage_before_batches
    main_task.backend.update_state(
        state="PROGRESS",
        meta={
            "progress": progress,
            "batches_done": batches_done,
            "total_batches": total_batches,
            "task_id": self.task_id,
            "message": f"Fetched content from {cdx_query}...",
            "start_time": start_time_formatted(start_time),
            "run_time_in_seconds": run_time_in_seconds(start_time),
        },
    )

    # Finish subtask
    return "Subtask completed"


@celery_app.task(bind=True, name="projects.tasks.set_project_status")
def set_project_status(self, main_task_id: str, project_indexed, project_id: int):
    logger.info(f"main_task_id {main_task_id}")
    logger.info(f"project_indexed {project_indexed}")
    logger.info(f"project_id {project_id}")

    main_task = AsyncResult(main_task_id, app=celery_app)

    logger.info(f"main_task {main_task}")

    if not project_indexed:
        logger.error("domain_indexed is required")

    if not project_id:
        logger.error("project_id is required")

    logger.info(f"Set status of project {project_id}...")

    from projects.models import Project

    project = Project.objects.get(id=project_id)

    if project_indexed:
        project.status = ProjectStatusChoices.INDEXED
    else:
        project.status = ProjectStatusChoices.NO_INDEX

    project.index_end_time = datetime.now()
    project.save()

    # progress = main_task.info.get("progress", 0)
    if main_task.info is not None:
        batches_done = main_task.info.get("batches_done", 0)
        total_batches = main_task.info.get("total_batches", 0)
    else:
        batches_done = 0
        total_batches = 0

    # Update the state to 'FINISHED' when done
    # main_task.update_state(
    #     state=states.SUCCESS,
    #     meta={
    #         "progress": 100,
    #         "batches_done": batches_done,
    #         "total_batches": total_batches,
    #         "task_id": self.task_id,
    #         "message": f"Finished indexing {project}.",
    #         "start_time": start_time_formatted(project.index_start_time),
    #         "end_time": start_time_formatted(project.index_end_time),
    #         "run_time_in_seconds": run_time_in_seconds(project.index_end_time),
    #     },
    # )

    return f"Status updated to {project.status} for project {project.name}"
