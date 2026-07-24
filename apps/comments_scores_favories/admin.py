from django.contrib import admin

from .models import Comments


# --------------------------------------------------------------------------------
@admin.register(Comments)
class CommentsAdmin(admin.ModelAdmin):
    list_display = [
        "comment_user",
        "service",
        "salon",
        "stylist",
        "is_active",
    ]
    list_editable = [
        "is_active",
    ]
