from urllib.parse import quote, unquote

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def strip_and_clean_url(url):
    """
    Strip and clean a URL.
    """
    url = url.strip()
    url = url.replace("http://", "")
    url = url.replace("https://", "")
    url = url.replace("www.", "")
    url = url.replace(" ", "")

    return url


def validate_url(url):
    """
    Validate a URL.
    """
    if not url:
        raise ValidationError("Please enter a URL.")

    url = strip_and_clean_url(url)

    # Validate that domain_name is a valid URL
    validate = URLValidator()
    try:
        validate(url)
    except ValidationError:
        raise ValidationError("Invalid URL. Please enter a valid URL.")

    return url


def get_domain_name_from_url(url):
    """
    Get the domain name from a URL.
    """
    return url.split("/")[2]


def percent_encode_url(url):
    """
    Percent-encode a URL.
    """
    return quote(url)


def percent_decode_url(url):
    """
    Percent-decode a URL.
    """
    return unquote(url)
