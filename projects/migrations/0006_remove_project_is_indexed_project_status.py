# Generated by Django 4.2.9 on 2024-01-24 19:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0005_rename_search_index_key_project_index_search_key"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="project",
            name="is_indexed",
        ),
        migrations.AddField(
            model_name="project",
            name="status",
            field=models.CharField(
                choices=[("no_index", "No Index"), ("in_progress", "In Progress"), ("indexed", "Indexed")],
                default="no_index",
            ),
        ),
    ]