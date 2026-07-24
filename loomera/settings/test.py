from .development import *

import os
from glob import glob

DEBUG = True
SECRET_KEY = env("SECRET_KEY", default="test-secret-key")

if os.name == "nt":
    OSGEO4W_ROOT = env("OSGEO4W_ROOT", default=r"C:\OSGeo4W")
    OSGEO4W_BIN = os.path.join(OSGEO4W_ROOT, "bin")

    if os.path.isdir(OSGEO4W_BIN):
        # برای Python 3.8+ روی ویندوز، فقط PATH همیشه کافی نیست.
        os.add_dll_directory(OSGEO4W_BIN)

        os.environ["PATH"] = OSGEO4W_BIN + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("GDAL_DATA", os.path.join(OSGEO4W_ROOT, "share", "gdal"))
        os.environ.setdefault("PROJ_LIB", os.path.join(OSGEO4W_ROOT, "share", "proj"))

        gdal_candidates = sorted(glob(os.path.join(OSGEO4W_BIN, "gdal*.dll")))
        geos_candidates = sorted(glob(os.path.join(OSGEO4W_BIN, "geos_c*.dll")))
        spatialite_candidates = sorted(
            glob(os.path.join(OSGEO4W_BIN, "mod_spatialite*.dll"))
        )

        if gdal_candidates:
            GDAL_LIBRARY_PATH = gdal_candidates[-1]

        if geos_candidates:
            GEOS_LIBRARY_PATH = geos_candidates[-1]

        if spatialite_candidates:
            SPATIALITE_LIBRARY_PATH = spatialite_candidates[-1]
        else:
            SPATIALITE_LIBRARY_PATH = os.path.join(OSGEO4W_BIN, "mod_spatialite.dll")
    else:
        SPATIALITE_LIBRARY_PATH = env(
            "SPATIALITE_LIBRARY_PATH",
            default=r"C:\OSGeo4W\bin\mod_spatialite.dll",
        )
else:
    SPATIALITE_LIBRARY_PATH = env(
        "SPATIALITE_LIBRARY_PATH", default="libspatialite.so.8"
    )

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.spatialite",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = BASE_DIR / "test_media"
STATIC_ROOT = BASE_DIR / "test_staticfiles"


