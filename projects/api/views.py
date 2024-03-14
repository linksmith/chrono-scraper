import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from config import celery_app

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
        return self.queryset.filter(
            user_id=self.request.user.id,
            # status=StatusChoices.INDEXED
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def rebuild_index(self, request, pk=None):
        logger.debug(f"rebuild_index: {pk}")
        result = Project.rebuild_index_by_project_id(project_id=pk)

        task = celery_app.AsyncResult(result.id)
        task_state = task.state

        return Response(
            status=status.HTTP_200_OK,
            data={
                "task_id": result.id,
                "task_state": task_state,
                "message": "Rebuilding index started. Check the status later.",
            },
        )
