"""
GET /api/v2/users/<username>/storage/ and /storage/<area>/: a person's own storage areas (home,
scratch), with their user quota and usage from VAST. See docs/rest-api-plan.md.
"""

import logging
import sys

import pytest
from django.core.cache import cache
from django.urls import reverse
from vast_api_client.exceptions import VastConnectionError

from rest_api import user_storage

GB = 1_000_000_000

AREAS = {
    "home": {"client": "hpc", "path": "/homedir"},
    "scratch": {"client": "hpc", "path": "/scratch"},
}


def user_entry(identifier, *, path="/homedir", system_id=466, soft=30 * GB, hard=30 * GB, used=GB, kind="username"):
    """A user quota entry as VAST lists it."""
    return {
        "id": hash((identifier, path)) % 100000,
        "path": path,
        "quota_system_id": system_id,
        "soft_limit": soft,
        "hard_limit": hard,
        "used_capacity": used,
        "used_inodes": 1234,
        "state": "OK",
        "entity": {"identifier": identifier, "identifier_type": kind, "is_group": False},
    }


def group_entry(identifier, *, path="/homedir", system_id=466):
    entry = user_entry(identifier, path=path, system_id=system_id, soft=None, hard=None, used=5)
    entry["entity"] = {"identifier": identifier, "identifier_type": "groupname", "is_group": True}
    return entry


class FakeVast:
    """Stands in for VASTClient: the quota and user quota calls, filtered as VAST filters them."""

    def __init__(self, entries=()):
        self.quotas = {
            "/homedir": {
                "id": 484,
                "path": "/homedir",
                "system_id": 466,
                "default_user_quota": {"soft_limit": 30 * GB, "hard_limit": 30 * GB},
                "last_user_quotas_update": "2026-11-16T21:49:07.652033Z",
            },
            "/scratch": {
                "id": 680,
                "path": "/scratch",
                "system_id": 657,
                "default_user_quota": {"soft_limit": 100 * GB, "hard_limit": 100 * GB},
                "last_user_quotas_update": "2026-11-16T21:49:07.652033Z",
            },
        }
        self.entries = list(entries)
        self.calls = []
        self.failure = None

    def _record(self, *call):
        self.calls.append(call)
        if self.failure:
            raise self.failure

    def get_quotas(self, path=None):
        self._record("get_quotas", str(path))
        return [quota for quota in self.quotas.values() if quota["path"].startswith(str(path))]

    def get_quota(self, quota_id):
        self._record("get_quota", quota_id)
        return next(quota for quota in self.quotas.values() if quota["id"] == quota_id)

    def get_user_quotas(self, path=None, identifier=None, **kwargs):
        self._record("get_user_quotas", str(path), str(identifier))
        return [
            entry
            for entry in self.entries
            if entry["path"] == str(path) and entry["entity"]["identifier"] == str(identifier)
        ]


@pytest.fixture(autouse=True)
def fresh_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def storage_settings(settings, monkeypatch):
    settings.USER_STORAGE_AREAS = AREAS
    settings.STORAGE_PLUGIN_CLIENTS = [{"client_key": "hpc", "host": "vms.example.edu", "user": "u", "password": "p"}]
    monkeypatch.setenv("STORAGE_LOG_ONLY", "False")
    return settings


@pytest.fixture
def vast(storage_settings, monkeypatch):
    """The fake VAST every area's client is, and no UIDs unless a test gives them."""
    fake = FakeVast()
    monkeypatch.setattr(user_storage, "vast_client_for", lambda client_key: fake)
    monkeypatch.setattr(user_storage, "uid_of", lambda username: None)
    return fake


@pytest.fixture
def smith(make_user):
    return make_user("smith01")


def areas_url(username, version="v2"):
    return reverse(f"rest_api:{version}:user-storage", kwargs={"username": username})


def area_url(username, area, version="v2"):
    return reverse(f"rest_api:{version}:user-storage-area", kwargs={"username": username, "area": area})


def get_area(api_client, caller, username, area="home"):
    api_client.force_authenticate(caller)
    return api_client.get(area_url(username, area))


def test_the_plugin_doesnt_import_the_storage_plugin():
    # plugins don't import each other; this one reads STORAGE_PLUGIN_CLIENTS instead
    assert not [name for name in sys.modules if name == "storage" or name.startswith("storage.")]


@pytest.mark.parametrize("version, prefix", [("v2", "/api/v2"), ("latest", "/api/latest"), ("unversioned", "/api")])
def test_the_urls(version, prefix):
    assert areas_url("smith01", version) == f"{prefix}/users/smith01/storage/"
    assert area_url("smith01", "home", version) == f"{prefix}/users/smith01/storage/home/"


# The list of areas


@pytest.mark.parametrize("version", ["v2", "latest", "unversioned"])
def test_the_areas_in_settings_order_with_urls_on_the_prefix_used(api_client, vast, smith, version):
    api_client.force_authenticate(smith)

    response = api_client.get(areas_url("smith01", version))

    assert response.status_code == 200
    assert response.json() == {
        "username": "smith01",
        "areas": [
            {"name": "home", "url": f"http://testserver{area_url('smith01', 'home', version)}"},
            {"name": "scratch", "url": f"http://testserver{area_url('smith01', 'scratch', version)}"},
        ],
    }
    assert vast.calls == []


def test_no_areas_when_none_are_configured(api_client, settings, smith):
    api_client.force_authenticate(smith)

    response = api_client.get(areas_url("smith01"))

    assert response.json() == {"username": "smith01", "areas": []}


def test_needs_authentication(api_client, vast, smith):
    assert api_client.get(areas_url("smith01")).status_code == 401
    assert api_client.get(area_url("smith01", "home")).status_code == 401


def test_is_read_only(api_client, vast, smith):
    api_client.force_authenticate(smith)

    assert api_client.post(areas_url("smith01"), {}).status_code == 405
    assert api_client.post(area_url("smith01", "home"), {}).status_code == 405


# One area


def test_the_response_shape(api_client, vast, smith):
    vast.entries = [user_entry("smith01", used=12 * GB)]

    response = get_area(api_client, smith, "smith01")

    assert response.status_code == 200
    assert response.json() == {
        "username": "smith01",
        "area": "home",
        "path": "/homedir",
        "scope": "user",
        "quota_source": "default",
        "soft_limit_bytes": 30 * GB,
        "hard_limit_bytes": 30 * GB,
        "used_bytes": 12 * GB,
        "used_inodes": 1234,
        "state": "OK",
        "retrieved_at": "2026-11-16T21:49:07.652033Z",
    }


def test_limits_that_differ_from_the_default_are_an_override(api_client, vast, smith):
    vast.entries = [user_entry("smith01", soft=200 * GB, hard=None)]

    body = get_area(api_client, smith, "smith01").json()

    assert body["quota_source"] == "override"
    assert body["soft_limit_bytes"] == 200 * GB
    assert body["hard_limit_bytes"] is None


def test_someone_with_no_entry_gets_the_default_and_nothing_used(api_client, vast, smith):
    body = get_area(api_client, smith, "smith01").json()

    assert body["quota_source"] == "default"
    assert (body["soft_limit_bytes"], body["hard_limit_bytes"]) == (30 * GB, 30 * GB)
    assert (body["used_bytes"], body["used_inodes"], body["state"]) == (0, 0, None)


def test_each_area_is_its_own_quota(api_client, vast, smith):
    vast.entries = [user_entry("smith01", path="/scratch", system_id=657, soft=100 * GB, hard=100 * GB, used=7 * GB)]

    body = get_area(api_client, smith, "smith01", area="scratch").json()

    assert (body["area"], body["path"], body["used_bytes"]) == ("scratch", "/scratch", 7 * GB)
    assert body["quota_source"] == "default"


@pytest.mark.parametrize(
    "entry",
    [
        group_entry("smith01"),
        user_entry("smith01", system_id=999),
        user_entry("smith01", kind="uid"),
    ],
    ids=["a group of the same name", "another quota", "recorded as a uid"],
)
def test_entries_that_arent_the_persons_own_are_ignored(api_client, vast, smith, entry):
    vast.entries = [entry]

    assert get_area(api_client, smith, "smith01").json()["used_bytes"] == 0


def test_an_entry_marked_as_a_group_is_ignored_whatever_its_identifier_type(api_client, vast, smith):
    # VAST gives groups a groupname or gid identifier type too, but is_group is what says it's a group
    entry = user_entry("smith01")
    entry["entity"]["is_group"] = True
    vast.entries = [entry]

    assert get_area(api_client, smith, "smith01").json()["used_bytes"] == 0


def test_the_user_entry_is_found_beside_a_group_of_the_same_name(api_client, vast, smith):
    vast.entries = [group_entry("smith01"), user_entry("smith01", used=3 * GB)]

    assert get_area(api_client, smith, "smith01").json()["used_bytes"] == 3 * GB


def test_someone_vast_records_by_uid_is_found_by_their_uid(api_client, vast, smith, monkeypatch):
    monkeypatch.setattr(user_storage, "uid_of", lambda username: 31415)
    vast.entries = [user_entry("31415", kind="uid", used=4 * GB)]

    assert get_area(api_client, smith, "smith01").json()["used_bytes"] == 4 * GB
    assert ("get_user_quotas", "/homedir", "31415") in vast.calls


def test_a_uid_isnt_asked_for_when_the_username_is_found(api_client, vast, smith, monkeypatch):
    monkeypatch.setattr(user_storage, "uid_of", lambda username: pytest.fail("uid looked up"))
    vast.entries = [user_entry("smith01")]

    assert get_area(api_client, smith, "smith01").status_code == 200


def test_a_uid_matches_only_an_entry_recorded_by_uid(api_client, vast, smith, monkeypatch):
    monkeypatch.setattr(user_storage, "uid_of", lambda username: 31415)
    vast.entries = [user_entry("31415", kind="username", used=4 * GB)]

    assert get_area(api_client, smith, "smith01").json()["used_bytes"] == 0


def test_uid_of_is_none_for_someone_getent_doesnt_know(monkeypatch):
    def unknown(username):
        raise ValueError(f"User {username} does not exist")

    monkeypatch.setattr(user_storage, "get_uid", unknown)

    assert user_storage.uid_of("ghost01") is None


# Errors


def test_an_area_that_isnt_configured_is_a_404(api_client, vast, smith):
    assert get_area(api_client, smith, "smith01", area="archive").status_code == 404
    assert vast.calls == []


def test_an_unknown_username_is_a_404(api_client, vast, make_user):
    caller = make_user("caller", superuser=True)

    assert get_area(api_client, caller, "nobody99").status_code == 404
    assert vast.calls == []


def test_storage_lookups_off_is_a_503_that_asks_nothing(api_client, vast, smith, monkeypatch):
    monkeypatch.setenv("STORAGE_LOG_ONLY", "True")

    response = get_area(api_client, smith, "smith01")

    assert response.status_code == 503
    assert "off" in response.json()["detail"]
    assert vast.calls == []


def test_storage_lookups_are_off_unless_turned_on(api_client, vast, smith, monkeypatch):
    # as in the storage plugin, which reads the same variable with the same default
    monkeypatch.delenv("STORAGE_LOG_ONLY")

    assert get_area(api_client, smith, "smith01").status_code == 503


def test_vast_failing_is_a_503_without_vasts_own_text(api_client, vast, smith):
    vast.failure = VastConnectionError("GET userquotas on vms.example.edu failed: secret detail")

    response = get_area(api_client, smith, "smith01")

    assert response.status_code == 503
    assert "vms.example.edu" not in response.content.decode()
    assert "secret" not in response.content.decode()


def test_an_area_path_with_no_quota_is_a_503(api_client, vast, smith, settings):
    settings.USER_STORAGE_AREAS = {"home": {"client": "hpc", "path": "/nowhere"}}

    assert get_area(api_client, smith, "smith01").status_code == 503


# Who can see whose


def test_another_persons_storage_is_a_404(api_client, vast, make_user, smith):
    response = get_area(api_client, make_user("jones01"), "smith01")

    assert response.status_code == 404
    assert vast.calls == []


@pytest.mark.parametrize("flags", [{"superuser": True}, {"view_any_person": True}])
def test_superusers_and_service_accounts_see_anyones(api_client, vast, make_user, smith, flags):
    caller = make_user("caller", **flags)

    assert get_area(api_client, caller, "smith01").status_code == 200
    api_client.force_authenticate(caller)
    assert api_client.get(areas_url("smith01")).status_code == 200


@pytest.mark.parametrize(
    "flags",
    [
        {"staff": True},
        {"perms": ["project.can_view_all_projects"]},
        {"perms": ["allocation.can_view_all_allocations"]},
    ],
)
def test_staff_and_coldfronts_view_all_permissions_dont_open_it(api_client, vast, make_user, smith, flags):
    caller = make_user("caller", **flags)

    assert get_area(api_client, caller, "smith01").status_code == 404
    api_client.force_authenticate(caller)
    assert api_client.get(areas_url("smith01")).status_code == 404


def test_a_service_accounts_lookup_is_logged(api_client, vast, make_user, smith, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_area(api_client, make_user("svc-dashboard", view_any_person=True), "smith01")

    assert [record.getMessage() for record in caplog.records if record.name == "rest_api.lookups"] == [
        "svc-dashboard looked up smith01: /api/v2/users/smith01/storage/home/"
    ]


# Caching and clients


def test_an_answer_is_reused_for_a_while(api_client, vast, smith):
    vast.entries = [user_entry("smith01")]
    get_area(api_client, smith, "smith01")
    asked = len(vast.calls)

    get_area(api_client, smith, "smith01")

    assert len(vast.calls) == asked


def test_an_areas_quota_is_found_once_for_everyone(api_client, vast, make_user, smith):
    get_area(api_client, smith, "smith01")
    jones = make_user("jones01")
    get_area(api_client, jones, "jones01")

    assert [call for call in vast.calls if call[0] == "get_quotas"] == [("get_quotas", "/homedir")]


def test_each_area_asks_its_own_client(api_client, storage_settings, smith, monkeypatch):
    storage_settings.USER_STORAGE_AREAS = {
        "home": {"client": "hpc", "path": "/homedir"},
        "lab": {"client": "rstore", "path": "/homedir"},
    }
    asked = []

    def client_for(client_key):
        asked.append(client_key)
        return FakeVast()

    monkeypatch.setattr(user_storage, "vast_client_for", client_for)
    monkeypatch.setattr(user_storage, "uid_of", lambda username: None)

    get_area(api_client, smith, "smith01", area="home")
    get_area(api_client, smith, "smith01", area="lab")

    assert set(asked) == {"hpc", "rstore"}


def test_a_client_is_built_from_its_storage_plugin_entry(storage_settings):
    client = user_storage.vast_client_for("hpc")

    assert client.host == "vms.example.edu"


def test_an_unknown_client_key_is_an_error(storage_settings):
    with pytest.raises(user_storage.StorageUnavailable):
        user_storage.vast_client_for("nope")
