from django.db.models import TextChoices


class StatusChoices(TextChoices):
    NO_INDEX = "no_index", "No Index"
    IN_PROGRESS = "in_progress", "In Progress"
    INDEXED = "indexed", "Indexed"


class ProjectStatusChoices(TextChoices):
    NO_INDEX = StatusChoices.NO_INDEX.value
    IN_PROGRESS = StatusChoices.IN_PROGRESS.value
    INDEXED = StatusChoices.INDEXED.value


class DomainStatusChoices(TextChoices):
    NO_INDEX = StatusChoices.NO_INDEX.value
    IN_PROGRESS = StatusChoices.IN_PROGRESS.value
    INDEXED = StatusChoices.INDEXED.value
