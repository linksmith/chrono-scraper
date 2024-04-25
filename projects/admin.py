from datetime import date

from django.contrib import admin
from django.utils import timezone

from .models import CdxQuery, Page, Project


class CdxQueryInline(admin.TabularInline):  # or admin.StackedInline
    model = CdxQuery
    extra = 0  # Number of empty forms to display
    can_delete = False
    exclude = ("pages",)  # Exclude the pages field


class CdxQueryPageInline(admin.TabularInline):  # or admin.StackedInline
    model = CdxQuery.pages.through
    extra = 0  # Number of empty forms to display
    can_delete = False


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    readonly_fields = (
        "id",
        "index_name",
        "index_task_id",
        "index_start_time",
        "index_end_time",
        "created_at",
        "updated_at",
    )
    inlines = [CdxQueryInline]
    fields = (
        "id",
        "name",
        "description",
        "index_name",
        "index_search_key",
        "index_task_id",
        "index_start_time",
        "index_end_time",
        "status",
        "user",
        "created_at",
        "updated_at",
    )

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        if obj is None:  # This means the form is for adding a new instance
            fields = [field for field in fields if field != "index_name"]
        return fields

    def response_change(self, request, project: Project):
        if "_rebuild_index_button" in request.POST:
            project.rebuild_index()
            self.message_user(request, "Index (re)building...")
        if "_delete_pages_and_index_button" in request.POST:
            project.delete_pages_and_index()
            self.message_user(request, "Index deleted...")
        return super().response_change(request, project)


@admin.register(CdxQuery)
class CdxQueryAdmin(admin.ModelAdmin):
    # inlines = [CdxQueryPageInline]
    list_filter = ("project",)
    exclude = ("pages",)  # Exclude the pages field

    def response_change(self, request, cdx_query: CdxQuery):
        if "_delete_pages_button" in request.POST:
            cdx_query.delete_pages()
            self.message_user(request, "Deleted pages...")

        return super().response_change(request, cdx_query)

    def save_model(self, request, obj, form, change):
        if not obj.from_date:
            obj.from_date = date(1990, 1, 1)
        if not obj.to_date:
            obj.to_date = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("wayback_machine_url",)

    readonly_fields = (
        "wayback_machine_url",
        "original_url",
        "title",
        "unix_timestamp",
        "mimetype",
        "status_code",
        "digest",
        "length",
        "meilisearch_id",
    )
