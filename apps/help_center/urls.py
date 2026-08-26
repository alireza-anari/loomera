from django.urls import path

from . import views

app_name = "help_center"

urlpatterns = [
    path("", views.help_home, name="home"),
    path("search/", views.help_search, name="search"),
    path("article/<slug:slug>/", views.help_article, name="article"),
    path("api/context/", views.context_api, name="context_api"),
    path("api/chat/", views.chat_api, name="chat_api"),
]
