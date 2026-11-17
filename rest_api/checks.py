"""
System checks for the apps the API needs, so a deployment that's missing them stops at
`manage.py check` and `migrate` instead of failing requests.
"""

from coldfront_utils.api_extensions import registered_extensions
from django.apps import apps
from django.core import checks
from django.urls import Resolver404, resolve

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


# each kind's extension route: as an error shows it, and as a path to resolve with sample values
EXTENSION_ROUTES = {
    "person": ("users/<username>/{name}/", "/v2/users/someone/{name}/"),
    "project": ("projects/<id>/{name}/", "/v2/projects/1/{name}/"),
    "allocation": ("allocations/<id>/{name}/", "/v2/allocations/1/{name}/"),
}


@checks.register()
def check_extension_names(app_configs, **kwargs):
    """E003 for each registered extension whose URL one of the API's own routes serves instead, such
    as a person extension named "projects". Found by resolving the extension's URL, so it covers
    every route the API has, not a list kept by hand."""
    from rest_api.extension_views import ExtensionView

    errors = []
    for kind, extension_classes in registered_extensions().items():
        shown, sample = EXTENSION_ROUTES[kind]
        for extension_class in extension_classes:
            name = extension_class.name
            try:
                view_class = getattr(
                    resolve(sample.format(name=name), urlconf="rest_api.urls").func, "view_class", None
                )
            except Resolver404:
                view_class = None
            if not (isinstance(view_class, type) and issubclass(view_class, ExtensionView)):
                errors.append(
                    checks.Error(
                        f"The {kind} extension {extension_class.__name__} is named {name!r}, and one of the API's "
                        f"own routes serves {shown.format(name=name)} instead.",
                        hint="Rename the extension, in the plugin that registers it.",
                        id="rest_api.E003",
                    )
                )
    return errors
