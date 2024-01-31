import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .meilisearch_utils import MeiliSearchManager
from .models import Domain, Project

meili_search_manager = MeiliSearchManager()


@receiver(post_delete, sender=Project)
def post_delete_project(sender, instance, **kwargs):
    logging.debug(f"Deleting project: {instance.name}...")
    meili_search_manager.delete_index(instance.index_name)


@receiver(post_delete, sender=Domain)
def post_delete_domain(sender, instance, **kwargs):
    logging.debug(f"Deleting domain from project ({instance.project.name}): {instance.id}: {instance.domain_name}...")
    meili_search_manager.delete_documents_for_domain(instance.project.index_name, instance.id)
