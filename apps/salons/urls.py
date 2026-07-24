from django.urls import path

from .views import (
    DetailSalonView,
    LegacySalonDetailRedirectView,
    PublicHomeView,
    ShowSalonsView,
    SalonStylistProfileView,
)

# -------------------------------------------------------------------
app_name = "salons"
urlpatterns = [
    path("", PublicHomeView.as_view(), name="home"),
    path("salons/", ShowSalonsView.as_view(), name="show_salons"),
    path("salons/<str:salon_slug>/", DetailSalonView.as_view(), name="detail_salon_slug"),
    path("salons/<str:salon_slug>/stylists/<int:stylist_id>/", SalonStylistProfileView.as_view(), name="stylist_profile_slug"),
    path("detail_salon/<int:salon_id>/", LegacySalonDetailRedirectView.as_view(), name="detail_salon"),
    path("detail_salon/<int:salon_id>/stylists/<int:stylist_id>/", SalonStylistProfileView.as_view(), name="stylist_profile"),
]
