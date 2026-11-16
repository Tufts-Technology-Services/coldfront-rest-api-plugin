# coldfront-rest-api-plugin

A [ColdFront](https://coldfront.readthedocs.io/) plugin that serves a read-only REST API for
other Tufts systems: a person's projects, allocations filtered by resource, the quota and usage
of a person's home and scratch, and live usage for storage allocations.

It replaces ColdFront's own API plugin (`PLUGIN_API`), which has no filters or pagination and
returns private attributes to anyone who can see the project.

**Status:** the projects endpoint is built; allocations and storage are to come. The
design, decisions and phases are in [docs/rest-api-plan.md](docs/rest-api-plan.md).

## Endpoints

- `GET /api/v2/users/<username>/projects/`: the Active projects a person is an Active member or
  PI of, with their membership and project attributes. Paginated: 100 per page, up to 1000 with
  `?page_size=`.

Every endpoint is also served at `/api/latest/...` and at `/api/...` with no version, both of
which follow the newest version: today, v2. A system that mustn't break when a v3 arrives should
call `/api/v2/`.

Who sees what follows ColdFront's own rules. Anyone can ask about themselves. Superusers can ask
about anyone, as can holders of ColdFront's `project.can_view_all_projects` (for projects) or
`allocation.can_view_all_allocations` (for allocations), and service accounts with the API's
`rest_api.view_any_person`. The staff flag alone isn't enough. For anyone else, another person's
username is a 404. Only superusers see private attributes.

### Your own token

Anyone signed in to ColdFront can make a token for themselves at `/api/token/`. The full token is
shown once, right after it's made; after that the page shows only its last six characters, with
buttons to regenerate or revoke it. Making, replacing and revoking a token are logged at INFO to
the `rest_api.tokens` logger. To link to it from the user profile page, the site's
`user/user_profile.html` includes the plugin's row inside its `profile_contents` block:

```django
{% include "rest_api/profile_token_row.html" %}
```

The row appears only on your own profile.

### Service accounts

A system calling the API gets an ordinary user, with no staff flag and an unusable password, that
holds `rest_api.view_any_person` ("Can look up any person through the REST API" in the admin),
and a token an admin issues:

```bash
coldfront drf_create_token <username>
```

Callers send it as `Authorization: Token <token>`. Each lookup a service account makes is logged
at INFO to the `rest_api.lookups` logger.

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

and mounts `rest_api.urls` at `api/`. The endpoints are under `/api/v2/` (ColdFront's built-in
API, which used to be at `/api/`, counts as v1), `/api/latest/` and `/api/`, and the token page
is at `/api/token/`.

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
- `rest_api/serializers.py`: the project, project user and project attribute serializers, from
  ColdFront's `coldfront/plugins/api/serializers.py`.
