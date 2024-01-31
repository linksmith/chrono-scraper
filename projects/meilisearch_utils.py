# Description: Refactored Meilisearch utils
import logging
import os

from meilisearch import Client
from meilisearch.errors import MeilisearchApiError
from meilisearch.index import Index
from meilisearch.models.key import Key


class MeiliSearchManager:
    filterable_attributes = ["unix_timestamp", "domain_name"]
    primary_key = "meilisearch_id"

    def __init__(self):
        self.client = Client(os.getenv("MEILISEARCH_HOST"), os.getenv("MEILISEARCH_MASTER_KEY"))

    def get_client(self):
        return self.client

    def create_project_index(self, index_name) -> Key | None:
        logging.info(f"Creating index: {index_name}...")
        self.client.create_index(index_name, {"primaryKey": self.primary_key})

        index = self.get_index(index_name)
        if index is not None:
            index.update_filterable_attributes(self.filterable_attributes)
            logging.info(f"Index created: {index_name}.")

            return self.create_index_search_key(index_name)

        return None

    def get_index(self, index_name: str) -> Index | None:
        try:
            index = self.client.get_index(index_name)
            index.update_filterable_attributes(self.filterable_attributes)
            return index
        except MeilisearchApiError as e:
            if e.code != "index_not_found":
                raise
        return None

    def get_or_create_project_index(self, index_name: str) -> Index | None:
        index = self.get_index(index_name)

        if index is None:
            index = self.create_project_index(index_name)

        return index

    def delete_index(self, index_name: str):
        logging.debug(f"Deleting index: {index_name}...")
        self.client.delete_index(index_name)

    def delete_documents_for_domain(self, index_name: str, domain_id: int):
        logging.debug(f"Deleting index: {index_name}...")
        index = self.client.get_index(index_name)

        index.delete_documents(filter=f"domain={domain_id}")

    def create_index_search_key(self, index_name: str):
        # create a read-only key
        return self.client.create_key(
            {
                "name": f"search:{index_name}",
                "description": f'Search key for index "{index_name}"',
                "indexes": [index_name],
                "actions": ["search"],
                "expiresAt": None,
            }
        )
