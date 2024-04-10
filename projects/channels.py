import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer

logger = logging.getLogger(__name__)


class TestConsumer(JsonWebsocketConsumer):
    def connect(self):
        logger.info("WS TestConsumer.connected...")
        self.accept()

    def receive(self, text_data=None, bytes_data=None, **kwargs):
        logger.info("receive...")
        self.send(text_data="Hello world!")

    def disconnect(self, close_code):
        logger.info("disconnect...")
        self.close()


class TaskProgressConsumer(JsonWebsocketConsumer):
    def celery_task_update(self, event):
        logger.info("celery_task_update...")
        message = event["message"]
        self.send_json(message)

    def connect(self):
        logger.info("WS TaskProgressConsumer.connected...")

        super().connect()
        task_id = self.scope.get("url_route").get("kwargs").get("task_id")

        logger.info(f"task_id: {task_id}")
        logger.info(f"channel_name: {self.channel_name}")

        async_to_sync(self.channel_layer.group_add)(task_id, self.channel_name)

    def receive(self, text_data=None, bytes_data=None, **kwargs):
        logger.info("receive...")
        self.send(text_data="Hello world!")

    def disconnect(self, close_code):
        logger.info("disconnect...")
        self.close()
