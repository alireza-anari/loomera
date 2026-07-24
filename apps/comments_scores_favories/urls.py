from django.urls import path

from .views import SalonCommentScoreView, addFavorite, get_favorite_salons, approve_comment

# --------------------------------------------------------------------------------------
app_name = "csf"
urlpatterns = [
    path(
        "comment-score/",
        SalonCommentScoreView.as_view(),
        name="salon_comment_score",
    ),
    path("add_favorite/", addFavorite, name="add_favorite"),
    path("favorite_salons/", get_favorite_salons, name="favorite_salons"),
    # path("like-work-sample/", like_work_sample, name="like_work_sample"),
    path(
        "approve-comment/<int:comment_id>/<int:customer_id>/",
        approve_comment,
        name="approve_comment",
    ),
]
