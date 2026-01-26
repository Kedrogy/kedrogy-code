from django.urls import path

from . import views

app_name = "django_dataset_new"
urlpatterns = [
    path("", views.index, name="index"),
    path("<int:dataset_id>/", views.detail, name="detail"),

    path("new_dataset/", views.new_dataset, name="new"),

    path("new_dataset_poll/<str:dataset_name>/<str:result_id>/", views.new_dataset_poll, name="poll"),
    path("new_dataset_result/<str:result_id>/", views.new_dataset_result, name="new-dataset-result"),
]
