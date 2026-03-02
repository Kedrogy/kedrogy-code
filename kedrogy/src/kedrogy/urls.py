from django.urls import path

from . import views

app_name = "kedrogy"
urlpatterns = [
    path("", views.index, name="index"),
    path("<int:dataset_id>/", views.detail, name="detail"),
    path("new_dataset/", views.new_dataset, name="new"),
    path("delete_dataset/<int:dataset_id>", views.delete_dataset, name="delete"),
    path("label_dataset/<int:dataset_id>", views.label_dataset, name="label"),
    path(
        "new_dataset_poll/<str:dataset_name>/<str:result_id>/",
        views.new_dataset_poll,
        name="poll",
    ),
    path(
        "new_dataset_result/<str:result_id>/",
        views.new_dataset_result,
        name="new-dataset-result",
    ),
    path("new_model/<int:dataset_id>", views.new_model, name="new_model"),
    path("model/<int:model_id>/", views.detail_model, name="detail_model"),
    path("train_model/<int:model_id>/", views.train_model, name="train_model"),
    path("delete_model/<int:model_id>", views.delete_model, name="delete_model"),
    path(
        "new_train_result/<str:result_id>/",
        views.new_train_result,
        name="new-train-result",
    ),
    path("serve_model/<int:model_id>/", views.serve_model, name="serve_model"),
    path(
        "new_serve_result/<str:result_id>/",
        views.new_serve_result,
        name="new-serve-result",
    ),
    path(
        "new_delete_model_result/<str:result_id>/",
        views.new_delete_model_result,
        name="new-delete-model-result",
    ),
    path("predict_model/<int:model_id>/", views.predict_model, name="predict_model"),
    path(
        "api/datasets/result/<int:result_id>/",
        views.new_dataset_result,
        name="api-dataset-result",
    ),
    path("api/datasets/<int:dataset_id>/", views.dataset_detail_api),
    path("api/models/<int:model_id>/train/", views.train_model_api),
    path("api/models/<int:model_id>/serve/", views.serve_model_api),
    path("api/train/result/<str:result_id>/", views.train_result_api),
    path("api/serve/result/<str:result_id>/", views.serve_result_api),
]
