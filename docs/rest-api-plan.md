# Plan: Tufts REST API

Status: agreed, 2026-11-02; revised 2026-11-16 to replace ColdFront's API with a plugin of our
own. Nothing built yet. The open questions are answered; see [Decisions](#decisions).

## Goal

A read-only REST API that other Tufts systems can call for:

1. **A person's projects:** every project someone belongs to, with its project attributes.
2. **Allocations:** filterable by the resource type and resource name of the allocation, with
   their public allocation attributes.
3. **Storage quotas:** the quota and usage of a person's home folder and scratch space, read live
   from VAST.

## Why not ColdFront's API

ColdFront ships an API plugin, `coldfront.plugins.api`, and the Tufts hosts turn it on today
(`PLUGIN_API: true` in coldfront-ansible's `group_vars/tufts/main.yml`). It serves read-only
endpoints under `/api/` (`projects`, `allocations`, `resources`, `users`, `allocation-requests`,
`allocation-change-requests`) and `POST /api/regenerate-token/`.

It doesn't cover what we need:

| Need | ColdFront's `/api/` |
| --- | --- |
| Another person's projects | Only the caller's own. Staff see everyone's, with no way to filter by person. |
| Filter allocations by resource | No filters on `allocations` at all. |
| Public attributes only | `?project_attributes=true` and `?allocation_attributes=true` return **every** attribute, private ones included. `is_private` on the attribute type is ignored. |
| Home and scratch quotas | Nothing. |
| Pagination | None. Every list returns every row. |

**The private attribute leak is live in production today.** Any user with a token can read the
private attributes of their own projects and allocations through `/api/`, including anything
ColdFront's web pages show only to superusers.

**Decided 2026-11-16: turn `PLUGIN_API` off and write our own API as a new plugin.** Nobody at
Tufts uses ColdFront's `/api/`. Turning it off closes the leak with a settings change and no
patch to the fork, and leaves one API with one set of visibility rules instead of two. This
replaces the 2026-11-02 decision to keep `PLUGIN_API` on and patch its serializers.

## What turning `PLUGIN_API` off changes

`PLUGIN_API` does more than serve `/api/` (`coldfront/config/plugins/api.py`). It adds
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
- **`POST /api/regenerate-token/` goes away.** Service accounts get their tokens from an admin
  anyway. If ordinary users ever need their own tokens, the plugin adds a small endpoint.
- **ColdFront's staff-only endpoints** (`users`, `allocation-requests`,
  `allocation-change-requests`) go with it. Nobody uses them.

## Decisions

- **A new plugin, not part of `tufts_local`** (decided 2026-11-16). `tufts_local` is reports and
  alerts; the API has its own dependencies, settings, permission, URL version and outside
  callers. Repo `coldfront-rest-api-plugin`, package `rest_api`. It follows the
  plugin conventions: a simple `AppConfig`, hatchling, uv, tests in `rest_api/tests/`, the
  shared ruff setup, CI and pre-commit. It depends on `coldfront`, `djangorestframework` and
  `django-filter`; `coldfront_utils` and `coldfront-storage-plugin` (both from git) come in with
  the storage quota endpoint, which is the first thing to need them.
- **Credit ColdFront's API for what we reuse** (decided 2026-11-16). Where code is copied or
  adapted from `coldfront.plugins.api` (its serializers, viewsets, the `REST_FRAMEWORK`
  settings), the file says so in a comment at the top, naming the source file and "(C) ColdFront
  Authors", and the README's Credits section lists it. ColdFront is AGPL-3.0-or-later, so the
  plugin is too, unlike the other Tufts plugins (GPL-3.0-or-later), and lists ColdFront Authors
  among its authors.
- **System checks guard the settings.** The plugin refuses to start if `rest_framework` or
  `rest_framework.authtoken` isn't installed, or if `coldfront.plugins.api` is (`PLUGIN_API`
  back on would bring the leak back and clash with the mount point).
- **Mount at `/api/v1/`** (`{app: rest_api, urls: api/}` in coldfront-ansible), now that
  ColdFront's `/api/` is off. The version in the path lets a response shape change later
  without breaking callers.
- **Read-only.** Every view is a `ReadOnlyModelViewSet` or a `GET`-only `APIView`.
- **People are named by username** (the UTLN), the same key Grouper, AD and the cluster use.
- **Superusers see private attributes; everyone else sees public ones only** (decided
  2026-11-02; superusers rather than staff decided 2026-11-16). This is the rule ColdFront's web
  pages use (`Allocation.get_attribute_set()` and the project detail view check
  `is_superuser`). Public means the attribute type has `is_private=False`. Staff who aren't
  superusers see public attributes only, as on the web pages. The response shape is the same
  for every caller: each attribute carries `"is_private"`, so superusers can tell the two apart
  and other callers just never see `true`.
- **Staff can look up anyone** (decided 2026-11-16), as they could in ColdFront's `/api/`.
  Seeing anyone's data and seeing private attributes are separate: staff get the first, only
  superusers get the second.
- **A service account can ask about anyone, but only with a dedicated permission, and never
  sees private attributes** (decided 2026-11-02). See [Who can see what](#who-can-see-what).
- **Only Active projects** (decided 2026-11-02). The projects endpoint lists Active projects
  only, and the allocations endpoint lists only allocations on Active projects. Membership is
  an Active `ProjectUser` row, or being the PI.
- **Resource filters match partially** (decided 2026-11-02): case-insensitive `icontains`.
- **Paginated.** Lists use DRF's `PageNumberPagination`, 100 per page by default and up to
  1000 with `?page_size=`. The allocation list in particular runs to thousands of rows.

## Who can see what

| Caller | Own data | Anyone's data | Private attributes |
| --- | --- | --- | --- |
| Any authenticated user | yes | no: 404 for someone else's username, not 403, so the API doesn't confirm who exists | no |
| Superusers | yes | yes | yes |
| Staff who aren't superusers | yes | yes | no |
| A service account with `rest_api.view_any_person` | yes | yes | no |

**The service account permission is the API's own,** not ColdFront's
`project.can_view_all_projects` / `allocation.can_view_all_allocations`. ColdFront's web
pages check those two as well, so granting them would also let the account browse every
project and allocation in the UI. `view_any_person` means nothing outside `/api/v1/`.

- **Defining it adds no table.** A data migration creates the permission against a
  `rest_api | api` content type that has no table behind it, the usual way to define a
  permission that isn't about a model.
- **A service account is an ordinary Django user** with that permission, an unusable password
  (so it can't log in to the web UI, only use its token) and `is_staff` off.
- **Its token is issued by an admin,** with DRF's `manage.py drf_create_token <username>` or in
  the admin's Tokens page. ColdFront's own token page only serves the logged-in user.
- **Private attributes stay superuser-only.** `view_any_person` widens *whose* data an account
  can read, not *what*. If a service ever needs private attributes, that is a second permission,
  not a staff or superuser flag on the account.
- **Every request a service account makes is logged** with the username it asked about, so
  there is a record of who looked up whom.

## Endpoints

### `GET /api/v1/users/<username>/projects/`

The **Active** projects `<username>` is an **Active** member of, plus any Active project they are
PI of. Projects in any other status (New, Archived, ...) are left out.

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
[alert audiences plan][alert-audiences]) from a plain member without a second request.

[alert-audiences]: https://github.com/Tufts-Technology-Services/tufts-coldfront-plugins/blob/main/docs/alert-audiences-plan.md#whos-who

### `GET /api/v1/allocations/`

Allocations the caller may see (see [Who can see what](#who-can-see-what)), filtered by:

| Parameter | Matches | Example |
| --- | --- | --- |
| `resource_type` | `resources__resource_type__name`, case-insensitive partial | `?resource_type=storage` |
| `resource` | `resources__name`, case-insensitive partial | `?resource=tier 2` |
| `status` | `status__name` | `?status=Active` |
| `project` | `project_id` | `?project=412` |
| `username` | an Active `AllocationUser`, or the project's PI | `?username=smith01` |

Only allocations on Active projects are listed. Each filter can be repeated to match any of
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

### `GET /api/v1/users/<username>/storage-quotas/`

Everything about one person's storage, in one response:

- **`areas`:** their quota and usage in each user-quota area on the hpc VAST: their home folder
  (`/homedir`) and scratch (`/scratch`, added 2026-11-02). Each area is the person's user quota
  inside that area's directory quota (option A below), looked up the same way.
- **`allocations`:** quota and usage for each storage allocation they belong to (added
  2026-11-02), live from VAST where the allocation is on VAST, from ColdFront's stored values
  where it is on TrueNAS. See [Project allocations](#project-allocations).

```json
{
  "username": "smith01",
  "areas": [
    {
      "name": "home",
      "path": "/homedir",
      "scope": "user",
      "quota_source": "override",
      "soft_limit_bytes": 100000000000,
      "hard_limit_bytes": 100000000000,
      "used_bytes": 85136281441,
      "used_inodes": 478373,
      "state": "OK",
      "retrieved_at": "2026-11-02T23:39:37Z"
    },
    {
      "name": "scratch",
      "path": "/scratch",
      "scope": "user",
      "quota_source": "default",
      "soft_limit_bytes": null,
      "hard_limit_bytes": null,
      "used_bytes": 0,
      "used_inodes": 0,
      "state": "OK",
      "retrieved_at": "2026-11-02T23:39:37Z"
    }
  ],
  "allocations": [
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
    },
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
  ]
}
```

(The scratch numbers above are placeholders: nothing about `/scratch` on VAST has been checked
yet. See [Scratch](#scratch).)

- **One list, not one endpoint per area,** so a dashboard gets everything in one request, and a
  third area later is a settings change, not a new URL.
- **Each area is looked up separately.** If VAST fails for one area, that area's entry carries
  `"error": "unavailable"` in place of the numbers and the others are still answered. The
  response is a 503 only when every area fails.

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
  quotas alike.
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

**One person is one small call** (confirmed 2026-11-02). `/userquotas/` filters server-side on
entry fields: `?path=/homedir` cut 16,548 entries to 10,634, and
`?path=/homedir&entity_identifier=tphimm01` returned two, the `tphimm01` **user** (200 GB
override, 58 GB used) and the `tphimm01` **group**. Users and groups share names, so the
`is_group: false` match above is required, not a precaution. The storage plugin makes that call
per person, then with the UID if the username finds no user entry, and caches the answer for a
few minutes. No scheduled task or bulk copy is needed.

Then:

- **The VAST call belongs in coldfront-storage-plugin**, in `storage/vast/vast.py`, which
  already owns `get_vast_client()` and the client config. `rest_api` calls it, as
  `tufts_local` calls `storage.truenas` for the tier 2 report. The VAST calls go in
  vast-api-client first, as methods next to `get_quotas()`: the quota detail
  (`GET /quotas/{id}`) and the user quota entries (`GET /userquotas/`, following `next` across
  pages).
- **Each area's quota `system_id` and default limits** come from `GET /quotas/{id}`, found by
  path once and cached for an hour: they change only when someone edits the quota.
- **The existing `get_all_quotas()` can't be reused as it is.** It keeps only `path`,
  `soft_limit`, `hard_limit` and `pretty_state`, and drops `system_id`,
  `default_user_quota` and every usage field.
- **Errors:** VAST unreachable or timing out is a 503 with a short message, never VAST's own
  error text, which includes the VMS hostname (the quota's `url` field does too, so it is never
  passed through). A username ColdFront doesn't know is a 404, as on the other endpoints;
  VAST is only asked about known users.
- **Settings:** `USER_QUOTA_CLIENT` (`hpc` at Tufts) and `USER_QUOTA_AREAS`, a name-to-path map
  (`{"home": "/homedir", "scratch": "/scratch"}`), in the order the response lists them. Neither
  has a default: a deployment that hasn't set them gets a system check error, not a guess.
- **Each area's `path` is its directory quota** (`/homedir`, `/scratch`), the quota the user quota
  sits in, with `"scope": "user"`, so a caller doesn't read it as the size of one folder.
- **Everything above applies per area:** each area's `system_id` and default limits come from
  its own `GET /quotas/{id}`, and each person is one `/userquotas/?path=<area>&entity_identifier=`
  call per area.

### Scratch

Added 2026-11-02. The lookup is assumed to work as it does for `/homedir`; none of this is checked
yet:

- **Is there a VAST quota at path `/scratch`,** and is that the path VAST uses (home is
  `/homedir` on VAST but `/cluster/home` on the cluster)?
- **Does it have user quotas** (`is_user_quota: true`, a `default_user_quota`)? If scratch has a
  directory quota but no user quotas, there is no per-person limit: the area can report the
  person's usage only if `/userquotas/` still lists them, and `null` limits otherwise.
- **Does `/userquotas/?path=/scratch&entity_identifier=<UTLN>` return that person's entry,** as it
  does for `/homedir`?

Checking them takes the same two calls as for home: `GET /quotas/?path=/scratch` and the
filtered `/userquotas/` query.


### Project allocations

Added 2026-11-02: quota and usage for each storage allocation the person belongs to, as close to
real time as makes sense.

**Which allocations:** Active allocations on Active projects where the person is an Active
`AllocationUser`, limited to resources that have a `StorageHandler` (so only storage). This uses
ColdFront's own allocation membership rather than project membership: someone can be on a
project without being on each of its allocations.

**Where each one lives.** The storage plugin already records it:

- The allocation's resource has a `StorageHandler` (one per `Resource`) whose `quota_client_id`
  names an entry in `STORAGE_PLUGIN_CLIENTS`: `hpc` or `rstore` (two VAST instances) or
  `truenas`. So allocations of one person can be spread across VAST instances, and each is asked
  of its own.
- That client config's `native_path_attribute_name` names the allocation attribute holding the
  path on the storage system (`vast_path` for both VAST instances).
- **Which kind of system a client is** isn't recorded in its config today, only implied by the
  handler's task names (`storage.vast...` vs `storage.truenas...`). The storage plugin should get
  an explicit `"type": "vast"` / `"truenas"` in each `STORAGE_PLUGIN_CLIENTS` entry
  (coldfront-ansible's Tufts settings) rather than parse task names.

**VAST allocations: live.** One `GET /quotas/?path=<vast_path>` to that allocation's VAST
instance, kept in step with the area lookups:

- **Limits:** `soft_limit` and `hard_limit`, both reported (either can be null). The storage
  plugin's batch task records `soft_limit`, falling back to `hard_limit`, as the allocation's
  quota; callers wanting the one ColdFront shows should do the same.
- **Usage comes from VAST, not Starfish.** ColdFront's stored usage (`reported_usage_bytes`) is
  written by the Starfish task from a once-a-day snapshot, too stale for this. The directory
  quota itself reports usage: `used_capacity` or `used_effective_capacity` (see the open
  question below). Every allocation the storage plugin provisions on VAST gets a directory quota
  at its path (`add_quota_and_protected_path`), so the quota lookup finds usage too.
- **`retrieved_at`** is the time of the VAST call. Unlike user quotas, a directory quota carries no
  "last updated" time; VAST keeps directory quota usage current itself.
- **Cached for a minute or two per path,** so a dashboard refreshing doesn't hit VAST every time,
  while still being close to live. Paths are cached per client, so the same path on two
  instances never collides.
- **A path VAST has no quota for** gets `"error": "no quota"` for that allocation; the rest of
  the response is unaffected.

**TrueNAS allocations: stored.** Read from the allocation's attributes, with no call out:
`reported_quota_bytes` and `quota_report_date` (written by the TrueNAS quota batch task), and
`reported_usage_bytes` and `usage_report_date` (written by the Starfish usage task, a once-a-day
snapshot, which Tufts considers adequate for TrueNAS). The entry has `"source": "stored"` and both
report dates, so a caller can tell how old each number is.

**No paths in the response.** The allocation is identified by its id, project and resource
name. `vast_path` and `Storage Path` are allocation attributes that may be private, and the
storage system path is never returned to callers who couldn't see it on the allocations endpoint.

**Errors** work as for the areas: a VAST instance that is down marks only its allocations
`"error": "unavailable"`.

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
Each VAST allocation entry therefore also carries the stored Starfish figure, `stored_used_bytes`
with `usage_reported_at`, so a caller can show the number ColdFront shows, or both.

```
coldfront-rest-api-plugin/
    pyproject.toml
    rest_api/
        __init__.py
        apps.py          # AppConfig; registers the system checks
        checks.py        # DRF and authtoken installed, coldfront.plugins.api not
        migrations/      # the view_any_person permission (data migration, no tables)
        permissions.py   # can see anyone (staff, superusers, view_any_person) vs. only yourself
        serializers.py   # attribute serializers: private ones for superusers only
        filters.py       # AllocationFilter (django-filter FilterSet)
        views.py
        urls.py          # mounted at api/ by coldfront-ansible; routes under v1/
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
   checks, the permission class, the `view_any_person` migration, pagination, and the projects
   endpoint. This sets the patterns the other two follow. Deploy order:
   1. the plugin merged and pushed;
   2. the fork's `tufts` extra names it, and `uv.lock` is updated, committed and pushed;
   3. coldfront-ansible adds `django_filters`, `rest_framework`, `rest_framework.authtoken` and
      `{app: rest_api, urls: api/}` to `tufts_plugin_apps`, and `REST_FRAMEWORK` to the Tufts
      settings, in the same deploy. Adding the apps before the package is installed would stop
      ColdFront starting; the plugin's system checks stop it starting without the settings.
2. **Allocations endpoint** with its filters.
3. **Storage quotas (home, scratch and allocations):** the vast-api-client calls, the `"type"`
   key in `STORAGE_PLUGIN_CLIENTS`, then the storage plugin functions and their tests, then the
   endpoint. Scratch needs its VAST quota checked first ([Scratch](#scratch)), and allocations
   need the usage field settled ([Project allocations](#project-allocations)); home is ready.
4. **Later:** an OpenAPI schema (drf-spectacular isn't installed today).

## Testing

- DRF's `APIClient` with `force_authenticate`, in `rest_api/tests/test_*.py`.
- A permission matrix per endpoint: the person themselves, another user (404), staff who
  aren't superusers, superusers, and a service account with and without `view_any_person`.
  Also a user holding ColdFront's `can_view_all_*` permissions but not ours, who still gets a
  404 for someone else.
- Private attributes appear for superusers and for nobody else: not staff who aren't
  superusers, not the person themselves, not a service account.
- A service account's lookups are logged with the username asked about.
- Each allocation filter, including an allocation with two resources matching once, not twice,
  and a repeated partial filter matching either value.
- Projects and allocations on New or Archived projects never appear, and neither do projects
  where the person's `ProjectUser` row is Removed.
- The system checks: an error when `rest_framework` or `rest_framework.authtoken` isn't
  installed, and when `coldfront.plugins.api` is.
- Storage quotas with a fake VAST client, like `FakeTrueNASClient` in the storage plugin's
  `test_tasks.py`: found by username, found by UID, no entry (default limits, 0 used), one area
  failing while the other answers, every area failing (503), and the cache answering a second
  request.
- Allocations: a VAST allocation on each of two instances asked of its own instance, a TrueNAS
  allocation read from stored attributes with no call out, an allocation on a non-storage
  resource left out, one instance down marking only its allocations, and no path in any
  response.
- A query-count test on each list (`django_assert_max_num_queries`), so a missing
  `prefetch_related` shows up as a failure, not as a slow page in production.

## Open questions

None. Answered 2026-11-02 (the first three here on 2026-11-16) and written into
[Decisions](#decisions) and the endpoint sections:

- `PLUGIN_API` goes off and the API is a new plugin, `rest_api`, mounted at
  `/api/v1/`. Nobody at Tufts uses ColdFront's `/api/`.
- Superusers see private attributes; nobody else does, staff who aren't superusers and service
  accounts included. This matches ColdFront's web pages.
- Staff can look up anyone's projects, allocations and quotas, as they could in ColdFront's
  `/api/`.
- A service account may ask about anyone, only with `rest_api.view_any_person`.
- Only Active projects; membership is an Active `ProjectUser` row or being the PI.
- Resource filters match partially (`icontains`).
- Home folders: option A, the person's user quota inside `/homedir`, looked up per person with
  `/userquotas/?path=/homedir&entity_identifier=`, UIDs resolved with `getent`.
- Scratch (`/scratch`) is reported the same way, in the same response. Its VAST quota is not
  checked yet; see [Scratch](#scratch).
- The person's storage allocations are in the same response: live from VAST, stored values for
  TrueNAS. See [Project allocations](#project-allocations).
