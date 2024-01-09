from django.contrib import admin

from .models import Domain, Page, Project

admin.site.register(Project)
admin.site.register(Domain)
admin.site.register(Page)
