#!/usr/bin/env python
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _read_dotenv_value(key: str) -> str | None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return None

    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        return None

    return None


def main():
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE",
        _read_dotenv_value("DJANGO_SETTINGS_MODULE") or "loomera.settings.production",
    )

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Make sure it's installed and available on your PYTHONPATH."
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
