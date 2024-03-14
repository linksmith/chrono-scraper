from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import DetailView
from django.views.generic.edit import CreateView, UpdateView
from django.views.generic.list import ListView

from .forms import DomainInlineCreateFormSet, DomainInlineUpdateFormSet, ProjectForm
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


class ProjectCreateView(CreateView):
    model = Project
    success_url = reverse_lazy("list-projects")
    template_name = "projects/create-project.html"
    form_class = ProjectForm

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["domains"] = DomainInlineCreateFormSet(self.request.POST)
        else:
            data["domains"] = DomainInlineCreateFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        domains = context["domains"]
        with transaction.atomic():
            form.instance.user = self.request.user
            self.object = form.save()
            self.object.save()
            if domains.is_valid():
                for domain_form in domains:
                    domain = domain_form.instance
                    domain.project = self.object
                    domain.save()
        return super().form_valid(form)


class ProjectUpdateView(UpdateView):
    model = Project
    template_name = "projects/update-project.html"
    success_url = reverse_lazy("list-projects")
    form_class = ProjectForm

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        if self.request.POST:
            data["domains"] = DomainInlineUpdateFormSet(self.request.POST, instance=self.object)
        else:
            data["domains"] = DomainInlineUpdateFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        domains = context["domains"]
        self.object = form.save()
        if domains.is_valid():
            domains.instance = self.object
            domains.save()
        else:
            context["formset_errors"] = domains.errors

        return super().form_valid(form) if form.is_valid() and domains.is_valid() else self.render_to_response(context)
