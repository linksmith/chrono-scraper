from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import DetailView
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import ListView

from .forms import CdxQueryInlineCreateFormSet, CdxQueryInlineUpdateFormSet, ProjectForm
from .models import Project


class ProjectListView(LoginRequiredMixin, ListView):
    template_name = "projects/list-projects.html"
    model = Project
    context_object_name = "projects"
    paginate_by = 10

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)


class ProjectDetailView(LoginRequiredMixin, DetailView):
    template_name = "projects/detail-project.html"
    model = Project
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)


class ProjectIndexView(LoginRequiredMixin, DetailView):
    model = Project
    template_name = "projects/index-project.html"
    success_url = reverse_lazy("list-projects")
    context_object_name = "project"

    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)


class ProjectCreateView(CreateView):
    model = Project
    template_name = "projects/create-project.html"
    success_url = reverse_lazy("list-projects")
    form_class = ProjectForm

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["cdx_queries"] = CdxQueryInlineCreateFormSet(self.request.POST)
        else:
            data["cdx_queries"] = CdxQueryInlineCreateFormSet()
        return data

    def form_valid(self, form):
        action = self.request.POST.get("action")

        context = self.get_context_data()
        cdx_queries = context["cdx_queries"]
        with transaction.atomic():
            form.instance.user = self.request.user
            self.object = form.save()
            self.object.save()
            if cdx_queries.is_valid():
                for cdx_query_form in cdx_queries:
                    cdx_query = cdx_query_form.instance
                    cdx_query.project = self.object
                    cdx_query.save()

        if action == "create_project_and_go_to_index":
            self.success_url = reverse_lazy("index-project", kwargs={"pk": self.object.pk})
        elif action == "create_project":
            self.success_url = reverse_lazy("list-projects")

        return super().form_valid(form)


class ProjectUpdateView(UpdateView):
    model = Project
    template_name = "projects/update-project.html"
    success_url = reverse_lazy("list-projects")
    form_class = ProjectForm

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        if self.request.POST:
            data["cdx_queries"] = CdxQueryInlineUpdateFormSet(self.request.POST, instance=self.object)
        else:
            data["cdx_queries"] = CdxQueryInlineUpdateFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        action = self.request.POST.get("action")

        context = self.get_context_data()
        cdx_queries = context["cdx_queries"]
        self.object = form.save()
        if cdx_queries.is_valid():
            cdx_queries.instance = self.object
            cdx_queries.save()
        else:
            context["formset_errors"] = cdx_queries.errors

        if action == "create_project_and_go_to_index":
            self.success_url = reverse_lazy("index-project", kwargs={"pk": self.object.pk})
        elif action == "create_project":
            self.success_url = reverse_lazy("list-projects")

        return (
            super().form_valid(form)
            if form.is_valid() and cdx_queries.is_valid()
            else self.render_to_response(context)
        )
