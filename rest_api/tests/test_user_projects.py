"""GET /api/v2/users/<username>/projects/: the New and Active projects a person is an Active member or PI of."""

import logging

import pytest
from django.urls import reverse


def projects_url(username, version="v2"):
    return reverse(f"rest_api:{version}:user-projects", kwargs={"username": username})


def get_projects(api_client, caller, username, **params):
    api_client.force_authenticate(caller)
    return api_client.get(projects_url(username), params)


def titles(response):
    return [project["title"] for project in response.json()["results"]]


@pytest.fixture
def smith(make_user):
    return make_user("smith01")


@pytest.fixture
def smiths_project(make_user, make_project, add_member, smith):
    project = make_project(make_user("pi01"), title="Ocean Modelling")
    add_member(project, smith, role="Manager")
    return project


@pytest.mark.parametrize(
    "version, path",
    [
        ("v2", "/api/v2/users/smith01/projects/"),
        ("latest", "/api/latest/users/smith01/projects/"),
        ("unversioned", "/api/users/smith01/projects/"),
    ],
)
def test_the_urls(version, path):
    assert projects_url("smith01", version) == path


@pytest.mark.parametrize("version", ["latest", "unversioned"])
def test_latest_and_unversioned_serve_v2(api_client, smith, smiths_project, version):
    api_client.force_authenticate(smith)

    response = api_client.get(projects_url("smith01", version))

    assert response.status_code == 200
    assert response.json() == api_client.get(projects_url("smith01")).json()


@pytest.mark.parametrize("version", ["v2", "latest", "unversioned"])
def test_the_next_page_stays_on_the_url_asked_for(api_client, make_project, smith, version):
    for title in ["A", "B"]:
        make_project(smith, title=title)
    api_client.force_authenticate(smith)

    response = api_client.get(projects_url("smith01", version), {"page_size": 1})

    assert response.json()["next"] == f"http://testserver{projects_url('smith01', version)}?page=2&page_size=1"


def test_needs_authentication(api_client, smiths_project):
    response = api_client.get(projects_url("smith01"))

    assert response.status_code == 401


def test_is_read_only(api_client, smith, smiths_project):
    api_client.force_authenticate(smith)

    assert api_client.post(projects_url("smith01"), {}).status_code == 405


# What is listed


def test_the_response_shape(api_client, smith, smiths_project, add_project_attribute):
    add_project_attribute(smiths_project, "Project Key", "OCEAN-01")

    response = get_projects(api_client, smith, "smith01")

    assert response.status_code == 200
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": smiths_project.pk,
                "title": "Ocean Modelling",
                "status": "Active",
                "pi": "pi01",
                "membership": {"role": "Manager", "status": "Active"},
                "project_attributes": [{"name": "Project Key", "value": "OCEAN-01", "is_private": False}],
            }
        ],
    }


def test_a_pi_without_a_membership_row(api_client, make_project, smith):
    make_project(smith, title="Smith Lab")

    response = get_projects(api_client, smith, "smith01")

    assert titles(response) == ["Smith Lab"]
    assert response.json()["results"][0]["membership"] is None


def test_a_pi_who_is_also_a_member_is_listed_once(api_client, make_project, add_member, smith):
    project = make_project(smith, title="Smith Lab")
    add_member(project, smith, role="Manager")

    response = get_projects(api_client, smith, "smith01")

    assert titles(response) == ["Smith Lab"]
    assert response.json()["results"][0]["membership"] == {"role": "Manager", "status": "Active"}


def test_new_projects_are_listed_as_in_coldfront(api_client, make_project, add_member, make_user, smith):
    add_member(make_project(make_user("pi01"), title="Member", status="New"), smith)
    make_project(smith, title="PI", status="New")

    response = get_projects(api_client, smith, "smith01")

    assert titles(response) == ["Member", "PI"]
    assert [project["status"] for project in response.json()["results"]] == ["New", "New"]


def test_archived_projects_are_left_out_by_default(api_client, make_project, add_member, make_user, smith):
    add_member(make_project(make_user("pi01"), title="Member", status="Archived"), smith)
    make_project(smith, title="PI", status="Archived")

    assert titles(get_projects(api_client, smith, "smith01")) == []


# Filtering by status


@pytest.fixture
def projects_in_each_status(make_project, add_member, make_user, smith):
    for status in ["New", "Active", "Archived"]:
        add_member(make_project(make_user(f"pi-{status.lower()}"), title=f"{status} project", status=status), smith)


@pytest.mark.parametrize(
    "statuses, expected",
    [
        (["Active"], ["Active project"]),
        (["New"], ["New project"]),
        (["Archived"], ["Archived project"]),
        (["Active", "Archived"], ["Active project", "Archived project"]),
    ],
)
def test_the_status_filter(api_client, smith, projects_in_each_status, statuses, expected):
    assert titles(get_projects(api_client, smith, "smith01", status=statuses)) == expected


def test_archived_projects_a_person_pis(api_client, make_project, smith):
    make_project(smith, title="Old Lab", status="Archived")

    assert titles(get_projects(api_client, smith, "smith01", status="Archived")) == ["Old Lab"]


def test_the_status_filter_doesnt_widen_who_is_listed(api_client, make_project, add_member, make_user, smith):
    add_member(make_project(make_user("pi01"), title="Removed", status="Archived"), smith, status="Removed")
    make_project(make_user("jones01"), title="Jones Lab", status="Archived")

    assert titles(get_projects(api_client, smith, "smith01", status="Archived")) == []


def test_an_unknown_status_is_a_400(api_client, smith, projects_in_each_status):
    response = get_projects(api_client, smith, "smith01", status="Retired")

    assert response.status_code == 400
    assert "status" in response.json()


def test_the_next_page_keeps_the_filter(api_client, make_project, smith):
    for title in ["A", "B"]:
        make_project(smith, title=title, status="Archived")

    response = get_projects(api_client, smith, "smith01", status="Archived", page_size=1)

    assert "status=Archived" in response.json()["next"]


def test_a_removed_member_is_left_out(api_client, make_project, add_member, make_user, smith):
    add_member(make_project(make_user("pi01")), smith, status="Removed")

    assert titles(get_projects(api_client, smith, "smith01")) == []


def test_other_peoples_projects_are_left_out(api_client, make_project, make_user, smiths_project, smith):
    make_project(make_user("jones01"), title="Jones Lab")

    assert titles(get_projects(api_client, smith, "smith01")) == ["Ocean Modelling"]


def test_projects_are_in_title_order(api_client, make_project, smith):
    for title in ["Zebrafish", "Alpha", "Microbes"]:
        make_project(smith, title=title)

    assert titles(get_projects(api_client, smith, "smith01")) == ["Alpha", "Microbes", "Zebrafish"]


# Who can see what


def test_another_users_projects_are_a_404(api_client, make_user, smiths_project):
    response = get_projects(api_client, make_user("jones01"), "smith01")

    assert response.status_code == 404


def test_an_unknown_username_is_the_same_404(api_client, make_user):
    response = get_projects(api_client, make_user("jones01"), "nobody99")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "flags",
    [{"superuser": True}, {"perms": ["project.can_view_all_projects"]}, {"view_any_person": True}],
)
def test_superusers_project_viewers_and_service_accounts_see_anyone(api_client, make_user, smiths_project, flags):
    response = get_projects(api_client, make_user("caller", **flags), "smith01")

    assert response.status_code == 200
    assert titles(response) == ["Ocean Modelling"]


@pytest.mark.parametrize("flags", [{"staff": True}, {"perms": ["allocation.can_view_all_allocations"]}])
def test_staff_and_allocation_viewers_dont_see_other_peoples_projects(api_client, make_user, smiths_project, flags):
    response = get_projects(api_client, make_user("caller", **flags), "smith01")

    assert response.status_code == 404


def test_an_unknown_username_is_a_404_for_superusers_too(api_client, make_user):
    response = get_projects(api_client, make_user("caller", superuser=True), "nobody99")

    assert response.status_code == 404


# Private attributes


@pytest.fixture
def attributes(smiths_project, add_project_attribute):
    add_project_attribute(smiths_project, "Group", "ocean_lab")
    add_project_attribute(smiths_project, "Billing Note", "secret", is_private=True)


def attribute_names(response):
    return [attribute["name"] for attribute in response.json()["results"][0]["project_attributes"]]


@pytest.mark.parametrize("flags", [{"perms": ["project.can_view_all_projects"]}, {"view_any_person": True}])
def test_project_viewers_and_service_accounts_dont_see_private_attributes(api_client, make_user, attributes, flags):
    response = get_projects(api_client, make_user("caller", **flags), "smith01")

    assert attribute_names(response) == ["Group"]


def test_the_person_themselves_doesnt_see_private_attributes(api_client, smith, attributes):
    assert attribute_names(get_projects(api_client, smith, "smith01")) == ["Group"]


def test_superusers_see_private_attributes(api_client, make_user, attributes):
    response = get_projects(api_client, make_user("caller", superuser=True), "smith01")

    assert response.json()["results"][0]["project_attributes"] == [
        {"name": "Billing Note", "value": "secret", "is_private": True},
        {"name": "Group", "value": "ocean_lab", "is_private": False},
    ]


# Logging


def test_a_service_account_lookup_is_logged(api_client, make_user, smiths_project, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_projects(api_client, make_user("svc-dashboard", view_any_person=True), "smith01")

    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        ("rest_api.lookups", "svc-dashboard looked up smith01: /api/v2/users/smith01/projects/")
    ]


def test_a_persons_own_lookup_isnt_logged(api_client, smith, smiths_project, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_projects(api_client, smith, "smith01")

    assert [record for record in caplog.records if record.name == "rest_api.lookups"] == []


@pytest.mark.parametrize("flags", [{"superuser": True}, {"perms": ["project.can_view_all_projects"]}])
def test_superuser_and_project_viewer_lookups_arent_logged(api_client, make_user, smiths_project, caplog, flags):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_projects(api_client, make_user("caller", **flags), "smith01")

    assert [record for record in caplog.records if record.name == "rest_api.lookups"] == []


# Pages and queries


def test_pages(api_client, make_project, smith):
    for title in ["A", "B", "C"]:
        make_project(smith, title=title)

    response = get_projects(api_client, smith, "smith01", page_size=2)

    assert response.json()["count"] == 3
    assert titles(response) == ["A", "B"]
    assert response.json()["next"] is not None


def test_queries_dont_grow_with_projects(
    api_client, make_user, make_project, add_member, add_project_attribute, smith, django_assert_max_num_queries
):
    caller = make_user("svc-dashboard", view_any_person=True)
    for number in range(10):
        project = make_project(make_user(f"pi{number:02}"), title=f"Project {number}")
        add_member(project, smith)
        add_project_attribute(project, "Group", f"group{number}")
        add_project_attribute(project, "Project Key", f"KEY-{number}")

    api_client.force_authenticate(caller)
    with django_assert_max_num_queries(7):
        response = api_client.get(projects_url("smith01"))

    assert response.json()["count"] == 10
