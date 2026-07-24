from .base import *

DEBUG = True
# Use env-provided allowed hosts instead of clearing the list
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=ALLOWED_HOSTS)
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=CSRF_TRUSTED_ORIGINS
)
