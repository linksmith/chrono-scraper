"""
ASGI config for Chrono Scraper project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/dev/howto/deployment/asgi/

"""
import os
import sys
from pathlib import Path

import environ
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

# This allows easy placement of apps within the interior
# chrono_scraper directory.

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
sys.path.append(str(BASE_DIR / "chrono_scraper"))

# chrono_scraper/
APPS_DIR = BASE_DIR / "chrono_scraper"

# If DJANGO_SETTINGS_MODULE is unset, default to the local settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# django.setup()

# This application object is used by any ASGI server configured to use this file.
# Import websocket application here, so apps from django_application are loaded first

from config import routing  # noqa isort:skip
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa isort:skip

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AuthMiddlewareStack(URLRouter(routing.websocket_urlpatterns)),
    }
)
