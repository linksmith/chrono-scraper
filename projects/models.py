import hashlib
import logging
from datetime import datetime

from django.db import models
from django.db.models import TextChoices
from meilisearch.models.key import Key

from .meilisearch_utils import MeiliSearchManager
from .tasks import start_load_pages_from_wayback_machine, start_rebuild_project_index

meili_search_manager = MeiliSearchManager()
logger = logging.getLogger(__name__)


class StatusChoices(TextChoices):
    NO_INDEX = "no_index", "No Index"
    IN_PROGRESS = "in_progress", "In Progress"
    INDEXED = "indexed", "Indexed"


class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=200, blank=True, null=True)
    index_name = models.SlugField(max_length=200, unique=True)
    index_search_key = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(max_length=16, choices=StatusChoices.choices, default=StatusChoices.NO_INDEX)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ("-created_at", "name")

    def domain_count(self):
        return self.domains.count()

    # list of comma separated domains
    def domain_list(self):
        return ", ".join([domain.domain_name for domain in self.domains.all()])

    def delete_pages_and_index(self):
        for domain in Domain.objects.filter(project=self):
            domain.delete_pages()

        meili_search_manager.delete_index(self.index_name)
        self.status = StatusChoices.NO_INDEX
        self.save()

    def rebuild_index(self):
        start_rebuild_project_index(self)


class Domain(models.Model):
    id = models.AutoField(primary_key=True)
    domain_name = models.CharField(max_length=256)
    from_date = models.DateField(default=datetime(1990, 1, 1))
    to_date = models.DateField(default=datetime.now)
    active = models.BooleanField(default=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="domains")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(f"{self.domain_name}")

    class Meta:
        verbose_name = "Domain"
        verbose_name_plural = "Domains"
        ordering = ("-created_at", "domain_name")

    def delete_pages(self):
        logger.info(f"Deleting domain pages: {self.domain_name}...")
        self.pages.all().delete()

    def rebuild_index(self):
        start_load_pages_from_wayback_machine(self.id, self.domain_name, self.active, self.from_date, self.to_date)


class Page(models.Model):
    id = models.AutoField(primary_key=True)
    meilisearch_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    wayback_machine_url = models.URLField(max_length=512, unique=True, db_index=True)
    original_url = models.URLField(max_length=256)
    title = models.CharField(max_length=256, blank=True)
    unix_timestamp = models.PositiveBigIntegerField()
    mimetype = models.CharField(max_length=256)
    status_code = models.IntegerField()
    digest = models.CharField(max_length=256)
    length = models.IntegerField()

    domain = models.ForeignKey("projects.Domain", on_delete=models.CASCADE, related_name="pages", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(f"{self.domain}: {self.wayback_machine_url}")

    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"
        ordering = ("domain", "-created_at")

    @staticmethod
    def wayback_machine_url_to_hash(wayback_machine_url):
        if wayback_machine_url is None:
            return None

        return hashlib.sha256(wayback_machine_url.encode()).hexdigest()

    def add_to_index(self, index_name: str, title: str, text: str):
        index = meili_search_manager.get_or_create_project_index(index_name)

        if index is None:
            logger.error(f"add_page_to_index: Could not find index {index_name}")
            return

        if isinstance(index, Key):
            logger.error(f"Expected Index, got Key {index_name}")
            return

        from projects.serializers import PageSerializer

        serializer = PageSerializer(self)

        index.add_documents(
            [
                {
                    "title": title,
                    "text": text,
                    "meilisearch_id": serializer.data["meilisearch_id"],
                    "id": serializer.data["id"],
                    "domain": serializer.data["domain"],
                    "domain_name": serializer.data["domain_name"],
                    "wayback_machine_url": serializer.data["wayback_machine_url"],
                    "original_url": serializer.data["original_url"],
                    "mimetype": serializer.data["mimetype"],
                    "unix_timestamp": int(serializer.data["unix_timestamp"]),
                }
            ]
        )
