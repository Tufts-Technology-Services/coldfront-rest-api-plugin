# Plan: Tufts REST API

Status: agreed, 2026-11-02; revised 2026-11-16 to replace ColdFront's API with a plugin of our
own, and to split storage into one request per area or allocation. Phase 1 is built; see
[Phases](#phases). The open questions are answered; see [Decisions](#decisions).

## Goal

A read-only REST API that other Tufts systems can call for:

1. **A person's projects:** every project someone belongs to, with its project attributes.
2. **Allocations:** filterable by the resource type and resource name of the allocation, with
   their public allocation attributes.
3. **Storage:** the quota and live usage of a person's own storage, their home folder and
   scratch, which aren't ColdFront allocations; and live usage for a project's storage
   allocations. Each request asks one storage system.

## Why not ColdFront's API (v1)

ColdFront ships an API plugin, `coldfront.plugins.api`, which the Tufts hosts turned on
(`PLUGIN_API: true` in coldfront-ansible's `group_vars/tufts/main.yml`) until phase 0 turned it
off. It serves read-only endpoints under `/api/` (`projects`, `allocations`, `resources`,
`users`, `allocation-requests`, `allocation-change-requests`) and `POST /api/regenerate-token/`.
This plan calls it **v1**, and this plugin's API **v2** (see [Decisions](#decisions)).

It doesn't cover what we need:

| Need | v1 |
| --- | --- |
| Another person's projects | Only the caller's own. Staff see everyone's, with no way to filter by person. |
| Filter allocations by resource | No filters on `allocations` at all. |
| Public attributes only | `?project_attributes=true` and `?allocation_attributes=true` return **every** attribute, private ones included. `is_private` on the attribute type is ignored. |
| Home and scratch quotas | Nothing. |
| Pagination | None. Every list returns every row. |

**The private attribute leak is live in production until phase 0 is deployed.** Any user with a
token can read the private attributes of their own projects and allocations through v1,
including anything ColdFront's web pages show only to superusers.

**Decided 2026-11-16: turn `PLUGIN_API` off and write our own API as a new plugin.** Nobody at
Tufts uses v1. Turning it off closes the leak with a settings change and no
patch to the fork, and leaves one API with one set of visibility rules instead of two. This
replaces the 2026-11-02 decision to keep `PLUGIN_API` on and patch its serializers.

## What turning `PLUGIN_API` off changes

`PLUGIN_API` does more than serve v1 (`coldfront/config/plugins/api.py`). It adds
`django_filters`, `rest_framework`, `rest_framework.authtoken` and `coldfront.plugins.api` to
`INSTALLED_APPS` and sets `REST_FRAMEWORK`. With it off:

- **DRF and django-filter are still installed** as packages: both are core ColdFront
  dependencies. The new plugin declares them in its own `pyproject.toml` all the same.
- **Their apps go in through coldfront-ansible.** `django_filters`, `rest_framework` and
  `rest_framework.authtoken` are added to `INSTALLED_APPS` alongside the plugin, as entries in
  `tufts_plugin_apps` without URLs.
- **`REST_FRAMEWORK` moves to coldfront-ansible's Tufts settings,** with the values ColdFront
  set: token and session authentication, `IsAuthenticated` by default, `DjangoFilterBackend` as
  the default filter backend. Pagination is set per view (see [Decisions](#decisions)).
- **`rest_framework.authtoken` stays installed,** so its table and any tokens already issued
  survive.
- **v1's `POST /api/regenerate-token/` goes away,** and the token section v1 added to the user
  profile with it. The plugin has its own token page in their place; see
  [The token page](#the-token-page).
- **v1's staff-only endpoints** (`users`, `allocation-requests`,
  `allocation-change-requests`) go with it. Nobody uses them.

## Decisions

- **A new plugin, not part of `tufts_local`** (decided 2026-11-16). `tufts_local` is reports and
  alerts; the API has its own dependencies, settings, permission, URL version and outside
  callers. Repo `coldfront-rest-api-plugin`, package `rest_api`. It follows the
  plugin conventions: a simple `AppConfig`, hatchling, uv, tests in `rest_api/tests/`, the
  shared ruff setup, CI and pre-commit. It depends on `coldfront`, `djangorestframework` and
  `django-filter`, and, for [plugin extensions](#plugin-extensions), on `coldfront_utils` (from
  git). Not on `coldfront-storage-plugin` or any other plugin (decided 2026-11-16): plugins don't
  import each other, so a plugin serves its content through the API by registering an extension.
- **Credit ColdFront's API for what we reuse** (decided 2026-11-16). Where code is copied or
  adapted from `coldfront.plugins.api` (its serializers, viewsets, the `REST_FRAMEWORK`
  settings), the file says so in a comment at the top, naming the source file and "(C) ColdFront
  Authors", and the README's Credits section lists it. ColdFront is AGPL-3.0-or-later, so the
  plugin is too, unlike the other Tufts plugins (GPL-3.0-or-later), and lists ColdFront Authors
  among its authors.
- **System checks guard the settings.** The plugin refuses to start if `rest_framework` or
  `rest_framework.authtoken` isn't installed, or if `coldfront.plugins.api` is (`PLUGIN_API`
  back on would bring the leak back and clash with the mount point).
- **Mount at `/api/v2/`** (`{app: rest_api, urls: api/}` in coldfront-ansible), now that v1
  is off. ColdFront's built-in API counts as v1 (decided 2026-11-16), so the version says this
  is a different API from v1, not a first release of it. v1 was never versioned in its paths:
  it was served at `/api/` itself. The version in the path also lets a response shape change later
  without breaking callers.
- **`latest` and no version follow the newest version** (decided 2026-11-16). Every endpoint is
  also served at `/api/latest/...` and at `/api/...` with no version, both answering as v2 for
  now. When a v3 arrives, they move to v3 and `/api/v2/` stays. A system that mustn't break
  when that happens should call `/api/v2/`. The unversioned paths take over v1's old prefix,
  so an old v1 URL such as `/api/users/` is no longer v1's: it is a 404, or a v2 route where
  the paths happen to match. Nobody calls v1, and `rest_api.E002` stops the two being installed
  together. Each prefix is its own URL namespace
  (`rest_api:v2`, `rest_api:latest`, `rest_api:unversioned`), and a page's `next` and
  `previous` links stay on the prefix the caller used.
- **Read-only.** Every view is a `ReadOnlyModelViewSet` or a `GET`-only `APIView`.
- **People are named by username** (the UTLN), the same key Grouper, AD and the cluster use.
- **Superusers see private attributes; everyone else sees public ones only** (decided
  2026-11-02; superusers rather than staff decided 2026-11-16). This is the rule ColdFront's web
  pages use (`Allocation.get_attribute_set()` and the project detail view check
  `is_superuser`). Public means the attribute type has `is_private=False`. Staff who aren't
  superusers see public attributes only, as on the web pages. The response shape is the same
  for every caller: each attribute carries `"is_private"`, so superusers can tell the two apart
  and other callers just never see `true`.
- **ColdFront's rules decide who sees what** (decided 2026-11-16). The API never shows more than
  ColdFront's own pages would. Seeing everyone's projects takes superuser or ColdFront's
  `project.can_view_all_projects`; everyone's allocations, superuser or
  `allocation.can_view_all_allocations`. The staff flag alone isn't enough, as in ColdFront.
  (This replaces a decision earlier the same day that staff could look up anyone.) Seeing
  anyone's data and seeing private attributes stay separate: only superusers get the second.
- **A service account can ask about anyone, but only with a dedicated permission, and never
  sees private attributes** (decided 2026-11-02). See [Who can see what](#who-can-see-what).
- **New and Active projects, as in ColdFront** (decided 2026-11-16, replacing Active only from
  2026-11-02). ColdFront's project list, and its allocation list for an ordinary user, show
  projects that are New or Active, so the projects endpoint and an ordinary user's allocations
  do too. Membership is an Active `ProjectUser` row, or being the PI. Archived projects, which
  ColdFront shows on a page of their own, come with `?status=Archived`.
- **Resource filters match partially** (decided 2026-11-02): case-insensitive `icontains`.
- **Paginated.** Lists use DRF's `PageNumberPagination`, 100 per page by default and up to
  1000 with `?page_size=`. The allocation list in particular runs to thousands of rows.

## Who can see what

| Caller | Own data | Anyone's projects | Anyone's allocations | Private attributes |
| --- | --- | --- | --- | --- |
| Any authenticated user, staff included | yes | no: 404 for someone else's username, not 403, so the API doesn't confirm who exists | no | no |
| Superusers | yes | yes | yes | yes |
| Holders of ColdFront's `project.can_view_all_projects` | yes | yes | no | no |
| Holders of ColdFront's `allocation.can_view_all_allocations` | yes | no | yes | no |
| A service account with `rest_api.view_any_person` | yes | yes | yes | no |

**This table covers the API's own endpoints only.** What a plugin serves through an extension
(storage, say) is the plugin's to decide, with permissions of its own (decided 2026-11-17; see
[Plugin extensions](#plugin-extensions)). It replaces the 2026-11-16 rule, which had the API say
who could see storage.

"Own data" follows ColdFront's rules too: on the allocations endpoint, an ordinary user sees the
allocations ColdFront's allocation list would show them (see
[`/allocations/`](#get-apiv2allocations)).

**The service account permission is the API's own,** not ColdFront's
`project.can_view_all_projects` / `allocation.can_view_all_allocations`. ColdFront's web
pages check those two as well, so granting them would also let the account browse every
project and allocation in the UI. `view_any_person` means nothing outside this API.

- **Defining it adds no table.** The permission is declared on `rest_api.models.ApiAccess`, an
  unmanaged model (`managed = False`) that exists only to carry it, so Django creates the
  permission and its content type and no table. (Changed 2026-11-16 from a data migration on a
  content type with no model: `manage.py remove_stale_contenttypes` would delete such a content
  type, and with it the permission and every grant of it.)
- **A service account is an ordinary Django user** with that permission, an unusable password
  (so it can't log in to the web UI, only use its token) and `is_staff` off.
- **Its token is issued by an admin,** with DRF's `manage.py drf_create_token <username>` or in
  the admin's Tokens page. The plugin's token page only serves the signed-in person, and a
  service account can't sign in.
- **Private attributes stay superuser-only.** `view_any_person` widens *whose* data an account
  can read, not *what*. If a service ever needs private attributes, that is a second permission,
  not a staff or superuser flag on the account.
- **Every request a service account makes is logged** with what it asked about, so there is a
  record of who looked up whom: at INFO, to the `rest_api.lookups` logger, as
  `<caller> looked up <username>: <path>`, `<caller> looked up allocations: <path and query>`
  (the query shows the filters, `?username=` included) and
  `<caller> looked up allocation <id>: <path>`. A service account here is a caller with
  `view_any_person` who isn't a superuser.

## The token page

Added 2026-11-16. v1 had a token section on the user profile page; the plugin replaces it with a
page of its own at `/api/token/`, outside the version prefixes since it is a web page, not part
of the API.

- **Anyone signed in can make a token for themselves** (decided 2026-11-16), as in v1. A
  person's token reads only what they can see signed in, so it is no wider than their session.
  Service account tokens still come from an admin.
- **The full token is shown once** (decided 2026-11-16), on the page right after it is created or
  regenerated; after that, only its last six characters and its date. A lost token is replaced by
  regenerating it. v1 put the full token in the profile page on every visit, so a superuser using
  View as could read it. The new token waits in the session, not in a flash message, which Django
  may keep in a cookie.
- **Regenerate and revoke** are POSTs with CSRF, each confirmed in the browser. Either one stops
  the old token working at once.
- **Logged** at INFO to `rest_api.tokens`: `<username> created an API token`, `... replaced their
  API token ending <last six>`, `... revoked their API token ending <last six>`.
- **The profile page links to it** (decided 2026-11-16): a row with the token's last six
  characters, or None, and a Manage button. The plugin provides the row,
  `rest_api/profile_token_row.html`. The Tufts branding replaces `user/user_profile.html`, so it
  includes the row in its `profile_contents` block; the row shows only on your own profile.

## Plugin extensions

Proposed 2026-11-16, settled 2026-11-17; not built. How a plugin serves its own content through
the API without the API knowing anything about it, and without either importing the other.

**Why.** Plugins don't import each other, and the API is a plugin. Anything it serves about a
plugin's data would otherwise mean depending on that plugin, or reading its settings and tables,
which is the same dependency hidden. Even a storage-shaped interface in the API ties it to how
storage plugins work. So the API offers generic places to attach content, and each plugin
fills them with its own.

**The pattern** is `coldfront_utils.allocation_request`'s: `coldfront_utils` holds base classes
and a registry; a plugin subclasses and registers in its `AppConfig.ready()`; the API reads the
registry. Both import `coldfront_utils`, neither imports the other: the storage plugin doesn't
depend on this one, nor this one on it. They meet only at runtime, through the registry, when
both are installed. Without the API, a plugin's registration does nothing; without the plugin,
its routes are 404s.

**The registry is in `coldfront_utils`, not in this repo** (decided 2026-11-17). Here, plugins
would depend on the API, optionally (an `api` extra, registering only when `rest_api` is
installed), which is a plugin importing a plugin, and each would need testing with and without
it. In `coldfront_utils`, which every plugin already depends on, none of that arises. The API
itself stays a plugin of its own rather than moving into `coldfront_utils`: each API change would
otherwise be a `coldfront_utils` release, moving the library every plugin shares, and
`view_any_person` belongs to the `rest_api` app label, so moving the app would lose its grants.

**What `coldfront_utils` provides** (a new module, `coldfront_utils.api_extensions`, decided
2026-11-17), with nothing about any one plugin's content in it:

- **Three base classes,** one for each thing the API serves: `PersonExtension`,
  `ProjectExtension` and `AllocationExtension`. A subclass sets `name` (its URL segment:
  lowercase letters, digits and hyphens), a one-line `description` and a `version` (see
  [Versioning](#versioning)), and implements `allows(target, caller)`,
  `summary(target, caller)`, and `item(target, key, caller)` if it has items. `target` is the
  person (a `User`), project or allocation; `caller` is who's asking. `summary` and `item` return
  data that can be rendered as JSON.
- **`allows(target, caller)` decides who sees the extension's content** (decided 2026-11-17). It
  has no default: an extension that doesn't implement it is closed to everyone. The plugin
  defines whatever permissions it needs as ordinary Django permissions on one of its own models
  (`storage.view_any_storage`, say), so the API never needs to know them.
- **Helpers for ColdFront's own rules,** so an extension can follow them without the API:
  `can_view_project(caller, project)` and `can_view_allocation(caller, allocation)`, the rules
  ColdFront's project and allocation pages use. An allocation extension that anyone who can see
  the allocation may see is `return can_view_allocation(caller, target)`.
- **Two exceptions** an extension raises instead of knowing about HTTP: `ExtensionNotFound`
  (404: no such item, or not for this caller) and `ExtensionUnavailable` (503, with a message
  safe to show callers; the details go in the plugin's own log).
- **`register_api_extension(cls)`,** which refuses a malformed name, a class that isn't exactly
  one of the three kinds, and a second class of the same kind with the same name, raising
  `ImproperlyConfigured` at startup, as `register_request_section` does. Registering the same
  class twice is allowed, since `ready()` can run more than once. Written in
  `register_request_section`'s style; the two registries share only a few lines, so they stay
  separate.
- **Lookups for the API:** `find_extension(kind, name)` and `registered_extensions()`. The
  registry holds classes, keyed by kind and name, and the API makes an instance per request.
- **Base classes, not protocols** (decided 2026-11-16). All three kinds have the same shape, so a
  protocol couldn't tell them apart and the registry couldn't check which kind it was given;
  base classes carry the shared defaults (`item()` answering "not found") and the contract's
  docstrings; nothing here checks protocols statically (the repos run ruff only); and
  `allocation_request`'s `RequestSection` is a base class too.
- **Size:** about 100 to 150 lines and their tests. The work is in the API plugin and in each
  plugin's extension.

**What the API does,** knowing only the registry:

- **Generic routes,** under every version prefix (`v2/`, `latest/`, none):
  `users/<username>/<name>/` and `users/<username>/<name>/<key>/`, and the same under
  `projects/<id>/` and `allocations/<id>/`. They're looked up in the registry when a request
  arrives, so a name nothing registered is a 404. A name that clashes with the API's own routes
  (`projects` under `users/`) is a system check error.
- **One target check, then the extension's** (decided 2026-11-17). The API looks up the person,
  project or allocation, and answers 404 if there's none. Then it asks the extension's
  `allows(target, caller)`; `False` is the same 404, so a caller can't tell a username that
  doesn't exist from one it may not ask about. Who may see the extension's content is decided
  only there: the API adds no rule of its own, and passes the extension no notion of a service
  account. A service account that should read a plugin's content is granted that plugin's
  permission, alongside `view_any_person` for the API's own endpoints.
- **Logging** of service accounts' lookups, as for the API's own endpoints.
- **Errors:** `ExtensionNotFound` is a 404, `ExtensionUnavailable` a 503 with its message, and
  anything else a 500, logged.
- **Discovery:** `GET /api/v2/extensions/` lists what's registered, by kind, with each name,
  description, version and whether it's deprecated, so a caller can see what a deployment serves.

### Versioning

Decided 2026-11-17. The API's version (`v2`) covers what the API owns: routing, authentication,
the error format and paging. Each extension's data shape is its plugin's, with a version of its
own:

- **`version`** is a class attribute (an integer, starting at 1), listed by the discovery
  endpoint, and the extension includes it in what it returns, so a caller can see what it got:
  `{"extension": "storage", "version": 1, ...}`.
- **Adding a field isn't a breaking change,** and keeps the version.
- **A breaking change is a new name.** The plugin registers a second extension,
  `storage-v2` with `version = 2`, served at `/api/v2/users/smith01/storage-v2/`, and keeps the
  old one, marked `deprecated = True` (shown by discovery), until its callers have moved. Then it
  stops registering the old one, which becomes a 404.
- **Every API prefix serves every extension:** a later `/api/v3/` serves `storage-v2` unchanged.
- **`latest` doesn't follow extension names.** It means the newest API version only;
  `/api/latest/users/smith01/storage/` is the `storage` extension, whatever newer names exist.

Not chosen: an extension declaring the API versions it's served under (a plugin's change would
wait for an API release, and an API release for every plugin); `?version=` (each extension
answering in several shapes); a version segment in the path (`storage/v2/` clashes with item
keys).

**What it means for storage:** the storage plugin registers a `PersonExtension` named `storage`
(the area list as its summary, each area as an item) and, for phase 4, an `AllocationExtension`
named `usage`. Their code lives in the storage plugin, beside its request section:
`storage/api_extension.py`, with the lookup in `storage/user_storage.py`. The VAST lookup,
`USER_STORAGE_AREAS` (and its system check), `STORAGE_LOG_ONLY` and the storage permission all
stay in the storage plugin, which already has the VAST client setup, `StorageHandler` and the
attribute names. The API serves `users/<username>/storage/` without containing the word. The
lookup built on the `storage-areas` branch (the API plugin's `user_storage.py`, with its tests)
moves there largely as it is; that branch's views and its vast-api-client dependency are dropped.

- **`storage`'s `allows()`:** the person themselves, superusers, and holders of the storage
  plugin's own `storage.view_any_storage` (for service accounts). ColdFront has no permission
  covering home folders, so none of its permissions open it.
- **`usage`'s `allows()`:** `can_view_allocation(caller, target)`, and a 404 (`ExtensionNotFound`)
  for an allocation that isn't storage.

**Not in the first version:** an extension adding fields to the API's own responses (billing's
cost on each allocation in the list, say). Useful, but a different kind of extension, with
questions of its own (query counts, which callers see the field). Nor paginated summaries
(decided 2026-11-17): the storage summary has a few areas; an extension that needs paging can be
given it then.

**Effort:** about two to three days across three repos, in this order: coldfront-utils (base
classes, exceptions, registry, the ColdFront rule helpers, tests: half a day to a day), the API
plugin (generic routes, the target check and `allows()`, errors, discovery, tests with fake
extensions: about a day), the storage plugin
(its `storage` extension, mostly the lookup already written: half a day to a day). They deploy
together through the fork's lock.

## Endpoints

### `GET /api/v2/users/<username>/projects/`

The projects `<username>` is an **Active** member of, plus any they are PI of, in title order.

- **Without `?status=`:** New and Active projects, as ColdFront's project list shows them.
- **With `?status=`:** exactly the statuses named, by name, Archived included, as ColdFront's
  archived projects page shows them. Repeatable: `?status=Active&status=Archived`. A name that
  isn't a project status is a 400 naming the valid ones, not an empty list. The filter only
  narrows: it never lists a project the person isn't a member or PI of.
- Added 2026-11-16, with Archived projects.

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 412,
      "title": "Ocean Modelling",
      "status": "Active",
      "pi": "pi01",
      "membership": {"role": "Manager", "status": "Active"},
      "project_attributes": [
        {"name": "Project Key", "value": "OCEAN-01", "is_private": false},
        {"name": "Group", "value": "ocean_lab", "is_private": false}
      ]
    }
  ]
}
```

`membership` is that person's own `ProjectUser` row, so a caller can tell a PI or an Approver
(an active Manager who isn't the PI, as defined in tufts-coldfront-plugins'
[alert audiences plan][alert-audiences]) from a plain member without a second request. It is `null` for a PI with no Active
`ProjectUser` row of their own.

[alert-audiences]: https://github.com/Tufts-Technology-Services/tufts-coldfront-plugins/blob/main/docs/alert-audiences-plan.md#whos-who

### `GET /api/v2/allocations/`

The allocations ColdFront's allocation list would show the caller (decided 2026-11-16: the API
uses ColdFront's rules):

- **Callers who can see all allocations** (superusers, holders of
  `allocation.can_view_all_allocations`, and service accounts with `view_any_person`) see every
  allocation, as ColdFront's "show all allocations" does, whatever its project's status.
- **Everyone else** sees allocations on New or Active projects where they have an Active
  `ProjectUser` row and either that row's role is Manager (so a project's PI and Approvers see
  all its allocations) or they are an Active or PendingEULA `AllocationUser` of the allocation.
- **Every allocation status** is listed unless `?status=` narrows it, as in ColdFront.

The list can be filtered by:

| Parameter | Matches | Example |
| --- | --- | --- |
| `resource_type` | `resources__resource_type__name`, case-insensitive partial | `?resource_type=storage` |
| `resource` | `resources__name`, case-insensitive partial | `?resource=tier 2` |
| `status` | `status__name` | `?status=Active` |
| `project` | `project_id` | `?project=412` |
| `username` | an Active `AllocationUser`, or the project's PI | `?username=smith01` |

Each filter can be repeated to match any of
several values (`?resource=A&resource=B`). For the partial filters, that is an OR of
`icontains` lookups, so they are method filters, not django-filter's `BaseInFilter`. Partial
matching means `?resource=Storage` matches every resource with "Storage" in its name; callers
wanting one resource should pass enough of its name. An allocation has many resources (an M2M),
so the filters match an allocation if **any** of its resources match, and the queryset is
`.distinct()`.

```json
{
  "id": 9031,
  "project": {"id": 412, "title": "Ocean Modelling", "pi": "pi01"},
  "status": "Active",
  "resources": [{"name": "Tier 2 Storage", "resource_type": "Storage"}],
  "start_date": "2026-01-15",
  "end_date": "2027-01-15",
  "allocation_attributes": [
    {"name": "Storage Quota (TB)", "value": "10", "usage": 6.2, "is_private": false}
  ]
}
```

`usage` comes from `AllocationAttributeUsage`, as in ColdFront's serializer, and is `null`
for attribute types without usage.

### `GET /api/v2/allocations/<id>/`

One allocation, in the same shape as in the list (added 2026-11-16). Who may see it is
ColdFront's allocation page's rule: superusers, holders of `allocation.can_view_all_allocations`
and service accounts with `view_any_person`, and anyone else for whom
`Allocation.has_perm(user, AllocationPermission.USER)` is true: an Active or New `ProjectUser`
row on its project, and either the PI or Manager role, or an Active, New or PendingEULA
`AllocationUser` row. Anyone else gets a 404, the same as for an allocation that doesn't exist.
`/allocations/<id>/usage/` uses the same rule.

### `GET /api/v2/users/<username>/storage/`

Served by the storage plugin's `storage` person extension (see
[Plugin extensions](#plugin-extensions)); this section and the next describe what it returns.

The storage areas that belong to a person rather than to a project: their home folder and
scratch. These aren't ColdFront allocations, so this is the only place the API reports them. The
list names each area and the URL to ask about it, and calls no storage system:

```json
{
  "extension": "storage",
  "version": 1,
  "username": "smith01",
  "areas": [
    {"name": "home", "url": "https://rcrm.it.tufts.edu/api/v2/users/smith01/storage/home/"},
    {"name": "scratch", "url": "https://rcrm.it.tufts.edu/api/v2/users/smith01/storage/scratch/"}
  ]
}
```

The areas come from the settings (below), in the order they are listed there. The list isn't
paginated, since there are only a few. Each `url` stays on the prefix the caller used (`v2`,
`latest` or none).

### `GET /api/v2/users/<username>/storage/<area>/`

That person's quota and live usage in one area. For home (`/homedir`, on the hpc VAST):

```json
{
  "extension": "storage",
  "version": 1,
  "username": "smith01",
  "area": "home",
  "path": "/homedir",
  "scope": "user",
  "quota_source": "override",
  "soft_limit_bytes": 100000000000,
  "hard_limit_bytes": 100000000000,
  "used_bytes": 85136281441,
  "used_inodes": 478373,
  "state": "OK",
  "retrieved_at": "2026-11-02T23:39:37Z"
}
```

Scratch (`/scratch`, added 2026-11-02) answers in the same shape; its VAST quota was checked on
2026-11-16 (see [Scratch](#scratch)).

**One area per request** (decided 2026-11-16). This replaces the 2026-11-02 plan of one
response holding every area and every storage allocation the person belongs to. Areas and
allocations can each live on a different storage system, and at Tufts many will. In one
response, the slowest system would set the response time, a failing system would mean a 200
with per-entry errors, and live and day-old numbers would sit side by side. With one area per
request:

- **Each request asks one storage system,** so its speed and its failures are that system's
  alone.
- **Status codes mean what they say.** An area whose storage system is unreachable or times out
  is a 503 for that request only. An area name not in the settings is a 404, as is a username
  ColdFront doesn't know.
- **Each area is cached on its own,** for as long as suits its storage system.
- **A new area is a settings change.** It appears in the list above, with no new route.

A dashboard showing home and scratch makes two requests, in parallel if it likes. Live usage
for project storage is a separate endpoint per allocation; see
[`/allocations/<id>/usage/`](#get-apiv2allocationsidusage).

**Settings:** `USER_STORAGE_AREAS` maps each area name to the `STORAGE_PLUGIN_CLIENTS` entry
it lives on and the path of its directory quota there:

```python
USER_STORAGE_AREAS = {
    "home": {"client": "hpc", "path": "/homedir"},
    "scratch": {"client": "hpc", "path": "/scratch"},
}
```

- **Unset, there are no storage areas** (changed 2026-11-16 from a system check error, since the
  plugin no longer needs the storage plugin): the area list is empty, and any area is a 404.
- **Set, it must be well formed:** a storage plugin system check error for each area that isn't a dict, has no
  client, has a path that isn't absolute, names a client that isn't in `STORAGE_PLUGIN_CLIENTS`,
  or has a name with a slash in it (the name is a URL segment).
- **Each area names its own client,** so areas needn't share a storage system.
- **Every area's client is taken to be a VAST.** Only VAST user quotas are looked up. The
  `"type"` key that would tell a VAST from a TrueNAS (see
  [Where an allocation lives](#where-an-allocation-lives)) comes with phase 4, which needs it.

### Home

Home folders live on the **hpc VAST** (`STORAGE_PLUGIN_CLIENTS` key `hpc`), at
`/cluster/home/<username>` on the cluster (hpc-cli creates them). On VAST they are one directory
quota, `homedir` (path `/homedir`), with user quotas inside it. There were two ways to report
per-person numbers:

| | A: user quotas inside the `/homedir` quota | B: a directory quota per home folder |
| --- | --- | --- |
| What VAST holds | The existing `/homedir` quota, plus a default user quota (and any per-person overrides) | One quota object per home folder |
| What counts as usage | Files under `/homedir` **owned by** the person | Files **inside** the person's folder |
| New users | Covered by the default user quota as soon as they exist | Each new home folder needs a quota created (hpc-cli, or a ColdFront task) |
| Existing users | Nothing to backfill | A quota created for every existing home folder |
| Lookup | By username within the `/homedir` quota | By path, like `get_quota()` today |
| Client work | A user quota call in vast-api-client, which has none today | None: `vc.get_quotas(path=...)` exists |

**Decided 2026-11-02: A.** The home folder quota already has user quotas, so A needs no change on
VAST. For a home folder that is `0700`, files under `/homedir` owned by a person and files
inside their folder are nearly the same set. A also needs no provisioning step and no backfill.

### What VAST returns

Two VAST calls were tried on the hpc cluster on 2026-11-02.

**`GET /quotas/{id}`** for the home folder quota (id 484, `system_id` 466, path `/homedir`):

- **`default_user_quota`:** the limits for anyone without an override, 30 GB soft and 30 GB
  hard. No usage figures.
- **`user_quotas`:** only the people **with an override**, nine at the time. Not enough on its
  own: most people are on the default.
- **`last_user_quotas_update`:** when VAST last recalculated user usage. This becomes the
  response's `retrieved_at`, since that's how fresh the number really is.
- **`num_exceeded_users`, `num_blocked_users`:** counts across all users (0 and 84 at the time).

**`GET /userquotas/`** lists every user and group quota entry on the cluster: 16,548 of them,
paginated (`count`, `next`, `previous`, `results`). Each entry has:

- **`quota_system_id`:** which directory quota it belongs to. For home folders that is **466**,
  the home quota's `system_id`, *not* its id 484. Each entry also has `path` (`/homedir`).
- **`soft_limit`, `hard_limit`:** the limits in force for that person, the 30 GB default
  included. Either can be `null` (`ymalon01`: 200 GB soft, no hard limit).
- **`used_capacity`, `used_inodes`, `state`:** the person's usage, for default and override
  quotas alike. `used_effective_capacity` is `null` on user quota entries (checked 2026-11-16), so
  `used_capacity` is the usage the area endpoint reports.
- **`entity`:** who the entry is for. `is_group` says user or group. `identifier_type` is
  `"username"` (`identifier` is then the UTLN) or `"uid"` (`identifier` is a UID and `name` is
  empty, presumably because VAST couldn't resolve it). Groups use `"groupname"` or `"gid"`.

What that means for the endpoint:

- **`/userquotas/` is the source.** A person's entry gives their limits and usage whether they
  are on the default or an override. `quota_source` is `"override"` if their limits differ from
  `default_user_quota`, `"default"` if not.
- **Match strictly:** `quota_system_id` equal to the area's quota `system_id`, `is_group` false,
  and then either `identifier_type == "username"` with `identifier` equal to the UTLN, or
  `identifier_type == "uid"` with the person's UID. Never a partial match: `root` and service
  accounts have entries too, and a user and a group can share a name (`sdough01` is both).
- **Some people are recorded by UID, so the endpoint needs their UID.** It uses
  `coldfront_utils.get_uid`, which runs `getent passwd` on the ColdFront host. p01 resolves
  cluster accounts (checked 2026-11-02 with `getent passwd cbarne02`). The UID is cached with
  the rest of the answer, so `getent` runs at most once per person per few minutes. Some UID
  entries belong to no current account (UID 1069 didn't resolve); nobody can ask the API about
  those, so they are never looked up. If a host can't resolve accounts, AD's `uidNumber` is the
  fallback: hpc-cli reads it from there when it creates home folders.
- **Someone with no entry at all** (never owned a file under `/homedir`, presumably) gets the
  default limits from `default_user_quota` with `used_bytes: 0` and `"quota_source": "default"`.
- **Limits can be null.** The response passes `null` through. It doesn't turn null into 0,
  which would read as "no space at all".
- **No percentages from VAST.** Its `percent_capacity` is null whenever `hard_limit` is, so the
  endpoint returns the raw numbers and leaves the arithmetic to callers.

**One person is one small call** (confirmed 2026-11-02, the filter's name corrected 2026-11-16).
`/userquotas/` filters server-side on entry fields: `?path=/homedir` cut 16,548 entries to 10,634,
and `?path=/homedir&entity__identifier=tphimm01` returned two, the `tphimm01` **user** (200 GB
override, 58 GB used) and the `tphimm01` **group**.

- **The filter is `entity__identifier`,** with two underscores (a Django lookup on the entry's
  `entity`). This plan first recorded it as `entity_identifier`, and vast-api-client was built
  that way. VAST ignores a filter it doesn't know and answers with every entry, so the mistake
  showed only on 2026-11-16, when a check against the hpc VMS got all 10,685 `/homedir` entries
  back. Of the names tried, only `entity__identifier` filters, under API versions `v7` and
  `latest` alike. Because a misspelt filter fails silently, the lookup's strict match below
  stays required, not a precaution.
- **Paging works as the client expects** (checked 2026-11-16): VAST honours `page_size`, and with
  `page_size=1` the client followed VAST's next link to get a user's two entries.
- **The UID fallback works** (checked 2026-11-16): `entity__identifier=1069` on `/homedir`
  returned the one entry VAST records by that UID (`identifier_type` `uid`, 30 GB default, 3.4 GB
  used). A username matches only entries recorded by username, and a UID only those recorded by
  UID, so the two lookups don't overlap.

Users and groups share names, so the `is_group: false` match above is required, not a
precaution. The lookup makes that call per person, then with the UID if the username finds no
user entry, and caches the answer for two minutes. No scheduled task or bulk copy is needed.

Then:

- **The lookup is the storage plugin's,** behind its `storage` extension (see
  [Plugin extensions](#plugin-extensions)). It calls vast-api-client's `get_quota` and
  `get_user_quotas` with the client the storage plugin's `get_vast_client()` builds for the
  area's `STORAGE_PLUGIN_CLIENTS` entry. (It was built first in the API plugin, on the
  `storage-areas` branch, before the extension design; it moves as it is.)
- **`STORAGE_LOG_ONLY` on** (its default, and set on cf-s01sim) means nothing is asked of VAST:
  the area endpoint answers 503, "Storage lookups are off on this host", and the log says what
  would have been looked up (decided 2026-11-16).
- **Each area's quota id** is found by path once and cached for an hour: it changes only if the
  quota is recreated. Its `system_id`, default limits and `last_user_quotas_update` are read with
  each lookup, so `retrieved_at` is current.
- **Caching:** each person's answer, per area, for two minutes, in Django's cache
  (`coldfront_utils`' `ttl_cache`), which the web workers share. VAST recalculates usage every
  minute or two, so nothing fresher is to be had.
- **Errors:** VAST unreachable or timing out is a 503 with a short message, never VAST's own
  error text, which includes the VMS hostname (the quota's `url` field does too, so it is never
  passed through). It fails only the area asked about. A username ColdFront doesn't know is a
  404, as on the other endpoints; VAST is only asked about known users.
- **The area's client and path come from `USER_STORAGE_AREAS`** (see the area endpoint), so
  the VAST instance asked is the one the area names, not a single user-quota client.
- **Each area's `path` is its directory quota** (`/homedir`, `/scratch`), the quota the user quota
  sits in, with `"scope": "user"`, so a caller doesn't read it as the size of one folder.
- **Everything above applies per area:** each area's `system_id` and default limits come from
  its own `GET /quotas/{id}`, and a request is one `/userquotas/?path=<area>&entity__identifier=`
  call (two if it falls back to the UID).

### Scratch

Added 2026-11-02; checked on the hpc VMS on 2026-11-16 with vast-api-client's `get_quota` and
`get_user_quotas`. It works as home does:

- **There is a directory quota at `/scratch`** on VAST: id 680, `system_id` 657.
- **It has user quotas** (`is_user_quota: true`), with a default of 100 GB soft and 100 GB hard.
- **`/userquotas/?path=/scratch&entity__identifier=<UTLN>` returns that person's user entry,**
  as for `/homedir` (`quota_system_id` 657). `cbarne02` had a user entry and no group entry
  there, where `/homedir` has both.

So scratch needs no code of its own: adding `"scratch": {"client": "hpc", "path": "/scratch"}` to
`USER_STORAGE_AREAS` is enough.


### `GET /api/v2/allocations/<id>/usage/`

Added 2026-11-02, as part of a combined storage response; its own endpoint since 2026-11-16. One
storage allocation's quota and usage, as close to live as its storage system allows. ColdFront's
stored quota and usage, the Starfish snapshot up to a day old, are already on the allocations
endpoint as attributes; this endpoint is for callers that need newer numbers.

- **Served by the storage plugin's `usage` allocation extension** (see
  [Plugin extensions](#plugin-extensions)), whose responses also carry `"extension"` and
  `"version"`.
- **Who can ask:** anyone who can see the allocation, by ColdFront's rule
  (`can_view_allocation` from `coldfront_utils`, the extension's `allows()`). For anyone else it
  is a 404.
- **Storage only:** an allocation whose resource has no `StorageHandler` is a 404.
- **Finding a person's storage allocations** is the allocations endpoint's job:
  `/api/v2/allocations/?username=smith01&resource_type=storage`, then one usage request per
  allocation. Allocation membership is ColdFront's own (`AllocationUser`), not project
  membership: someone can be on a project without being on each of its allocations.

#### Where an allocation lives

The storage plugin already records it:

- The allocation's resource has a `StorageHandler` (one per `Resource`) whose `quota_client_id`
  names an entry in `STORAGE_PLUGIN_CLIENTS`: `hpc` or `rstore` (two VAST instances) or
  `truenas`. Each allocation is asked of its own instance.
- That client config's `native_path_attribute_name` names the allocation attribute holding the
  path on the storage system (`vast_path` for both VAST instances).
- **Which kind of system a client is** isn't recorded in its config today, only implied by the
  handler's task names (`storage.vast...` vs `storage.truenas...`). The storage plugin should get
  an explicit `"type": "vast"` / `"truenas"` in each `STORAGE_PLUGIN_CLIENTS` entry
  (coldfront-ansible's Tufts settings) rather than parse task names. The storage areas use it
  too.

#### VAST allocations: live

One `GET /quotas/?path=<vast_path>` to that allocation's VAST instance:

```json
{
  "allocation": 9031,
  "project": {"id": 412, "title": "Ocean Modelling"},
  "resource": "Tier 3 Storage",
  "source": "vast",
  "soft_limit_bytes": 10000000000000,
  "hard_limit_bytes": 10000000000000,
  "used_bytes": 6200000000000,
  "state": "OK",
  "retrieved_at": "2026-11-03T14:05:12Z",
  "stored_used_bytes": 6150000000000,
  "usage_reported_at": "2026-11-03T03:00:00Z"
}
```

- **Limits:** `soft_limit` and `hard_limit`, both reported (either can be null). The storage
  plugin's batch task records `soft_limit`, falling back to `hard_limit`, as the allocation's
  quota; callers wanting the one ColdFront shows should do the same.
- **Usage comes from VAST, not Starfish.** ColdFront's stored usage (`reported_usage_bytes`) is
  written by the Starfish task from a once-a-day snapshot, too stale for this. The directory
  quota itself reports usage: `used_capacity` or `used_effective_capacity` (see "Still to check"
  below). Every allocation the storage plugin provisions on VAST gets a directory quota at its
  path (`add_quota_and_protected_path`), so the quota lookup finds usage too.
- **`retrieved_at`** is the time of the VAST call. Unlike user quotas, a directory quota carries no
  "last updated" time; VAST keeps directory quota usage current itself.
- **Cached for a minute or two per path,** so a dashboard refreshing doesn't hit VAST every time,
  while still being close to live. Paths are cached per client, so the same path on two
  instances never collides.
- **Errors:** the VAST instance unreachable or timing out is a 503, with a short message and never
  VAST's own error text. A path VAST has no quota for is a 404 with the detail "No quota for this
  allocation.", so a caller can tell it from an allocation it can't see.

#### TrueNAS allocations: stored

TrueNAS has no live source, so the response is ColdFront's stored values, read from the
allocation's attributes with no call out: `reported_quota_bytes` and `quota_report_date` (written
by the TrueNAS quota batch task), and `reported_usage_bytes` and `usage_report_date` (written by
the Starfish usage task, a once-a-day snapshot, which Tufts considers adequate for TrueNAS).

```json
{
  "allocation": 8120,
  "project": {"id": 412, "title": "Ocean Modelling"},
  "resource": "Tier 2 Storage",
  "source": "stored",
  "soft_limit_bytes": null,
  "hard_limit_bytes": 2000000000000,
  "used_bytes": 1100000000000,
  "state": null,
  "quota_reported_at": "2026-11-03T02:00:00Z",
  "usage_reported_at": "2026-11-03T03:00:00Z"
}
```

Answering with the stored values, rather than a 404, means a caller can use the one URL for every
storage allocation; `"source": "stored"` and the report dates tell it how old the numbers are.

#### For both

**No paths in the response.** The allocation is identified by its id, project and resource
name. `vast_path` and `Storage Path` are allocation attributes that may be private, and the
storage system path is never returned to callers who couldn't see it on the allocations endpoint.

**Still to check:** which VAST usage field to report. On `/homedir` `used_capacity` and
`used_effective_capacity` were equal. On a project quota where they differ, the field to report
is the one measured the same way people are billed and told their quota: if quotas are enforced
on logical size, the logical figure. `GET /quotas/?path=<vast_path>` for one real project
allocation on each instance (`hpc` and `rstore`) would show both, and comparing them with that
allocation's Starfish number (logical size, though a day old) shows which is which. Also worth
confirming: that allocations created before the storage plugin managed VAST also have a
directory quota at their `vast_path`.

**ColdFront keeps showing Starfish's usage** (decided 2026-11-02). The live VAST figure is used
only in this API's responses and is never written to ColdFront: `reported_usage_bytes` stays
Starfish's, and the VAST quota batch task keeps storing only quotas. So for a VAST allocation the
API's `used_bytes` and the usage on ColdFront's allocation page can differ, the API being newer.
Each VAST response therefore also carries the stored Starfish figure, `stored_used_bytes` with
`usage_reported_at`, so a caller can show the number ColdFront shows, or both.

## Layout

```
coldfront-rest-api-plugin/
    pyproject.toml
    rest_api/
        __init__.py
        apps.py          # AppConfig; registers the system checks
        checks.py        # DRF and authtoken installed, coldfront.plugins.api not
        models.py        # ApiAccess: unmanaged, no table; carries view_any_person
        migrations/      # creates ApiAccess's permission, not a table
        permissions.py   # who sees everyone's projects or allocations, ColdFront's rules
        serializers.py   # attribute serializers: private ones for superusers only
        filters.py       # AllocationFilter (django-filter FilterSet)
        views.py
        extension_views.py # generic routes for plugin extensions (see Plugin extensions)
        token_views.py   # the token page: create, regenerate, revoke your own token
        templates/rest_api/  # the token page, and the row the profile page includes
        urls.py          # mounted at api/ by coldfront-ansible; routes under v2/, and token/
        tests/
            settings.py  # coldfront's settings, plus DRF, authtoken and rest_api
```

The test settings add `rest_framework`, `rest_framework.authtoken`, `django_filters` and
`rest_api` to `INSTALLED_APPS` and set `REST_FRAMEWORK`, since `PLUGIN_API` isn't there to do
it, along with the usual in-memory SQLite and MD5 hasher.

## Phases

0. **Turn `PLUGIN_API` off** in coldfront-ansible's `group_vars/tufts/main.yml`. This closes the
   private attribute leak and needs nothing else, so it can deploy now, ahead of the plugin.
   The `authtoken_token` table stays in the database; nothing reads it until the plugin's
   settings put `rest_framework.authtoken` back.
1. **The plugin and the projects endpoint:** the new repo with its CI and pre-commit, the system
   checks (`rest_api.E001`: a DRF app missing; `rest_api.E002`: ColdFront's API, v1, installed), the
   permission, pagination, and the projects endpoint. Built 2026-11-16 on the
   `projects-endpoint` branch. This sets the patterns the other two follow. Deploy order:
   1. the plugin merged and pushed;
   2. the fork's `tufts` extra names it, and `uv.lock` is updated, committed and pushed;
   3. coldfront-ansible adds `django_filters`, `rest_framework`, `rest_framework.authtoken` and
      `{app: rest_api, urls: api/}` to `tufts_plugin_apps`, and `REST_FRAMEWORK` to the Tufts
      settings, in the same deploy. Adding the apps before the package is installed would stop
      ColdFront starting; the plugin's system checks stop it starting without the settings.
2. **Allocations endpoints:** the filtered list and the single allocation, with ColdFront's rules
   for who sees which. Built 2026-11-16 on the `allocations-endpoint` branch, with the move to
   ColdFront's permissions and project statuses and the projects endpoint's `?status=`.
3. **Plugin extensions, then storage areas:** the vast-api-client user quota calls (built and
   tried against the hpc VMS on 2026-11-16, by username, by UID and across pages; merged). Then
   [plugin extensions](#plugin-extensions) in coldfront-utils and the API plugin, and the
   storage plugin's `storage` extension, which takes over the lookup first built in the API
   plugin on the `storage-areas` branch. Home and scratch are both ready
   ([Scratch](#scratch)). To deploy: coldfront-utils, the storage plugin and the API plugin
   together through the fork's lock, then `USER_STORAGE_AREAS` in coldfront-ansible's Tufts
   settings, with `STORAGE_LOG_ONLY` off on the hosts that should ask VAST.
4. **Live allocation usage:** the storage plugin's directory quota lookup, then
   `/allocations/<id>/usage/`. Needs the allocations endpoint (phase 2) and the VAST usage
   field settled (see "Still to check" under
   [`/allocations/<id>/usage/`](#get-apiv2allocationsidusage)).
5. **Later:** an OpenAPI schema (drf-spectacular isn't installed today).

## Testing

- DRF's `APIClient` with `force_authenticate`, in `rest_api/tests/test_*.py`.
- A permission matrix per endpoint: the person themselves, another user (404), staff without a
  permission (404), superusers, holders of the matching ColdFront `can_view_all_*` permission
  (and of the other one, who get a 404), and a service account with and without
  `view_any_person`.
- Private attributes appear for superusers and for nobody else: not staff who aren't
  superusers, not the person themselves, not a service account.
- A service account's lookups are logged with the username asked about.
- Each allocation filter, including an allocation with two resources matching once, not twice,
  and a repeated partial filter matching either value.
- New and Active projects appear and Archived ones don't unless `?status=` asks for them
  (each status alone and together, an unknown one a 400, the filter kept in `next`), and
  projects never appear where the person's `ProjectUser` row is Removed, whatever the filter.
- An ordinary user's allocations follow ColdFront's list rule: on New or Active projects, through
  a Manager row or an Active or PendingEULA allocation membership. Callers who see all
  allocations see every project status. The single allocation follows `Allocation.has_perm`.
- The system checks: an error when `rest_framework` or `rest_framework.authtoken` isn't
  installed, and when `coldfront.plugins.api` is.
- Plugin extensions with fake extensions registered for the test: each kind's routes under
  every prefix, a missing person, project or allocation a 404, `allows()` returning `False` the
  same 404 (and the extension's `summary` not called), `ExtensionNotFound` and
  `ExtensionUnavailable` becoming 404 and 503, an unknown name a 404, a name clashing with the
  API's routes a system check error, logging, and the discovery list with versions and
  `deprecated`. The registry's own tests, and those of `can_view_project` and
  `can_view_allocation`, live in coldfront-utils. The storage extensions' tests (their
  `allows()`, the VAST lookup with a fake VAST client that filters as VAST does) live in the
  storage plugin.
- Allocation usage: a VAST allocation on each of two instances asked of its own instance, a
  TrueNAS allocation read from stored attributes with no call out, a non-storage allocation and
  one the caller can't see (both 404), no VAST quota at the path (404 with its own detail), the
  instance down (503), and no path in any response.
- A query-count test on each list (`django_assert_max_num_queries`), so a missing
  `prefetch_related` shows up as a failure, not as a slow page in production.

## Open questions

Open as of 2026-11-17:

- **Per-folder usage inside a home** (top-level folders with their sizes): VAST can't give it
  accurately and close to live (vast-api-client's `docs/vast-usage-findings.md`). The choice is
  between a background `du` service on the cluster (live), Starfish (daily, if it scans
  `/homedir`) and leaving it out (the live total and the folder names from `list_dir`).
- **Whether `used_capacity` counts apparent or allocated bytes** (`du -sb` or `du -sB1`): they
  differed by 1.5% on one home; compare in exact bytes.
- **Phase 4's VAST usage field** (`used_capacity` or `used_effective_capacity` on a directory
  quota), under [`/allocations/<id>/usage/`](#get-apiv2allocationsidusage), "Still to check".

Answered 2026-11-02 (the first three here on 2026-11-16, the extension ones 2026-11-17) and
written into [Decisions](#decisions), [Plugin extensions](#plugin-extensions) and the endpoint
sections:

- Plugin extensions: the registry is in `coldfront_utils.api_extensions`; each extension decides
  who sees its content with `allows()`, and plugins define their own permissions; each extension
  has its own `version`, a breaking change being a new name; summaries aren't paginated.
- Someone else's storage: the storage extension's rule, the person themselves, superusers and
  holders of `storage.view_any_storage`.

- `PLUGIN_API` goes off and the API is a new plugin, `rest_api`, mounted at
  `/api/v2/` (also `/api/latest/` and `/api/`), with ColdFront's API counting as v1. Nobody
  at Tufts uses v1.
- Superusers see private attributes; nobody else does, staff who aren't superusers and service
  accounts included. This matches ColdFront's web pages.
- Who sees everyone follows ColdFront: superusers and holders of ColdFront's
  `can_view_all_projects` or `can_view_all_allocations` for that kind of data, plus service
  accounts with `view_any_person`. Staff alone don't.
- A service account may ask about anyone, only with `rest_api.view_any_person`.
- New and Active projects, as in ColdFront; membership is an Active `ProjectUser` row or being
  the PI.
- Resource filters match partially (`icontains`).
- Home folders: option A, the person's user quota inside `/homedir`, looked up per person with
  `/userquotas/?path=/homedir&entity__identifier=`, UIDs resolved with `getent`.
- Scratch (`/scratch`) is reported the same way, as its own area. Its VAST quota was checked on
  2026-11-16; see [Scratch](#scratch).
- Storage is one request per area (`users/<username>/storage/<area>/`) and per allocation
  (`allocations/<id>/usage/`), not one response for everything (2026-11-16): each request asks
  one storage system. Allocations are live from VAST, stored values for TrueNAS.
