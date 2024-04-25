from rest_framework import serializers

from projects.models import CdxQuery, Page, Project


class PageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = [
            "id",
            "title",
            "meilisearch_id",
            "unix_timestamp",
            "wayback_machine_url",
            "original_url",
            "mimetype",
        ]


class CdxQuerySerializer(serializers.ModelSerializer):
    index_name = serializers.SerializerMethodField()

    class Meta:
        model = CdxQuery
        fields = [
            "id",
            "url",
            "domain_name",
            "index_name",
            "from_date",
            "to_date",
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
            "is_public",
            "index_name",
            "cdx_query_count",
            "index_search_key",
            "index_start_time",
            "index_end_time",
            "index_duration_in_seconds",
            "index_duration_in_minutes",
            "index_duration_in_hours",
        ]
