from django.conf import settings
from rest_framework.routers import DefaultRouter, SimpleRouter

from chrono_scraper.users.api.views import UserViewSet
from projects.api.views import ProjectViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("users", UserViewSet)
router.register("projects", ProjectViewSet, basename="projects")


app_name = "api"
urlpatterns = router.urls
