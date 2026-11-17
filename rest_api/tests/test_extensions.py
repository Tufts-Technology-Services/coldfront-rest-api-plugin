"""
Plugin extensions served by the API: routing, the target lookup and allows(), errors, logging and
the discovery list. The extensions here are fakes, registered for each test; real ones live in their
plugins, with their own tests.
"""

import logging

import pytest
from coldfront_utils.api_extensions import (
    AllocationExtension,
    ExtensionNotFound,
    ExtensionUnavailable,
    PersonExtension,
    ProjectExtension,
    can_view_allocation,
    can_view_project,
    extensions,
    register_api_extension,
)
from django.urls import reverse

# (extension name, method) for every summary() and item() call, so a test can check none was made
calls = []


class PersonNotes(PersonExtension):
    """Open to the person themselves and superusers. Items: any key but the special ones below."""

    name = "notes"
    description = "A person's notes"

    def allows(self, target, caller):
        return caller == target or caller.is_superuser

    def summary(self, target, caller):
        calls.append((self.name, "summary"))
        return {"extension": self.name, "version": self.version, "username": target.username}

    def item(self, target, key, caller):
        calls.append((self.name, "item"))
        if key == "missing":
            raise ExtensionNotFound(key)
        if key == "down":
            raise ExtensionUnavailable("Notes are unavailable right now.")
        if key == "broken":
            raise RuntimeError("the notes store sent something unexpected")
        return {"extension": self.name, "version": self.version, "username": target.username, "key": key}


class OldPersonNotes(PersonNotes):
    name = "old-notes"
    description = "A person's notes, the old way"
    deprecated = True


class ProjectNotes(ProjectExtension):
    """Open to whoever ColdFront's project page is."""

    name = "notes"
    description = "A project's notes"

    def allows(self, target, caller):
        return can_view_project(caller, target)

    def summary(self, target, caller):
        calls.append((self.name, "summary"))
        return {"extension": self.name, "version": self.version, "project": target.pk}


class AllocationUsage(AllocationExtension):
    """Open to whoever ColdFront's allocation page is."""

    name = "usage"
    description = "An allocation's usage"
    version = 2

    def allows(self, target, caller):
        return can_view_allocation(caller, target)

    def summary(self, target, caller):
        calls.append((self.name, "summary"))
        return {"extension": self.name, "version": self.version, "allocation": target.pk}

    def item(self, target, key, caller):
        calls.append((self.name, "item"))
        return {"extension": self.name, "version": self.version, "allocation": target.pk, "key": key}


@pytest.fixture(autouse=True)
def fake_extensions(monkeypatch):
    """A registry holding only the fakes above."""
    monkeypatch.setattr(extensions, "_registry", {})
    calls.clear()
    for extension_class in (PersonNotes, OldPersonNotes, ProjectNotes, AllocationUsage):
        register_api_extension(extension_class)


def extension_url(kind, name, key=None, version="v2", **target):
    """The URL of an extension's summary, or of one item if key is given."""
    url_name = f"rest_api:{version}:{kind}-extension" + ("-item" if key is not None else "")
    kwargs = {"name": name, **target} | ({"key": key} if key is not None else {})
    return reverse(url_name, kwargs=kwargs)


def get_as(api_client, caller, url):
    api_client.force_authenticate(caller)
    return api_client.get(url)


@pytest.fixture
def smith(make_user):
    return make_user("smith01")


@pytest.fixture
def project(make_user, make_project, add_member, smith):
    project = make_project(make_user("pi01"))
    add_member(project, smith)
    return project


@pytest.fixture
def allocation(make_allocation, add_allocation_user, project, smith):
    allocation = make_allocation(project)
    add_allocation_user(allocation, smith)
    return allocation


# the URLs


@pytest.mark.parametrize("version, prefix", [("v2", "/api/v2/"), ("latest", "/api/latest/"), ("unversioned", "/api/")])
def test_the_urls_under_every_prefix(version, prefix):
    assert extension_url("person", "storage", version=version, username="smith01") == f"{prefix}users/smith01/storage/"
    assert (
        extension_url("person", "storage", key="home", version=version, username="smith01")
        == f"{prefix}users/smith01/storage/home/"
    )
    assert extension_url("project", "notes", version=version, pk=7) == f"{prefix}projects/7/notes/"
    assert extension_url("allocation", "usage", key="x", version=version, pk=9) == f"{prefix}allocations/9/usage/x/"
    assert reverse(f"rest_api:{version}:extension-list") == f"{prefix}extensions/"


@pytest.mark.parametrize("version", ["latest", "unversioned"])
def test_latest_and_unversioned_serve_the_same_extensions(api_client, smith, version):
    response = get_as(api_client, smith, extension_url("person", "notes", version=version, username="smith01"))

    assert response.status_code == 200
    assert response.json() == {"extension": "notes", "version": 1, "username": "smith01"}


def test_the_apis_own_routes_win_over_an_extension_of_the_same_name(api_client, smith, project):
    class Projects(PersonNotes):
        name = "projects"

    register_api_extension(Projects)

    response = get_as(api_client, smith, reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"}))

    assert response.status_code == 200
    assert "results" in response.json()
    assert calls == []


# person extensions


def test_a_person_sees_their_own_summary(api_client, smith):
    response = get_as(api_client, smith, extension_url("person", "notes", username="smith01"))

    assert response.status_code == 200
    assert response.json() == {"extension": "notes", "version": 1, "username": "smith01"}


def test_a_person_sees_their_own_item(api_client, smith):
    response = get_as(api_client, smith, extension_url("person", "notes", key="2026", username="smith01"))

    assert response.status_code == 200
    assert response.json() == {"extension": "notes", "version": 1, "username": "smith01", "key": "2026"}


def test_whom_allows_admits_sees_someone_elses(api_client, make_user, smith):
    response = get_as(
        api_client, make_user("root01", superuser=True), extension_url("person", "notes", username="smith01")
    )

    assert response.status_code == 200
    assert response.json()["username"] == "smith01"


@pytest.mark.parametrize("key", [None, "2026"])
def test_whom_allows_refuses_gets_a_404_and_the_extension_is_not_asked(api_client, make_user, smith, key):
    response = get_as(api_client, make_user("jones01"), extension_url("person", "notes", key=key, username="smith01"))

    assert response.status_code == 404
    assert calls == []


def test_a_refusal_and_an_unknown_username_look_the_same(api_client, make_user, smith):
    jones = make_user("jones01")

    refused = get_as(api_client, jones, extension_url("person", "notes", username="smith01"))
    unknown = get_as(api_client, jones, extension_url("person", "notes", username="nobody99"))

    assert (refused.status_code, refused.json()) == (unknown.status_code, unknown.json())


def test_an_unknown_username_is_a_404_even_for_a_superuser(api_client, make_user):
    response = get_as(
        api_client, make_user("root01", superuser=True), extension_url("person", "notes", username="nobody99")
    )

    assert response.status_code == 404
    assert calls == []


def test_an_unregistered_name_is_a_404(api_client, smith):
    assert get_as(api_client, smith, extension_url("person", "diary", username="smith01")).status_code == 404
    assert get_as(api_client, smith, extension_url("person", "diary", key="a", username="smith01")).status_code == 404


def test_a_name_registered_for_another_kind_is_a_404(api_client, smith):
    response = get_as(api_client, smith, extension_url("person", "usage", username="smith01"))

    assert response.status_code == 404


def test_an_item_the_extension_has_no_items_for_is_a_404(api_client, project):
    pi = project.pi

    response = get_as(api_client, pi, extension_url("project", "notes", key="a", pk=project.pk))

    assert response.status_code == 404


def test_extension_not_found_is_a_404(api_client, smith):
    response = get_as(api_client, smith, extension_url("person", "notes", key="missing", username="smith01"))

    assert response.status_code == 404


def test_extension_unavailable_is_a_503_with_its_message(api_client, smith):
    response = get_as(api_client, smith, extension_url("person", "notes", key="down", username="smith01"))

    assert response.status_code == 503
    assert response.json() == {"detail": "Notes are unavailable right now."}


def test_any_other_failure_is_logged_with_the_extension_and_raised(api_client, smith, caplog):
    caplog.set_level(logging.ERROR, logger="rest_api.extensions")

    with pytest.raises(RuntimeError):
        get_as(api_client, smith, extension_url("person", "notes", key="broken", username="smith01"))

    messages = [record.getMessage() for record in caplog.records if record.name == "rest_api.extensions"]
    assert messages == ["The person extension notes (PersonNotes) failed: /api/v2/users/smith01/notes/broken/"]


def test_signing_in_is_required(api_client, smith):
    assert api_client.get(extension_url("person", "notes", username="smith01")).status_code == 401
    assert api_client.get(reverse("rest_api:v2:extension-list")).status_code == 401


def test_extensions_are_read_only(api_client, smith):
    api_client.force_authenticate(smith)

    assert api_client.post(extension_url("person", "notes", username="smith01"), {}).status_code == 405
    assert calls == []


# project and allocation extensions


def test_a_project_member_sees_the_projects_extension(api_client, smith, project):
    response = get_as(api_client, smith, extension_url("project", "notes", pk=project.pk))

    assert response.status_code == 200
    assert response.json() == {"extension": "notes", "version": 1, "project": project.pk}


def test_someone_off_the_project_gets_a_404(api_client, make_user, project):
    response = get_as(api_client, make_user("jones01"), extension_url("project", "notes", pk=project.pk))

    assert response.status_code == 404
    assert calls == []


def test_a_missing_project_is_a_404(api_client, make_user):
    response = get_as(api_client, make_user("root01", superuser=True), extension_url("project", "notes", pk=999999))

    assert response.status_code == 404
    assert calls == []


def test_an_allocation_user_sees_the_allocations_extension_and_its_items(api_client, smith, allocation):
    summary = get_as(api_client, smith, extension_url("allocation", "usage", pk=allocation.pk))
    item = get_as(api_client, smith, extension_url("allocation", "usage", key="today", pk=allocation.pk))

    assert summary.json() == {"extension": "usage", "version": 2, "allocation": allocation.pk}
    assert item.json() == {"extension": "usage", "version": 2, "allocation": allocation.pk, "key": "today"}


def test_someone_off_the_allocation_gets_a_404(api_client, make_user, allocation):
    response = get_as(api_client, make_user("jones01"), extension_url("allocation", "usage", pk=allocation.pk))

    assert response.status_code == 404
    assert calls == []


def test_a_missing_allocation_is_a_404(api_client, make_user):
    response = get_as(api_client, make_user("root01", superuser=True), extension_url("allocation", "usage", pk=999999))

    assert response.status_code == 404
    assert calls == []


# logging


def lookups(caplog):
    return [(record.name, record.getMessage()) for record in caplog.records if record.name == "rest_api.lookups"]


def test_a_service_accounts_person_lookup_is_logged(api_client, make_user, smith, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_as(
        api_client,
        make_user("svc-dashboard", view_any_person=True),
        extension_url("person", "notes", username="smith01"),
    )

    assert lookups(caplog) == [("rest_api.lookups", "svc-dashboard looked up smith01: /api/v2/users/smith01/notes/")]


def test_a_service_accounts_project_and_allocation_lookups_are_logged(
    api_client, make_user, project, allocation, caplog
):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")
    service_account = make_user("svc-dashboard", view_any_person=True)

    get_as(api_client, service_account, extension_url("project", "notes", pk=project.pk))
    get_as(api_client, service_account, extension_url("allocation", "usage", key="today", pk=allocation.pk))

    assert lookups(caplog) == [
        ("rest_api.lookups", f"svc-dashboard looked up project {project.pk}: /api/v2/projects/{project.pk}/notes/"),
        (
            "rest_api.lookups",
            f"svc-dashboard looked up allocation {allocation.pk}: /api/v2/allocations/{allocation.pk}/usage/today/",
        ),
    ]


def test_view_any_person_alone_does_not_open_an_extension(api_client, make_user, smith):
    response = get_as(
        api_client,
        make_user("svc-dashboard", view_any_person=True),
        extension_url("person", "notes", username="smith01"),
    )

    assert response.status_code == 404


def test_ordinary_callers_and_superusers_are_not_logged(api_client, make_user, smith, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_as(api_client, smith, extension_url("person", "notes", username="smith01"))
    get_as(api_client, make_user("root01", superuser=True), extension_url("person", "notes", username="smith01"))

    assert lookups(caplog) == []


# discovery


def test_the_discovery_list_shows_every_extension_by_kind(api_client, smith):
    response = get_as(api_client, smith, reverse("rest_api:v2:extension-list"))

    assert response.status_code == 200
    assert response.json() == {
        "person": [
            {"name": "notes", "description": "A person's notes", "version": 1, "deprecated": False},
            {"name": "old-notes", "description": "A person's notes, the old way", "version": 1, "deprecated": True},
        ],
        "project": [{"name": "notes", "description": "A project's notes", "version": 1, "deprecated": False}],
        "allocation": [{"name": "usage", "description": "An allocation's usage", "version": 2, "deprecated": False}],
    }


def test_the_discovery_list_with_nothing_registered(api_client, smith, monkeypatch):
    monkeypatch.setattr(extensions, "_registry", {})

    response = get_as(api_client, smith, reverse("rest_api:v2:extension-list"))

    assert response.json() == {"person": [], "project": [], "allocation": []}
