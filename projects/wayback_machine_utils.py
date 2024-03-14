# Description: Meilisearch utils
import logging
from io import BytesIO
from typing import Any

import pdfplumber
import requests
from bs4 import BeautifulSoup
from django.conf import settings

logger = logging.getLogger(__name__)


# Define a custom exception
class WaybackMachineException(Exception):
    pass


# Define a custom exception
class PageAlreadyExistsForDomainException(WaybackMachineException):
    pass


class NotEnoughContentException(WaybackMachineException):
    pass


class ContentFormattingException(WaybackMachineException):
    pass


proxy = requests.Session()
proxy.proxies.update(settings.PROXY_SETTINGS)


def create_page_from_wayback_machine(domain_id: int, cdx_page) -> tuple[object, str, str] | None:
    unix_timestamp = cdx_page[0]
    original_url = cdx_page[1]
    mimetype = cdx_page[2]

    wayback_machine_url = get_wayback_machine_url(unix_timestamp, original_url)

    from projects.models import Page

    if Page.page_exists(domain_id, wayback_machine_url):
        logger.debug(f"Page already exists for domain {domain_id}: {wayback_machine_url}")
        raise PageAlreadyExistsForDomainException

    wayback_machine_content_url = get_wayback_machine_content_url(unix_timestamp, original_url)

    raw_content = None

    try:
        response = proxy.get(wayback_machine_content_url)
        if response.status_code == 200:
            raw_content = response.content
    except Exception:
        logger.error(f"Error fetching {wayback_machine_content_url}")
        raise WaybackMachineException

    if not raw_content:
        logger.error(f"raw_content is empty {wayback_machine_content_url}")
        raise WaybackMachineException

    if mimetype == "application/pdf":
        title, text = fetch_pdf_content_on_the_fly(raw_content, wayback_machine_url, original_url)

    elif mimetype == "text/html":
        title, text = fetch_html_content(raw_content, wayback_machine_url)

    else:
        logger.error(f"Unaccepted mimetype: {mimetype}")
        raise WaybackMachineException

    text_length = len(text)
    if not text or text_length < 400:
        logger.debug(f"Skipping page: {wayback_machine_url} because there is not enough content")
        raise NotEnoughContentException

    try:
        from projects.models import Page

        page = Page.objects.create(
            domain_id=domain_id,
            unix_timestamp=unix_timestamp,
            original_url=original_url,
            mimetype=mimetype,
            status_code=cdx_page[3],
            digest=cdx_page[4],
            length=cdx_page[5],
            wayback_machine_url=wayback_machine_url,
        )
    except Exception:
        logger.debug(f"Page already exists for domain {domain_id}: {wayback_machine_url}")
        raise PageAlreadyExistsForDomainException

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
    except Exception:
        logger.exception(f"Error fetching {url}")
        raise WaybackMachineException

    if response.status_code != 200:
        logger.error(
            f"Wayback Machine API unavailable. domain_id: {domain_id}, domain_name: "
            f"{domain_name}, from_date: {from_date}, to_date: {to_date}. "
            f"response.status: {response.status_code}"
        )
        raise WaybackMachineException

    try:
        response_json = response.json()
    except Exception:
        logger.exception(f"Error fetching {url}")
        raise WaybackMachineException

    if not isinstance(response_json, list) or len(response_json) < 2:
        logger.error("JSON response not correctly formatted. It should be a list of less then 2 length.")
        raise ContentFormattingException

    return response_json[1:]


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
    except Exception:
        logger.error(f"Skipping page: {wayback_machine_url} because there is a PDF parsing error")
        raise ContentFormattingException

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
    except Exception:
        logger.error(f"Skipping page: {wayback_machine_url} because there is a HTML parsing error")
        raise ContentFormattingException

    title = "NO TITLE"
    if soup.title is not None:
        title = soup.title.string

    try:
        if title is not None:
            title = title.encode("ascii", "ignore").decode("utf-8")
    except Exception:
        logger.error(f"Skipping page: {wayback_machine_url} because there is an Error encoding HTML title")
        raise ContentFormattingException

    if title is None or title == "":
        title = "NO TITLE"

    return title, text
