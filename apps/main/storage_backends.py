from urllib.parse import urlencode

from django.conf import settings
from storages.backends.s3 import S3Storage


class LoomeraS3MediaStorage(S3Storage):
    """S3 media storage that exposes uploaded media through Loomera.

    Liara/Nginx can intercept extension-looking paths before they reach Django.
    When MEDIA_PROXY_ENABLED=True, FileField/ImageField .url therefore uses a
    query-string based proxy URL such as::

        /asset-proxy/?path=images/services/example.png

    Reads and writes still use S3/Object Storage; only browser-facing URLs are
    routed through the Django proxy view.
    """

    def url(self, name, parameters=None, expire=None, http_method=None):
        if getattr(settings, "MEDIA_PROXY_ENABLED", False):
            media_url = getattr(settings, "MEDIA_PROXY_URL", "/asset-proxy/") or "/asset-proxy/"
            # Liara/Nginx may intercept any path that starts with /media before Django.
            # Keep browser-facing media proxy URLs under a non-media prefix.
            if str(media_url).startswith("/media"):
                media_url = "/asset-proxy/"
            if not media_url.startswith("/") and not media_url.startswith("http"):
                media_url = f"/{media_url}"
            if not media_url.endswith("/"):
                media_url = f"{media_url}/"
            clean_name = str(name).lstrip("/")
            return f"{media_url}?{urlencode({'path': clean_name})}"
        return super().url(
            name,
            parameters=parameters,
            expire=expire,
            http_method=http_method,
        )
