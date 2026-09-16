import threading

from django.contrib.auth import SESSION_KEY


class RequestMiddleware:
    def __init__(self, get_response, thread_local=threading.local()):
        self.get_response = get_response
        self.thread_local = thread_local

    def __call__(self, request):
        self.thread_local.current_request = request
        response = self.get_response(request)
        return response


class AuthenticatedHtmlNoStoreMiddleware:
    """Prevent authenticated HTML pages from being restored from browser history cache.

    Public/anonymous responses are untouched. This keeps public cacheability intact while
    ensuring private account/booking pages cannot be revealed via Back after logout/cancel.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Use the authenticated session marker rather than evaluating request.user.
        # Evaluating Django's lazy user here can perform a model lookup before the
        # view runs and can interfere with endpoints/tests that intentionally mock
        # app/model resolution. SessionMiddleware + AuthenticationMiddleware run
        # before this middleware, so the auth session key is authoritative here.
        was_authenticated = SESSION_KEY in request.session
        response = self.get_response(request)
        content_type = (response.get("Content-Type", "") or "").lower()
        if was_authenticated and "text/html" in content_type:
            response["Cache-Control"] = "private, no-store, no-cache, max-age=0, must-revalidate"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
