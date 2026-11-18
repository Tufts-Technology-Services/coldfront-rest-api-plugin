# coldfront-rest-api-plugin

A [ColdFront](https://coldfront.readthedocs.io/) plugin that serves a read-only REST API for
other Tufts systems: a person's projects, allocations filtered by resource, the quota and usage
of a person's home and scratch, and live usage for storage allocations.

It replaces ColdFront's own API plugin (`PLUGIN_API`), which has no filters or pagination and
returns private attributes to anyone who can see the project.

**Status:** the projects and allocations endpoints are built, and so are the routes plugins serve
their own data through ("Plugin extensions" below); storage is to come, as the storage plugin's
extension. The design, decisions and phases are in [docs/rest-api-plan.md](docs/rest-api-plan.md).

## Endpoints

- `GET /api/v2/users/<username>/projects/`: the projects a person is an Active member or PI of,
  with their membership and project attributes. New and Active ones, as ColdFront's project list
  shows them, unless `?status=` names others (`?status=Archived`, repeatable). Paginated: 100 per
  page, up to 1000 with `?page_size=`.
- `GET /api/v2/allocations/`: the allocations ColdFront's allocation list would show the caller,
  with their project, status, resources, dates and attributes (with usage). Filters, each
  repeatable: `resource_type` and `resource` (case-insensitive, partial), `status`, `project`
  (an id) and `username` (an Active allocation user or the project's PI). Paginated as above.
- `GET /api/v2/allocations/<id>/`: one allocation, for anyone ColdFront's allocation page would
  show it to; a 404 for anyone else.
- `GET /api/v2/extensions/`: the plugin extensions this deployment serves (below), by kind, each
  with its name, description, version and whether it's deprecated.

Every endpoint is also served at `/api/latest/...` and at `/api/...` with no version, both of
which follow the newest version: today, v2. A system that mustn't break when a v3 arrives should
call `/api/v2/`.

### Who can use it

Only people allowed to: holders of `rest_api.use_api` ("Can use the REST API" in the admin), which
the plugin's migrations give to a group, `rest_api_users`. Admins add people to that group.
Superusers are allowed without it. Anyone else gets a 403 from every endpoint, even with a token,
and from the token page, and their profile shows no token row. Taking someone out of the group
shuts out their token at once; it isn't deleted, and works again if they're added back.

### Who sees what

Who sees what follows ColdFront's own rules. Anyone allowed to use the API can ask about themselves. Superusers can ask
about anyone, as can holders of ColdFront's `project.can_view_all_projects` (for projects) or
`allocation.can_view_all_allocations` (for allocations), and service accounts with the API's
`rest_api.view_any_person`. The staff flag alone isn't enough. For anyone else, another person's
username is a 404. Only superusers see private attributes.

### Plugin extensions

Plugins serve their own data through the API by registering an extension with
`coldfront_utils.api_extensions` (see that package's README). Neither imports the other. The API
serves each one at

- `GET /api/v2/users/<username>/<name>/` and `.../<name>/<key>/`, for a person,
- `GET /api/v2/projects/<id>/<name>/` and `.../<name>/<key>/`, for a project,
- `GET /api/v2/allocations/<id>/<name>/` and `.../<name>/<key>/`, for an allocation,

under every prefix, with the request's query parameters passed to the extension. A summary lists
its items by key: an item's URL is the summary's URL plus `<key>/`. The extension decides who sees
its content, with permissions its plugin
defines; the rules above are only for the API's own endpoints. A person, project or allocation that
doesn't exist, and one the extension doesn't allow the caller, are the same 404, as is a name no
extension has. Parameters the extension can't use are a 400, and an extension that can't reach its
data a 503, each with a message; one that fails is a 500, logged to `rest_api.extensions`. Service accounts' lookups are logged as for the API's own
endpoints, so a service account that should read an extension needs its plugin's permission as well
as `rest_api.view_any_person`.

Each extension's response carries its own `version`. A breaking change to an extension arrives under
a new name (`storage-v2`), and the old one is listed as deprecated at `/api/v2/extensions/` until it
goes.

### Your own token

Anyone allowed to use the API (above) can make a token for themselves at `/api/token/`. The full token is
shown once, right after it's made; after that the page shows only its last six characters, with
buttons to regenerate or revoke it. Making, replacing and revoking a token are logged at INFO to
the `rest_api.tokens` logger. To link to it from the user profile page, the site's
`user/user_profile.html` includes the plugin's row inside its `profile_contents` block:

```django
{% include "rest_api/profile_token_row.html" %}
```

The row appears only on your own profile, and only if you're allowed to use the API.

### Service accounts

A system calling the API gets an ordinary user, with no staff flag and an unusable password, that
is in the `rest_api_users` group, holds `rest_api.view_any_person` ("Can look up any person
through the REST API" in the admin), and has a token an admin issues:

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

The system checks stop `migrate` and `check` when a DRF app is missing (`rest_api.E001`), when
ColdFront's own API is installed (`rest_api.E002`), and when a plugin registers an extension that one
of the API's own routes would hide, such as a person extension named `projects` (`rest_api.E003`).

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
