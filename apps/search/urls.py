from django.urls import path
from django.views.generic import RedirectView
from .views import (
    salon_search,
    SearchPageView,
    search_results_api,
    salon_list,
    FilterSalonView,
    loomera_search,
    salonify_search,
    customers_search,
    FilterCustomersView,
    AjaxSearchView,
    map_tile_proxy,
    reverse_geocode_proxy,
    search_suggestions,
    location_suggestions,
    record_search_click,
)

app_name = "search"

urlpatterns = [
    path("salon_search/", salon_search, name="salon_search"),
    path("", SearchPageView.as_view(), name="search_page"),
    path(
        "search/",
        RedirectView.as_view(
            pattern_name="search:search_page",
            permanent=False,
            query_string=True,
        ),
        name="search_page_legacy",
    ),
    path("results/", search_results_api, name="search_results_api"),
    path("salon_list", salon_list, name="salon_list"),
    path("filter_salon/", FilterSalonView.as_view(), name="filter_salon"),
    path("loomera_search/", loomera_search, name="loomera_search"),
    # Legacy public alias kept for backward compatibility with existing integrations.
    path("salonify_search/", salonify_search, name="salonify_search"),
    path("customers_search/", customers_search, name="customers_search"),
    path("filter_customers/", FilterCustomersView.as_view(), name="filter_customers"),
    path("ajax/", AjaxSearchView.as_view(), name="ajax_search"),
    path("map-tiles/<int:z>/<int:x>/<int:y>/", map_tile_proxy, name="map_tile_proxy"),
    path(
        "map-tiles/<int:z>/<int:x>/<int:y>",
        map_tile_proxy,
        name="map_tile_proxy_no_slash",
    ),
    path("reverse-geocode/", reverse_geocode_proxy, name="reverse_geocode_proxy"),
    path("suggestions/", search_suggestions, name="search_suggestions"),
    path("location-suggestions/", location_suggestions, name="location_suggestions"),
    path("click/", record_search_click, name="record_search_click"),
]
