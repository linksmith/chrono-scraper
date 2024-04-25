from django.urls import path

from projects.consumers import TaskProgressServerSentEventsConsumer, TaskProgressWebsocketConsumer, TestConsumer

websocket_urlpatterns = [
    path("task/test/", TestConsumer.as_asgi()),
    path("task/progress/<str:task_id>/", TaskProgressWebsocketConsumer.as_asgi()),
    path("task/project_index_status/<str:task_id>/", TaskProgressServerSentEventsConsumer.as_asgi()),
]
