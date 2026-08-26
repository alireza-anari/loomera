"""
URL configuration for loomera project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
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

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve
from apps.main.views import (
    HealthCheckView,
    PartnerPageView,
    RobotsTxtView,
    SupportView,
    media_proxy,
)
from apps.articles.sitemaps import (
    ArticleCategorySitemap,
    ArticleSitemap,
    ArticleTagSitemap,
)
from apps.main.sitemaps import StaticViewSitemap
from apps.salons.sitemaps import SalonSitemap
from apps.services.sitemaps import ServiceGroupSitemap, ServiceSitemap

sitemaps = {
    "static": StaticViewSitemap,
    "salons": SalonSitemap,
    "services": ServiceSitemap,
    "service_groups": ServiceGroupSitemap,
    "articles": ArticleSitemap,
    "article_categories": ArticleCategorySitemap,
    "article_tags": ArticleTagSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("help/", include("apps.help_center.urls", namespace="help_center")),
    path("support/", SupportView.as_view(), name="support"),
    path("partners/", PartnerPageView.as_view(), name="partners"),
    path("join-loomera/", PartnerPageView.as_view(), name="join_loomera"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("api/", include("apps.api.urls", namespace="api")),
    path("robots.txt", RobotsTxtView.as_view(), name="robots_txt"),
    path("robot.txt", RobotsTxtView.as_view(), name="robot_txt_legacy"),
    path("asset-proxy/", media_proxy, name="asset_proxy"),
    re_path(r"^asset-proxy/(?P<path>.+)$", media_proxy, name="asset_proxy_legacy"),
    path("media-proxy/", media_proxy, name="media_proxy"),
    re_path(r"^media-proxy/(?P<path>.+)$", media_proxy, name="media_proxy_legacy"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("main/", include("apps.main.urls", namespace="main")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("services/", include("apps.services.urls", namespace="services")),
    path("", include("apps.salons.urls", namespace="salons")),
    path("stylists/", include("apps.stylists.urls", namespace="stylists")),
    # path("blogs/", include("apps.blogs.urls", namespace="blogs")),
    path("orders/", include("apps.orders.urls", namespace="orders")),
    # path("discounts/", include("apps.discounts.urls", namespace="discounts")),
    path("payments/", include("apps.payments.urls", namespace="payments")),
    path("csf/", include("apps.comments_scores_favories.urls", namespace="csf")),
    path("search/", include("apps.search.urls", namespace="search")),
    # path("locations/", include("apps.locations.urls", namespace="locations")),
    path("dashboards/", include("apps.dashboards.urls", namespace="dashboards")),
    path(
        "notifications/", include("apps.notifications.urls", namespace="notifications")
    ),
    path(
        "messaging/webhooks/bale/", include("apps.bale_bot.urls", namespace="bale_bot")
    ),
    path("messaging/", include("apps.messaging.urls", namespace="messaging")),
    path("platform/", include("apps.platform_admin.urls", namespace="platform_admin")),
    path("magazine/", include("apps.articles.urls", namespace="articles")),
]

if settings.DEBUG or getattr(settings, "SERVE_MEDIA_INSECURELY", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
