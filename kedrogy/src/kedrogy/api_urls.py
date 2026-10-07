from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

router = DefaultRouter()
router.register(r"datasets", api_views.DatasetViewSet)
router.register(r"models", api_views.MLModelViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "tasks/<str:task_type>/<str:result_id>/status/",
        api_views.task_status,
        name="task-status",
    ),
]
