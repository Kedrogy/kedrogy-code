"""Administrative views cannot bypass reviewed cleanup or binding workflows."""
from django.contrib import admin
from .models import DjangoDataset

@admin.register(DjangoDataset)
class DatasetAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
