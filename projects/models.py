import logging
from datetime import datetime

from django.db import models

from chrono_scraper.utils.url_utils import percent_decode_url

from .enums import ProjectStatusChoices
from .meilisearch_utils import MeiliSearchManager, generate_meilisearch_id
from .tasks import start_build_project_index_task

meili_search_manager = MeiliSearchManager()
logger = logging.getLogger(__name__)


class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=200, blank=True, null=True)
    is_public = models.BooleanField(default=False)
    index_name = models.SlugField(max_length=200, unique=True)
    index_search_key = models.CharField(max_length=64, blank=True, null=True)
    index_task_id = models.CharField(max_length=200, blank=True, null=True)
    index_start_time = models.DateTimeField(blank=True, null=True)
    index_end_time = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=16, choices=ProjectStatusChoices.choices, default=ProjectStatusChoices.NO_INDEX
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    user = models.ForeignKey("users.User", on_delete=models.CASCADE)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ("-created_at", "name")

    @property
    def cdx_query_count(self):
        return self.cdx_queries.count()

    @property
    # list of comma separated domains
    def cdx_query_list(self):
        return ", ".join([cdx_query.url for cdx_query in self.cdx_queries.all()])

    @property
    def index_duration_in_seconds(self):
        if self.index_start_time is None or self.index_end_time is None:
            return None

        return (self.index_end_time - self.index_start_time).seconds

    @property
    def index_duration_in_minutes(self):
        if self.index_start_time is None or self.index_end_time is None:
            return None

        return (self.index_end_time - self.index_start_time).seconds / 60

    @property
    def index_duration_in_hours(self):
        if self.index_start_time is None or self.index_end_time is None:
            return None

        return (self.index_end_time - self.index_start_time).seconds / 3600

    @staticmethod
    def build_index_by_project_id(project_id: int):
        task = start_build_project_index_task.apply_async((project_id,))
        logger.debug(f"rebuild_index: {project_id} - {task.id}")
        return task

    def delete_pages_and_index(self):
        for cdx_query in CdxQuery.objects.filter(project=self):
            cdx_query.delete_pages()

        meili_search_manager.delete_index(self.index_name)
        self.status = ProjectStatusChoices.NO_INDEX
        self.save()

    def build_index(project_id: int):
        task = start_build_project_index_task.apply_async((project_id,))
        logger.debug(f"rebuild_index: {project_id} - {task.id}")
        return task


class CdxQuery(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.CharField(max_length=256)
    from_date = models.DateField(default=datetime(1990, 1, 1))
    to_date = models.DateField(default=datetime.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="cdx_queries")
    pages = models.ManyToManyField("projects.Page", related_name="cdx_queries")

    def __str__(self):
        return str(f"{self.url}: {self.from_date} - {self.to_date}")

    class Meta:
        verbose_name = "CDX Query"
        verbose_name_plural = "CDX Queries"
        ordering = ("url", "-from_date", "-to_date")

    @property
    def domain_name(self):
        """
        Return the domain name from the URL
        """
        if self.url is None:
            return None

        decoded_url = percent_decode_url(self.url)

        if decoded_url is None:
            return None

        return decoded_url.split("/")[0]

    def delete_pages(self):
        """
        Delete all pages that are not associated with any other cdx_query
        """
        logger.info(f"Deleting domain pages: {self.url}...")
        self.pages.exclude(cdx_queries__count__gt=1).delete()
        self.pages.clear()


class Page(models.Model):
    id = models.AutoField(primary_key=True)
    meilisearch_id = models.CharField(max_length=64, blank=True, null=True, unique=True, db_index=True)
    wayback_machine_url = models.URLField(max_length=1024, unique=False, db_index=True)
    original_url = models.URLField(max_length=512)
    raw_content = models.TextField(blank=True)
    title = models.CharField(max_length=512, blank=True)
    unix_timestamp = models.PositiveBigIntegerField()
    mimetype = models.CharField(max_length=256)
    status_code = models.IntegerField()
    digest = models.CharField(max_length=256)
    length = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.wayback_machine_url

    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"
        ordering = ("wayback_machine_url", "-created_at")

    @staticmethod
    def page_exists(wayback_machine_url):
        meilisearch_id = generate_meilisearch_id(wayback_machine_url)
        return Page.objects.filter(meilisearch_id=meilisearch_id).exists()
