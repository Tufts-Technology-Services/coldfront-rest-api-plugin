# Plan: writes through plugin extensions

Proposed 2026-11-17; nothing here is built or decided. The API is read-only today (see
[rest-api-plan.md](rest-api-plan.md), "Decisions"). This is what the
[plugin extension](rest-api-plan.md#plugin-extensions) contract would need for an extension to
accept changes as well: creating, updating and deleting its items.

## Goal

A plugin can let callers change its own data through the API, on the same terms as reading it: the
API knows nothing about the plugin, the plugin knows nothing about HTTP, and neither imports the
other. Writes stay opt-in per extension, and per operation, so every extension that exists today
stays read-only without a change.

A likely first use: a storage quota change, made as a ColdFront allocation change request so that
ticketing and the approvals follow it (quota changes go only through change requests, as decided
for the request form).

## What changes for callers

| Request | Extension method | Success |
| --- | --- | --- |
| `GET <target>/<name>/` | `summary()` | 200 (as today) |
| `GET <target>/<name>/<key>/` | `item()` | 200 (as today) |
| `POST <target>/<name>/` | `create()` | 201, the new item, and a `Location` header with its URL |
| `PATCH <target>/<name>/<key>/` | `update()` | 200, the item as it now is |
| `DELETE <target>/<name>/<key>/` | `delete()` | 204, no body |

- **A method the extension doesn't implement is a 405,** with an `Allow` header listing the
  methods it does. `PUT` is a 405 everywhere: `PATCH` changes only the fields sent, which is what
  callers want, and supporting both doubles every extension's work.
- **The body is a JSON object.** Anything else (not JSON, a list, form data) is a 400 from the API
  before the extension is asked.
- **`Location` is built by the API,** from the key the extension returns, on the prefix the caller
  used: the same rule as items by key, so an extension still never builds a URL.

## The contract

Additions to `coldfront_utils.api_extensions`, all optional for an extension:

```python
class ApiExtension:
    # (today's attributes, allows(), summary(), item())

    def allows_write(self, target, caller, operation, key=None) -> bool:
        """Whether caller may make this change: operation is "create", "update" or "delete", key the
        item's for update and delete. Only asked once allows() has said caller may see target.
        Required if the extension implements any write method; there's no default."""

    def create(self, target, caller, data, params) -> dict:
        """Make a new item from data (the request's JSON object). Return the new item as item()
        would, including its "key", which the API uses for Location."""

    def update(self, target, key, caller, data, params) -> dict:
        """Change the item named key with the fields in data, and return it as item() would."""

    def delete(self, target, key, caller, params) -> None:
        """Remove the item named key."""
```

- **Opt-in by implementing.** The API offers a method only if the extension overrides it,
  checked as `allows()` and `summary()` are checked today: at registration.
- **`allows_write()` is required** once any write method is implemented, and is refused at
  registration otherwise, so a write can't be open by accident (fail closed, as `allows()` is).
- **Errors**, as exceptions the API maps to responses:
  - `ExtensionBadRequest`, 400, gains field errors: `ExtensionBadRequest("The quota is invalid.",
    errors={"quota_tb": ["Must be at least 0.1."]})` becomes `{"detail": ..., "errors": {...}}`.
    A message alone still works as today. A Django form's `form.errors` fits `errors` as it is,
    so an extension can validate with the forms it already has.
  - `ExtensionConflict`, new, 409: the change can't be made in the item's current state (a change
    request already pending, a share still being created).
  - `ExtensionNotFound` (404) and `ExtensionUnavailable` (503), as today.
- **Validation is the extension's.** The contract doesn't take a DRF serializer, which would make
  plugins depend on DRF; a Django form, or plain checks, raise `ExtensionBadRequest`.

## Who may write

Three checks, in this order, each failing closed:

1. **The API's own write permission,** `rest_api.change_through_api` (new, on `ApiAccess`, as
   `view_any_person` is). Without it, every write is a 403, whatever the extension says. So a
   token can only read unless an admin has granted its owner this, and a leaked token of an
   ordinary user can't change anything. Session callers (a signed-in browser) need it too: one rule
   for every way in.
2. **`allows(target, caller)`,** as for reading. Refused, it's the same 404 as today, so a write
   reveals no more about what exists than a read does.
3. **`allows_write(target, caller, operation, key)`.** Refused, it's a 403: the caller can already
   see the target, so the 403 reveals nothing new.

Service accounts that write need all three: `change_through_api`, and whatever the plugin's own
permissions are.

## What the API does around a write

- **The acting user.** `coldfront_utils.task_context`'s `ActingUserMiddleware` reads
  `request.user` while the middleware runs, before DRF has authenticated a token, so for a
  token-authenticated request it sees nobody (checked 2026-11-17 in `task_context/middleware.py`).
  The API therefore runs each write inside `acting_as(caller.get_username())`, so tasks the write
  queues carry who made it, as they do for the web pages.
- **History.** simple_history reads `request.user` when a row is saved, and DRF sets the
  underlying request's user once it authenticates, so `history_user` should be the caller. To prove
  with a test before relying on it.
- **One transaction.** Each write runs in `transaction.atomic()` (`ATOMIC_REQUESTS` is off at
  Tufts), so a write that fails partway leaves nothing behind. Extensions queue tasks with
  `transaction.on_commit()`, as plugins already must.
- **Through ColdFront's own paths.** The extension must make changes the way ColdFront's views do
  (model methods, ColdFront's signals with a `sender` receivers accept, change requests rather than
  direct edits where ColdFront has them), so ticketing, Grouper and storage tasks follow an API
  change as they follow one made on a page. The contract can't enforce this; each extension's
  review and tests must.
- **Logging.** Every write, by anyone, at INFO to a new `rest_api.changes` logger: caller, method,
  path and status, e.g. `smith01 PATCH /api/v2/allocations/9031/quota-change/412/: 200`. Not the
  body, which may hold personal data. Reads stay logged for service accounts only, as today.
- **Discovery** lists each extension's operations:
  `{"name": "quota-change", ..., "operations": ["read", "create"]}`.
- **CSRF.** DRF's `SessionAuthentication` already enforces it for session callers' writes; token
  callers don't send cookies, so need none.

## Versioning

The shape an extension accepts is part of its version, like the shape it returns. A breaking
change to what `create()` or `update()` accepts is a new extension name, as for reads. A new
optional field isn't breaking.

## Not in the first version

- **Writes to the API's own endpoints** (projects, allocations). ColdFront's own flows for those
  (allocation requests, change requests, approvals) would come as extensions too, if at all: the
  first open question below.
- **Long-running changes** (202 Accepted). A change that queues work answers 201 or 200 with the
  item as it stands (a change request "Pending", say), and the caller reads the item again for
  progress. A 202 with a status URL can come if a use needs it.
- **Retries and concurrency.** A retried `POST` can create twice; an `Idempotency-Key` header can
  come later, and extensions should make `create()` idempotent where the data allows (an item keyed
  by what it's for). Concurrent `PATCH`es: the last one wins; `ETag`/`If-Match` can come later.
- **Rate limits.** DRF's throttling, for writes by tokens, if a caller misbehaves.
- **Bulk changes.** One item per request.

## Testing

- coldfront-utils: registration (write methods without `allows_write()` refused; each method
  detected as offered), the new exception and `ExtensionBadRequest`'s errors.
- rest_api, with fake extensions: each method's status and body; 405 with `Allow` for what isn't
  offered and for `PUT`; a body that isn't a JSON object a 400 before the extension runs; the three
  checks in order (no `change_through_api` 403, `allows()` refused 404, `allows_write()` refused
  403) with the extension never asked when one fails; `Location` on every prefix; a failure partway
  rolls back; tasks queued in a write carry the caller as acting user, token and session both;
  `history_user` is the token caller; every write logged without its body; discovery's operations.
- Each plugin: its extension's validation, `allows_write()` and that its changes go through
  ColdFront's paths (signals sent, change requests made).

## Open questions

1. **What's first, and whose?** The quota change as a change request is the likely first use.
   Allocation change requests are ColdFront's, not a plugin's: does the storage plugin's extension
   make them (it owns quotas), or does the API register extensions for ColdFront's own flows?
2. **One API-wide write permission** (`change_through_api`, proposed) or none, leaving it all to
   each extension's own permissions? One is simpler to audit and fails closed; none is one fewer
   grant.
3. **Should a person's own token be able to write at all,** or only service accounts and
   sessions? With the permission above it's an admin's choice per person.
4. **The 400 body's shape:** `{"detail": ..., "errors": {...}}` (proposed), or DRF's own
   `{"field": [...]}` at the top level, which the API's own endpoints would produce if they ever
   took writes.

## Effort

About two and a half days before any plugin's own extension: coldfront-utils (the methods,
registration checks, `ExtensionConflict` and field errors, tests: half a day to a day), rest_api
(the routes' write methods, the three checks and the permission's migration, transactions, acting
user, logging, discovery, tests: about a day and a half). Then each extension's own work, which for
a quota change request depends on how ColdFront's change request is made outside its view.
