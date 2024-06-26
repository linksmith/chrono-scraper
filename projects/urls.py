from django.urls import path

from .views import ProjectCreateView, ProjectIndexView, ProjectListView, ProjectUpdateView

urlpatterns = [
    path("", ProjectListView.as_view(), name="list-projects"),
    path("create", ProjectCreateView.as_view(), name="create-project"),
    path("<int:pk>/update", ProjectUpdateView.as_view(), name="update-project"),
    path("<int:pk>/index", ProjectIndexView.as_view(), name="index-project"),
]
