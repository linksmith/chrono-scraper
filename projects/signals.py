import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from slugify import slugify

from .meilisearch_utils import MeiliSearchManager
from .models import Domain, Page, Project

meili_search_manager = MeiliSearchManager()

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Project)
def post_delete_project(sender, instance, **kwargs):
    logger.info(f"Deleting project: {instance.name}...")
    meili_search_manager.delete_index(instance.index_name)


@receiver(pre_save, sender=Project)
def pre_save_project(sender, instance, **kwargs):
    logger.info(f"Saving project: {instance.name}...")

    if not instance.index_name:  # If the index_name hasn't been set yet
        instance.index_name = slugify(instance.name)
        original_index_name = instance.index_name

        # Ensure the index_name is unique
        index = 1
        while Project.objects.filter(index_name=instance.index_name).exists():
            instance.index_name = f"{original_index_name}-{index}"
            index += 1

    # if this is a new project, create the index and keys
    if not instance.pk:
        key = meili_search_manager.create_project_index(instance.index_name)

        if key is None:
            logger.error(f"Could not create index {instance.index_name}")
            return

        instance.index_search_key = key.key


@receiver(post_delete, sender=Domain)
def post_delete_domain(sender, instance, **kwargs):
    logger.info(f"Deleting domain from project ({instance.project.name}): {instance.id}: {instance.domain_name}...")
    meili_search_manager.delete_documents_for_domain(instance.project.index_name, instance.id)


@receiver(pre_save, sender=Page)
def pre_save_page(sender, instance, **kwargs):
    if not instance.meilisearch_id:
        instance.meilisearch_id = instance.generate_meilisearch_id()
