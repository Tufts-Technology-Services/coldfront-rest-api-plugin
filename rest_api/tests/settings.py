"""Django settings for the plugin's test suite.

Builds on ColdFront's own settings so the core apps and models match a real deployment, then
swaps in an in-memory database so the tests need no services.
"""

from coldfront.config.settings import *  # noqa: F403

# ColdFront adds the DRF apps only with PLUGIN_API, which the deployment turns off for this plugin,
# so the deployment adds them itself, and so do the tests. A shell with PLUGIN_API set would add them
# twice, and ColdFront's API with them, so those are dropped first.
_DRF_APPS = ["django_filters", "rest_framework", "rest_framework.authtoken"]
INSTALLED_APPS = [  # noqa: F405
    *[app for app in INSTALLED_APPS if app not in [*_DRF_APPS, "coldfront.plugins.api"]],  # noqa: F405
    "django_filters",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_api",
]

# Copied from ColdFront's coldfront/config/plugins/api.py, (C) ColdFront Authors, AGPL-3.0-or-later:
# the values ColdFront's PLUGIN_API sets, which the deployment sets in its own settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}

# rest_api/urls.py is mounted by the deployment, so the tests mount it too
ROOT_URLCONF = "rest_api.tests.urls"

# In memory, whatever DB_URL says: ColdFront's settings take the database from it, and in a shell
# where it names a real server, the tests would create their database there.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# a deliberately weak hasher: creating users is much faster, and nothing here checks its strength
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
