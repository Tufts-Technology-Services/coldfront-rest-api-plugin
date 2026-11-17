"""
System checks for the apps the API needs, so a deployment that's missing them stops at
`manage.py check` and `migrate` instead of failing requests.
"""

from django.apps import apps
from django.conf import settings
from django.core import checks

# ColdFront installs these only with PLUGIN_API, which is off where this plugin runs
REQUIRED_APPS = ["rest_framework", "rest_framework.authtoken", "django_filters"]


@checks.register()
def check_installed_apps(app_configs, **kwargs):
    """E001 for each app in REQUIRED_APPS that isn't installed; E002 if ColdFront's own API is."""
    errors = [
        checks.Error(
            f"{app} isn't in INSTALLED_APPS, and the REST API needs it.",
            hint="With PLUGIN_API off, ColdFront doesn't install it: add it alongside rest_api.",
            id="rest_api.E001",
        )
        for app in REQUIRED_APPS
        if not apps.is_installed(app)
    ]
    if apps.is_installed("coldfront.plugins.api"):
        errors.append(
            checks.Error(
                "ColdFront's own API (coldfront.plugins.api) is installed alongside rest_api.",
                hint=(
                    "Turn PLUGIN_API off. ColdFront's API returns private attributes to anyone who can see "
                    "the project, and serves /api/, where rest_api is mounted."
                ),
                id="rest_api.E002",
            )
        )
    return errors


def storage_area_error(message):
    return checks.Error(
        message,
        hint=(
            "USER_STORAGE_AREAS maps each area to the STORAGE_PLUGIN_CLIENTS entry it lives on and its "
            'directory quota there: {"home": {"client": "hpc", "path": "/homedir"}}.'
        ),
        id="rest_api.E003",
    )


@checks.register()
def check_user_storage_areas(app_configs, **kwargs):
    """E003 for each way USER_STORAGE_AREAS is malformed, if it's set. Unset, there are no storage areas."""
    areas = getattr(settings, "USER_STORAGE_AREAS", None)
    if areas is None:
        return []
    if not isinstance(areas, dict):
        return [storage_area_error("USER_STORAGE_AREAS must be a dict of areas.")]
    client_keys = {entry.get("client_key") for entry in getattr(settings, "STORAGE_PLUGIN_CLIENTS", []) or []}
    errors = []
    for name, area in areas.items():
        if not name or "/" in str(name):
            # the name is a URL segment: storage/<area>/
            errors.append(storage_area_error(f"The storage area name {name!r} must be non-empty, with no slash."))
        elif not isinstance(area, dict):
            errors.append(storage_area_error(f"USER_STORAGE_AREAS[{name!r}] must be a dict with a client and a path."))
        elif not area.get("client"):
            errors.append(storage_area_error(f"USER_STORAGE_AREAS[{name!r}] names no client."))
        elif not str(area.get("path") or "").startswith("/"):
            errors.append(
                storage_area_error(f"USER_STORAGE_AREAS[{name!r}] needs an absolute path, not {area.get('path')!r}.")
            )
        elif area["client"] not in client_keys:
            errors.append(
                storage_area_error(
                    f"USER_STORAGE_AREAS[{name!r}] names client {area['client']!r}, which isn't in STORAGE_PLUGIN_CLIENTS."
                )
            )
    return errors
