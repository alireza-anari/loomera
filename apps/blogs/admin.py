from django.contrib import admin

from .models import Blogs, BlogsGallery, GroupBlog


# -------------------------------------------------------------------------------------------------
class BlogsGalleryInlineAdmin(admin.TabularInline):
    model = BlogsGallery
    extra = 1


@admin.register(Blogs)
class BlogsAdmin(admin.ModelAdmin):
    list_display = ["title", "summary", "author", "register_date", "view_number", "is_active"]
    list_filter = ["author", "is_active"]
    ordering = ["register_date", "is_active"]
    inlines = [BlogsGalleryInlineAdmin]


# -------------------------------------------------------------------------------------------------
@admin.register(GroupBlog)
class GroupBlogAdmin(admin.ModelAdmin):
    list_display = ["group_title"]
