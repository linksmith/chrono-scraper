from rest_framework import serializers

from projects.models import Domain, Page, Project


class PageSerializer(serializers.ModelSerializer):
    domain_name = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = [
            "meilisearch_id",
            "id",
            "domain",
            "domain_name",
            "unix_timestamp",
            "wayback_machine_url",
            "original_url",
            "mimetype",
        ]

    def get_domain_name(self, obj):
        if obj.domain is None:
            return None
        return obj.domain.domain_name


class DomainSerializer(serializers.ModelSerializer):
    index_name = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = [
            "id",
            "domain_name",
            "index_name",
            "from_date",
            "to_date",
            "active",
        ]

    def get_index_name(self, obj):
        if obj.project is None:
            return None
        return obj.project.index_name


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "status",
            "index_name",
            "index_search_key",
        ]
