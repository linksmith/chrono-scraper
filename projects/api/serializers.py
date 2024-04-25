from django.contrib.auth import get_user_model
from rest_framework import serializers

from chrono_scraper.users.models import User as UserType
from projects.models import CdxQuery, Project

User = get_user_model()


class UserSerializer(serializers.ModelSerializer[UserType]):
    class Meta:
        model = User
        fields = ["name", "url"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "index_name",
            "index_search_key",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:project-detail", "lookup_field": "pk"},
        }


class CdxQuerySerializer(serializers.ModelSerializer):
    class Meta:
        model = CdxQuery
        fields = [
            "id",
            "url",
            "domain_name",
            "from_date",
            "to_date",
            "project",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:domain-detail", "lookup_field": "pk"},
        }
