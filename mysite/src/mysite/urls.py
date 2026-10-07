"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import set_language
from django.urls import path, include

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from . import views
from .errors import health, error_400, error_403, error_404, error_500


urlpatterns = (
    [
        path("health/", health),
        path("api/", include("kedrogy.api_urls")),
        path("", include("kedrogy.urls")),
        path("admin/", admin.site.urls),
        path("logout/", views.logout, name="logout"),
        path("i18n/", set_language, name="set_language"),
    ]
    + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
)  # https://docs.djangoproject.com/en/6.0/howto/static-files/#serving-static-files-during-development

urlpatterns += i18n_patterns(
    path("", include("kedrogy.urls", namespace="kedrogy_i18n")),
)

handler400 = error_400
handler403 = error_403
handler404 = error_404
handler500 = error_500
