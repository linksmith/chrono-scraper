import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from ..models import Project
from .serializers import ProjectSerializer

User = get_user_model()
logger = logging.getLogger(__name__)


class ProjectViewSet(ModelViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, int)
        return self.queryset.filter(user_id=self.request.user.id)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def rebuild_index(self, request, pk=None):
        logger.debug(f"rebuild_index: {pk}")
        celery_task = Project.build_index_by_project_id(project_id=pk)
        # task = celery_app.AsyncResult(celery_task.id)

        return Response(
            status=status.HTTP_200_OK,
            data={
                "celery_task_id": celery_task.id,
                "status": celery_task.state,
                "message": "Rebuilding index started. Check the status later.",
            },
        )
