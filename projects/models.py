from django.db import models
from django.urls import reverse


class Project(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ("-created_at", "name")

    def get_absolute_url(self):
        return reverse("projects:detail", kwargs={"slug": self.slug})

    def get_update_url(self):
        return reverse("projects:update", kwargs={"slug": self.slug})

    def get_delete_url(self):
        return reverse("projects:delete", kwargs={"slug": self.slug})

    def get_create_url(self):
        return reverse("projects:create")

    def get_list_url(self):
        return reverse("projects:list")

    def get_add_domain_url(self):
        return reverse("domains:add", kwargs={"slug": self.slug})

    def get_add_domains_url(self):
        return reverse("domains:add_domains", kwargs={"slug": self.slug})


class Domain(models.Model):
    id = models.AutoField(primary_key=True)
    domain_name = models.CharField(max_length=256)
    from_date = models.DateField(blank=True, null=True)
    to_date = models.DateField(blank=True, null=True)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.domain_name

    class Meta:
        verbose_name = "Domain"
        verbose_name_plural = "Domains"
        ordering = ("-created_at", "domain_name")

    def get_absolute_url(self):
        return reverse("domains:detail", kwargs={"pk": self.pk})

    def get_update_url(self):
        return reverse("domains:update", kwargs={"pk": self.pk})

    def get_delete_url(self):
        return reverse("domains:delete", kwargs={"pk": self.pk})

    def get_create_url(self):
        return reverse("domains:create")

    def get_list_url(self):
        return reverse("domains:list")

    def get_add_domain_url(self):
        return reverse("domains:add", kwargs={"slug": self.slug})

    def get_add_domains_url(self):
        return reverse("domains:add_domains", kwargs={"slug": self.slug})


class Page(models.Model):
    id = models.AutoField(primary_key=True)
    domain = models.ForeignKey("projects.Domain", on_delete=models.CASCADE)
    domain_name = models.CharField(max_length=256)
    project = models.CharField(max_length=256)
    original_url = models.URLField(max_length=256)
    wayback_machine_url = models.URLField(max_length=512)
    title = models.CharField(max_length=256, blank=True)
    timestamp = models.DateTimeField()
    unix_timestamp = models.IntegerField()
    raw = models.TextField(blank=True)
    text = models.TextField(blank=True)
    mimetype = models.CharField(max_length=256)
    status_code = models.IntegerField()
    digest = models.CharField(max_length=256)
    length = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.wayback_machine_url

    class Meta:
        verbose_name = "Page"
        verbose_name_plural = "Pages"
        ordering = ("-created_at", "domain_name")

    def get_absolute_url(self):
        return reverse("pages:detail", kwargs={"pk": self.pk})

    def get_update_url(self):
        return reverse("pages:update", kwargs={"pk": self.pk})

    def get_delete_url(self):
        return reverse("pages:delete", kwargs={"pk": self.pk})

    def get_create_url(self):
        return reverse("pages:create")

    def get_list_url(self):
        return reverse("pages:list")

    def get_add_domain_url(self):
        return reverse("domains:add", kwargs={"id": self.id})

    def get_add_domains_url(self):
        return reverse("domains:add_domains", kwargs={"id": self.id})
