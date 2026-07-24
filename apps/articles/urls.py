from django.urls import path

from .views import (
    ArticleCategoryView,
    ArticleDetailView,
    ArticleTagView,
    ContentReportCreateView,
    MagazineHomeView,
    StoryClickTrackView,
    StoryExploreView,
    StoryViewTrackView,
)

app_name = "articles"

urlpatterns = [
    path("", MagazineHomeView.as_view(), name="magazine_home"),
    path("category/<str:slug>/", ArticleCategoryView.as_view(), name="category_detail"),
    path("tag/<str:slug>/", ArticleTagView.as_view(), name="tag_detail"),
    path("stories/", StoryExploreView.as_view(), name="story_explore"),
    path("stories/<int:pk>/view/", StoryViewTrackView.as_view(), name="story_view"),
    path("stories/<int:pk>/click/", StoryClickTrackView.as_view(), name="story_click"),
    path("report/<str:model_name>/<int:object_id>/", ContentReportCreateView.as_view(), name="content_report"),
    path("<str:slug>/", ArticleDetailView.as_view(), name="article_detail"),
]
