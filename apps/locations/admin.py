from django.contrib.gis import admin

from .models import Neighborhood


@admin.register(Neighborhood)
class NeighborhoodAdmin(admin.GISModelAdmin):
    list_display = ["name", "polygon"]
