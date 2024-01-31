from datetime import datetime

from django.utils.timezone import make_aware


def format_timestamp(unix_timestamp):
    # Parse the timestamp string
    dt = datetime.strptime(unix_timestamp, "%Y%m%d%H%M%S")

    return make_aware(dt)
