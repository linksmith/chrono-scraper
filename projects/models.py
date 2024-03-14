import hashlib
import logging
from datetime import datetime

from django.db import models
from meilisearch.models.key import Key

from .enums import DomainStatusChoices, ProjectStatusChoices
from .meilisearch_utils import MeiliSearchManager
from .tasks import start_rebuild_project_index_task

meili_search_manager = MeiliSearchManager()
logger = logging.getLogger(__name__)


class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=200, blank=True, null=True)
    index_name = models.SlugField(max_length=200, unique=True)
    index_search_key = models.CharField(max_length=64, blank=True, null=True)
    status = models.CharField(
        max_length=16, choices=ProjectStatusChoices.choices, default=ProjectStatusChoices.NO_INDEX
    )
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
        self.status = ProjectStatusChoices.NO_INDEX
        self.save()

    def rebuild_index(self):
        return Project.rebuild_index_by_project_id(self.id)

    @staticmethod
    def rebuild_index_by_project_id(project_id: int):
        task = start_rebuild_project_index_task.apply_async((project_id,))
        logger.info(f"rebuild_index: {project_id} - {task.id}")
        return task


class Domain(models.Model):
    id = models.AutoField(primary_key=True)
    domain_name = models.CharField(max_length=256)
    from_date = models.DateField(default=datetime(1990, 1, 1))
    to_date = models.DateField(default=datetime.now)
    active = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=DomainStatusChoices.choices, default=DomainStatusChoices.NO_INDEX)
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


class Page(models.Model):
    id = models.AutoField(primary_key=True)
    meilisearch_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    wayback_machine_url = models.URLField(max_length=1024, unique=False, db_index=True)
    original_url = models.URLField(max_length=512)
    title = models.CharField(max_length=512, blank=True)
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

    def generate_meilisearch_id(self):
        return Page.generate_meilisearch_id_for_instance(self.wayback_machine_url, self.domain.id)

    @staticmethod
    def generate_meilisearch_id_for_instance(wayback_machine_url, domain_id):
        if wayback_machine_url is None:
            return None

        if domain_id is None:
            return None

        # generate a hash from domain.id and wayback_machine_url
        return hashlib.sha256(f"{domain_id}-{wayback_machine_url}".encode()).hexdigest()

    @staticmethod
    def page_exists(domain_id, wayback_machine_url):
        meilisearch_id = Page.generate_meilisearch_id_for_instance(
            wayback_machine_url=wayback_machine_url, domain_id=domain_id
        )
        return Page.objects.filter(meilisearch_id=meilisearch_id).exists()

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
