# Generated by Django 4.2.9 on 2024-01-24 19:42

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0007_alter_project_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="description",
            field=models.TextField(blank=True, max_length=200, null=True),
        ),
    ]
