# Description: Meilisearch utils
import logging
from io import BytesIO
from typing import Any

import pdfplumber
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.db import IntegrityError

logger = logging.getLogger(__name__)


# Define a custom exception
class WaybackMachineException(Exception):
    pass


proxy = requests.Session()
proxy.proxies.update(settings.PROXY_SETTINGS)


def create_page_from_wayback_machine(domain_id: int, cdx_page) -> tuple[Any, ...] | None:
    unix_timestamp = cdx_page[0]
    original_url = cdx_page[1]
    mimetype = cdx_page[2]
    wayback_machine_url = get_wayback_machine_url(unix_timestamp, original_url)

    wayback_machine_content_url = get_wayback_machine_content_url(unix_timestamp, original_url)

    raw_content = None

    try:
        response = proxy.get(wayback_machine_content_url)
        if response.status_code == 200:
            raw_content = response.content
    except Exception as error:
        raise WaybackMachineException(f"Error fetching {wayback_machine_content_url}, {error}")

    if not raw_content:
        raise WaybackMachineException(f"raw_content is empty {wayback_machine_content_url}")

    if mimetype == "application/pdf":
        title, text = fetch_pdf_content_on_the_fly(raw_content, wayback_machine_url, original_url)

    elif mimetype == "text/html":
        title, text = fetch_html_content(raw_content, wayback_machine_url)

    else:
        raise WaybackMachineException(f"Unaccepted mimetype: {mimetype}")

    text_length = len(text)
    if not text or text_length < 400:
        raise WaybackMachineException(
            f"Skipping page: {wayback_machine_url} because it's too short ({text_length}) chars."
        )

    from projects.models import Page

    try:
        page, _ = Page.objects.get_or_create(
            domain_id=domain_id,
            unix_timestamp=unix_timestamp,
            original_url=original_url,
            mimetype=mimetype,
            status_code=cdx_page[3],
            digest=cdx_page[4],
            length=cdx_page[5],
            wayback_machine_url=wayback_machine_url,
        )
    except IntegrityError as error:
        raise WaybackMachineException(f"Error creating page. It already exists: {wayback_machine_url}, {error}")
    except Exception as error:
        raise WaybackMachineException(f"Error creating page: {wayback_machine_url}, {error}")

    return page, title, text


def fetch_cdx_pages(domain_id: int, domain_name: str, from_date: str, to_date: str) -> list[tuple[Any, ...]] | None:
    if not isinstance(domain_id, int):
        raise ValueError("domain_id must be an integer")
    if not isinstance(domain_name, str):
        raise ValueError("domain_name must be a string")
    if not isinstance(from_date, str):
        raise ValueError("from_date must be a string")
    if not isinstance(to_date, str):
        raise ValueError("to_date must be a string")

    url = (
        f"https://web.archive.org/cdx/search/cdx?url={domain_name}&from={from_date}&to={to_date}&output=json"
        f"&collapse=digest&matchType=domain&fl=timestamp,original,mimetype,statuscode,digest,"
        f"length&filter=statuscode:200&filter=mimetype:text/html|application/pdf"
    )

    try:
        response = proxy.get(url)
    except Exception as error:
        raise WaybackMachineException(f"Error fetching {url}, ERROR: {error}")

    if response.status_code != 200:
        raise WaybackMachineException(
            f"Error fetching {url}, response.status: {response.status_code}",
        )

    try:
        response_json = response.json()
    except Exception as error:
        raise WaybackMachineException(f"Error fetching {url}, ERROR: {error}")

    if not isinstance(response_json, list) or len(response_json) < 2:
        raise WaybackMachineException(
            f"JSON response not correctly formatted. " f"It should be a list of less then 2 length: {response_json}"
        )

    return response_json[1:]


def filter_out_existing_pages(cdx_pages, domain_id):
    if cdx_pages is None:
        return None

    logger.debug("Filtering out existing pages")

    from projects.models import Page

    existing_page_wayback_machine_urls = (
        Page.objects.filter(domain_id=domain_id).values_list("wayback_machine_url", flat=True).all()
    )

    filtered_cdx_pages = []
    for cdx_page in cdx_pages:
        wayback_machine_url = get_wayback_machine_url(cdx_page[0], cdx_page[1])
        if wayback_machine_url not in existing_page_wayback_machine_urls:
            filtered_cdx_pages.append(cdx_page)

    existing_pages_count = len(existing_page_wayback_machine_urls)
    skipped_page_count = len(cdx_pages) - existing_pages_count
    filtered_cdx_pages_count = len(filtered_cdx_pages)

    logger.debug(f"Existing pages for domain_id {domain_id}: {existing_pages_count}")
    logger.debug(f"Skipped pages: {skipped_page_count}")
    logger.debug(f"Adding new pages: {filtered_cdx_pages_count}")

    return filtered_cdx_pages


def get_wayback_machine_url(unix_timestamp: str, original_url: str) -> str:
    return f"https://web.archive.org/web/{unix_timestamp}/{original_url}"


def get_wayback_machine_content_url(unix_timestamp: str, original_url: str) -> str:
    return f"https://web.archive.org/web/{unix_timestamp}if_/{original_url}"


def fetch_pdf_content_on_the_fly(raw_content, wayback_machine_url, original_url) -> tuple[str, str]:
    pdf_content = ""
    pdf_title = ""

    try:
        with pdfplumber.open(BytesIO(raw_content)) as pdf:
            pdf_content = " ".join(page.extract_text() for page in pdf.pages)
            if pdf.metadata is not None and "title" in pdf.metadata:
                pdf_title = pdf.metadata["title"]

        if pdf_title is None or pdf_title == "":
            pdf_title = original_url.split("/")[-1]

        if pdf_title is None or pdf_title == "":
            pdf_title = "NO TITLE"
    except Exception as error:
        raise WaybackMachineException(
            f"Skipping page: {wayback_machine_url} because there is a PDF parsing error, {error}"
        )

    return pdf_title, pdf_content


def fetch_html_content(raw_content: bytes, wayback_machine_url) -> tuple[str, str]:
    try:
        soup = BeautifulSoup(raw_content, "html.parser")
        text = soup.get_text()
        # remove all newlines
        text = text.replace("\n", " ")
        # remove all spaces at the beginning and end of the string
        text = text.strip()
        # remove all spaces longer than 1 in an efficient way
        text = " ".join(text.split())
        # fix any encoding issues
        text = text.encode("ascii", "ignore").decode("utf-8")
    except Exception as error:
        raise WaybackMachineException(
            f"Skipping page: {wayback_machine_url} because there is a HTML parsing error, {error}"
        )

    title = "NO TITLE"
    if soup.title is not None:
        title = soup.title.string

    try:
        if title is not None:
            title = title.encode("ascii", "ignore").decode("utf-8")
    except Exception as error:
        raise WaybackMachineException(
            f"Skipping page: {wayback_machine_url} because there is an Error encoding HTML title, {error}"
        )

    if title is None or title == "":
        title = "NO TITLE"

    return title, text
