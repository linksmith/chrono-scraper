# Description: Meilisearch utils
import logging
from io import BytesIO

import pdfplumber
import requests
from bs4 import BeautifulSoup
from django.conf import settings

from chrono_scraper.utils.url_utils import get_domain_name_from_url

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


class CdxQueryPageCollections:
    def __init__(self, cdx_query=None, cdx_query_pages=None):
        if cdx_query_pages is None:
            cdx_query_pages = []

        self.cdx_query = cdx_query
        self.cdx_query_pages = cdx_query_pages


proxy = requests.Session()
proxy.proxies.update(settings.PROXY_SETTINGS)


def get_wayback_machine_url(unix_timestamp: int, original_url: str) -> str:
    return f"https://web.archive.org/web/{str(unix_timestamp)}/{original_url}"


def get_wayback_machine_content_url(unix_timestamp: int, original_url: str) -> str:
    return f"https://web.archive.org/web/{str(unix_timestamp)}if_/{original_url}"


class WBMPage:
    title = ""
    text = ""
    raw_content = ""

    def __init__(self, unix_timestamp: int, original_url, mimetype, status_code, digest, length):
        self.unix_timestamp = unix_timestamp
        self.original_url = original_url
        self.mimetype = mimetype
        self.status_code = status_code
        self.digest = digest
        self.length = length

    @property
    def wayback_machine_url(self):
        return get_wayback_machine_url(self.unix_timestamp, self.original_url)

    @property
    def domain_name(self):
        return get_domain_name_from_url(self.original_url)


def get_wayback_machine_page(cdx_query_id, wbm_page) -> WBMPage:
    # TODO: Redo this check
    from models import Page

    if Page.page_exists(cdx_query_id, wbm_page.wayback_machine_url):
        logger.debug(f"Page already exists for domain {wbm_page.wayback_machine_url}")
        raise PageAlreadyExistsForDomainException

    wayback_machine_content_url = get_wayback_machine_content_url(wbm_page.unix_timestamp, wbm_page.original_url)

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

    if wbm_page.mimetype == "application/pdf":
        title, text = fetch_pdf_content_on_the_fly(raw_content, wbm_page.wayback_machine_url, wbm_page.original_url)

    elif wbm_page.mimetype == "text/html":
        title, text = fetch_html_content(raw_content, wbm_page.wayback_machine_url)

    else:
        logger.error(f"Unaccepted mimetype: {wbm_page.mimetype}")
        raise WaybackMachineException

    text_length = len(text)
    if not text or text_length < 400:
        logger.debug(f"Skipping page: {wbm_page.wayback_machine_url} because there is not enough content")
        raise NotEnoughContentException

    wbm_page.title = title
    wbm_page.title = text
    wbm_page.title = raw_content

    return wbm_page


def fetch_cdx_pages(cdx_query_id: int, cdx_query_url: str, from_date: str, to_date: str, batch_size: int):
    if not isinstance(cdx_query_id, int):
        raise ValueError("cdx_query_id must be an integer")
    if not isinstance(cdx_query_url, str):
        raise ValueError("cdx_query_url must be a string")
    if not isinstance(from_date, str):
        raise ValueError("from_date must be a string")
    if not isinstance(to_date, str):
        raise ValueError("to_date must be a string")

    cdx_api_url = (
        f"https://web.archive.org/cdx/search/cdx?url={cdx_query_url}&from={from_date}&to={to_date}&output=json"
        f"&collapse=digest&matchType=prefix&fl=timestamp,original,mimetype,statuscode,digest,length"
        f"&filter=statuscode:200&filter=mimetype:text/html|application/pdf&limit={batch_size}&showResumeKey=true"
    )

    try:
        response = proxy.get(cdx_api_url)
    except Exception:
        logger.exception(f"Error fetching {cdx_api_url}")
        raise WaybackMachineException

    if response.status_code != 200:
        logger.error(
            f"Wayback Machine API unavailable. cdx_query_id: {cdx_query_id}, cdx_query_url: "
            f"{cdx_query_url}, from_date: {from_date}, to_date: {to_date}. "
            f"response.status: {response.status_code}"
        )
        raise WaybackMachineException

    try:
        response_json = response.json()
    except Exception:
        logger.exception(f"Error fetching {cdx_api_url}")
        raise WaybackMachineException

    if not isinstance(response_json, list) or len(response_json) < 2:
        logger.error("JSON response not correctly formatted. It should be a list of more than 2 length.")
        raise ContentFormattingException

    resume_key = response_json[-1]
    results = [row for row in response_json[1:-1] if row]

    return results, resume_key


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
