"""
System checks for the apps the API needs, so a deployment that's missing them stops at
`manage.py check` and `migrate` instead of failing requests.
"""

from django.apps import apps
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
