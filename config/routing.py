from django.urls import path

from projects.channels import TaskProgressConsumer, TestConsumer

websocket_urlpatterns = [
    path("task/test/", TestConsumer.as_asgi()),
    path("task/progress/<str:task_id>/", TaskProgressConsumer.as_asgi()),
]
