# coldfront-rest-api-plugin

A [ColdFront](https://coldfront.readthedocs.io/) plugin that will serve a read-only REST API for
other Tufts systems: a person's projects, allocations filtered by resource, and a person's
storage quotas and usage, read live from VAST.

It replaces ColdFront's own API plugin (`PLUGIN_API`), which has no filters or pagination and
returns private attributes to anyone who can see the project.

**Status:** set up, nothing built yet. The design, decisions and phases are in
[docs/rest-api-plan.md](docs/rest-api-plan.md).

## Requirements

- ColdFront 1.1.8 or later (but not 2.x)
- Python 3.11 or later
- `PLUGIN_API` off

## Installation

The plugin is installed as part of Tufts' ColdFront deployment: the fork's `tufts` extra names it,
and coldfront-ansible adds it to the settings. Turning `PLUGIN_API` off removes the Django REST
Framework apps ColdFront would otherwise install, so the deployment adds them alongside the
plugin:

```python
INSTALLED_APPS += [
    "django_filters",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_api",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
}
```

and mounts `rest_api.urls` at `api/`. The endpoints are under `/api/v1/`.

## Development

```bash
uv sync
uv run pre-commit install
uv run pytest
uv run ruff check
uv run ruff format --check
```

The tests use `rest_api/tests/settings.py`: ColdFront's settings, the DRF apps, and an in-memory
SQLite database.

## Credits

This plugin builds on ColdFront's own API plugin, `coldfront.plugins.api`
([source](https://github.com/coldfront/coldfront/tree/main/coldfront/plugins/api)),
(C) ColdFront Authors, licensed AGPL-3.0-or-later. This plugin is AGPL-3.0-or-later too, and
lists ColdFront Authors among its authors. Code copied or adapted from ColdFront says so at the
top of the file, and is listed here:

- `rest_api/tests/settings.py`: the `REST_FRAMEWORK` settings, from ColdFront's
  `coldfront/config/plugins/api.py`.
