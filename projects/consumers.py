import asyncio
import json
import logging

from asgiref.sync import async_to_sync, sync_to_async
from channels.generic.http import AsyncHttpConsumer
from channels.generic.websocket import JsonWebsocketConsumer

from projects.tasks import get_task_status

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


class TaskProgressWebsocketConsumer(JsonWebsocketConsumer):
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


class TaskProgressServerSentEventsConsumer(AsyncHttpConsumer):
    async def handle(self, body):
        task_id = self.scope.get("url_route").get("kwargs").get("task_id")
        logger.info(f"task_id: {task_id}")

        await self.send_headers(
            headers=[
                (b"Cache-Control", b"no-cache"),
                (b"Content-Type", b"text/event-stream"),
                (b"Transfer-Encoding", b"chunked"),
            ]
        )
        try:
            while True:
                status = await sync_to_async(get_task_status)(task_id)
                await self.send_body(f"data: {json.dumps(status)}\n\n".encode(), more_body=True)
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Connection closed: {e}")  # Log or handle the cleanup here
