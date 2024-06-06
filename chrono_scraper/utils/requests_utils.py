from functools import wraps

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class SessionManager:
    def __init__(self):
        self.session = None

    def __enter__(self):
        if self.session is None:
            self.session = requests.Session()
            retry = Retry(connect=3, backoff_factor=0.5)
            adapter = HTTPAdapter(max_retries=retry)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()


def session_manager(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with SessionManager() as session:
            return func(session, *args, **kwargs)

    return wrapper
