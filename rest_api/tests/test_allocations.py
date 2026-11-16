"""
GET /api/v2/allocations/ and /api/v2/allocations/<id>/: allocations, by ColdFront's rules.

The list shows what ColdFront's allocation list would show the caller; the single allocation
follows ColdFront's allocation page. See docs/rest-api-plan.md.
"""

import datetime
import logging

import pytest
from django.urls import reverse

VIEW_ALL_ALLOCATIONS = "allocation.can_view_all_allocations"


def list_url(version="v2"):
    return reverse(f"rest_api:{version}:allocation-list")


def detail_url(pk, version="v2"):
    return reverse(f"rest_api:{version}:allocation-detail", kwargs={"pk": pk})


def get_list(api_client, caller, **params):
    api_client.force_authenticate(caller)
    return api_client.get(list_url(), params)


def get_detail(api_client, caller, allocation):
    api_client.force_authenticate(caller)
    return api_client.get(detail_url(allocation.pk))


def listed_ids(response):
    assert response.status_code == 200, response.content
    return [allocation["id"] for allocation in response.json()["results"]]


@pytest.fixture
def pi(make_user):
    return make_user("pi01")


@pytest.fixture
def smith(make_user):
    return make_user("smith01")


@pytest.fixture
def project(make_project, add_member, pi):
    """Ocean Modelling: pi01 is its PI, with the Manager row ColdFront gives a PI."""
    project = make_project(pi, title="Ocean Modelling")
    add_member(project, pi, role="Manager")
    return project


@pytest.fixture
def allocation(make_allocation, project):
    return make_allocation(project)


@pytest.fixture
def other_allocation(make_allocation, make_project, make_user):
    """An allocation on someone else's project that smith01 has nothing to do with."""
    return make_allocation(make_project(make_user("jones01"), title="Jones Lab"), resources=["Tier 1 HPC"])


@pytest.mark.parametrize(
    "version, list_path, detail_path",
    [
        ("v2", "/api/v2/allocations/", "/api/v2/allocations/7/"),
        ("latest", "/api/latest/allocations/", "/api/latest/allocations/7/"),
        ("unversioned", "/api/allocations/", "/api/allocations/7/"),
    ],
)
def test_the_urls(version, list_path, detail_path):
    assert list_url(version) == list_path
    assert detail_url(7, version) == detail_path


def test_needs_authentication(api_client, allocation):
    assert api_client.get(list_url()).status_code == 401
    assert api_client.get(detail_url(allocation.pk)).status_code == 401


def test_is_read_only(api_client, pi, allocation):
    api_client.force_authenticate(pi)

    assert api_client.post(list_url(), {}).status_code == 405
    assert api_client.delete(detail_url(allocation.pk)).status_code == 405


# The shape


def test_the_response_shape(api_client, make_allocation, add_allocation_attribute, project, pi):
    allocation = make_allocation(
        project,
        resources=["Tier 2 Storage"],
        start_date=datetime.date(2026, 1, 15),
        end_date=datetime.date(2027, 1, 15),
    )
    add_allocation_attribute(allocation, "Storage Quota (TB)", "10", usage=6.2)
    add_allocation_attribute(allocation, "Group", "ocean_lab")
    expected = {
        "id": allocation.pk,
        "project": {"id": project.pk, "title": "Ocean Modelling", "pi": "pi01"},
        "status": "Active",
        "resources": [{"name": "Tier 2 Storage", "resource_type": "Storage"}],
        "start_date": "2026-01-15",
        "end_date": "2027-01-15",
        "allocation_attributes": [
            {"name": "Group", "value": "ocean_lab", "usage": None, "is_private": False},
            {"name": "Storage Quota (TB)", "value": "10", "usage": 6.2, "is_private": False},
        ],
    }

    listed = get_list(api_client, pi)
    single = get_detail(api_client, pi, allocation)

    assert listed.json() == {"count": 1, "next": None, "previous": None, "results": [expected]}
    assert single.status_code == 200
    assert single.json() == expected


def test_listed_in_id_order(api_client, make_allocation, project, pi):
    allocations = [make_allocation(project) for _ in range(3)]

    assert listed_ids(get_list(api_client, pi)) == [allocation.pk for allocation in allocations]


@pytest.mark.parametrize("status", ["Active", "Expired", "Denied"])
def test_every_allocation_status_is_listed(api_client, make_allocation, project, pi, status):
    allocation = make_allocation(project, status=status)

    assert listed_ids(get_list(api_client, pi)) == [allocation.pk]


# The list, for someone who can't see all allocations: ColdFront's allocation list rule


@pytest.mark.parametrize("status", ["Active", "PendingEULA"])
def test_an_allocation_user_sees_it(api_client, add_member, add_allocation_user, project, allocation, smith, status):
    add_member(project, smith)
    add_allocation_user(allocation, smith, status=status)

    assert listed_ids(get_list(api_client, smith)) == [allocation.pk]


@pytest.mark.parametrize("status", ["Removed", "New"])
def test_an_allocation_user_in_another_status_doesnt(
    api_client, add_member, add_allocation_user, project, allocation, smith, status
):
    add_member(project, smith)
    add_allocation_user(allocation, smith, status=status)

    assert listed_ids(get_list(api_client, smith)) == []


def test_a_project_member_not_on_the_allocation_doesnt(api_client, add_member, project, allocation, smith):
    add_member(project, smith)

    assert listed_ids(get_list(api_client, smith)) == []


def test_a_manager_sees_all_the_projects_allocations(api_client, make_allocation, add_member, project, smith):
    add_member(project, smith, role="Manager")
    allocations = [make_allocation(project), make_allocation(project)]

    assert listed_ids(get_list(api_client, smith)) == [allocation.pk for allocation in allocations]


def test_the_pi_sees_all_the_projects_allocations(api_client, make_allocation, project, pi):
    allocations = [make_allocation(project), make_allocation(project)]

    assert listed_ids(get_list(api_client, pi)) == [allocation.pk for allocation in allocations]


@pytest.mark.parametrize("status", ["Removed", "New"])
def test_an_allocation_user_needs_an_active_project_membership(
    api_client, add_member, add_allocation_user, project, allocation, smith, status
):
    add_member(project, smith, status=status)
    add_allocation_user(allocation, smith)

    assert listed_ids(get_list(api_client, smith)) == []


def test_a_manager_row_that_isnt_active_doesnt_count(api_client, add_member, project, allocation, smith):
    add_member(project, smith, role="Manager", status="Removed")

    assert listed_ids(get_list(api_client, smith)) == []


@pytest.mark.parametrize("status, listed", [("New", True), ("Active", True), ("Archived", False)])
def test_project_status(api_client, make_project, make_allocation, add_member, pi, status, listed):
    project = make_project(pi, title="Lab", status=status)
    add_member(project, pi, role="Manager")
    allocation = make_allocation(project)

    assert listed_ids(get_list(api_client, pi)) == ([allocation.pk] if listed else [])


def test_other_peoples_allocations_arent_listed(api_client, allocation, other_allocation, pi):
    assert listed_ids(get_list(api_client, pi)) == [allocation.pk]


# The list, for those who can see all allocations


@pytest.mark.parametrize("flags", [{"superuser": True}, {"perms": [VIEW_ALL_ALLOCATIONS]}, {"view_any_person": True}])
def test_seeing_all_allocations(
    api_client, make_user, make_project, make_allocation, allocation, other_allocation, flags
):
    archived = make_allocation(make_project(make_user("old01"), title="Old Lab", status="Archived"))

    response = get_list(api_client, make_user("caller", **flags))

    assert listed_ids(response) == [allocation.pk, other_allocation.pk, archived.pk]


@pytest.mark.parametrize("flags", [{"staff": True}, {"perms": ["project.can_view_all_projects"]}])
def test_staff_and_project_viewers_see_only_their_own(api_client, make_user, allocation, other_allocation, flags):
    assert listed_ids(get_list(api_client, make_user("caller", **flags))) == []


# A single allocation: ColdFront's allocation page rule


@pytest.mark.parametrize("status", ["Active", "New", "PendingEULA"])
def test_an_allocation_user_can_open_it(
    api_client, add_member, add_allocation_user, project, allocation, smith, status
):
    add_member(project, smith)
    add_allocation_user(allocation, smith, status=status)

    assert get_detail(api_client, smith, allocation).status_code == 200


def test_a_new_project_member_on_the_allocation_can_open_it(
    api_client, add_member, add_allocation_user, project, allocation, smith
):
    add_member(project, smith, status="New")
    add_allocation_user(allocation, smith)

    assert get_detail(api_client, smith, allocation).status_code == 200


def test_a_member_can_open_it_on_an_archived_project(api_client, make_project, make_allocation, add_member, pi):
    project = make_project(pi, title="Old Lab", status="Archived")
    add_member(project, pi, role="Manager")
    allocation = make_allocation(project)

    assert get_detail(api_client, pi, allocation).status_code == 200


def test_a_manager_can_open_any_of_the_projects_allocations(api_client, add_member, project, allocation, smith):
    add_member(project, smith, role="Manager")

    assert get_detail(api_client, smith, allocation).status_code == 200


def test_a_project_member_not_on_it_gets_a_404(api_client, add_member, project, allocation, smith):
    add_member(project, smith)

    assert get_detail(api_client, smith, allocation).status_code == 404


def test_someone_elses_allocation_is_a_404(api_client, other_allocation, smith):
    assert get_detail(api_client, smith, other_allocation).status_code == 404


def test_an_allocation_that_doesnt_exist_is_the_same_404(api_client, smith, db):
    api_client.force_authenticate(smith)

    assert api_client.get(detail_url(999999)).status_code == 404


@pytest.mark.parametrize("flags", [{"superuser": True}, {"perms": [VIEW_ALL_ALLOCATIONS]}, {"view_any_person": True}])
def test_those_who_see_all_can_open_any(api_client, make_user, other_allocation, flags):
    assert get_detail(api_client, make_user("caller", **flags), other_allocation).status_code == 200


@pytest.mark.parametrize("flags", [{"staff": True}, {"perms": ["project.can_view_all_projects"]}])
def test_staff_and_project_viewers_get_a_404(api_client, make_user, other_allocation, flags):
    assert get_detail(api_client, make_user("caller", **flags), other_allocation).status_code == 404


# Private attributes


@pytest.fixture
def attributes(allocation, add_allocation_attribute):
    add_allocation_attribute(allocation, "Group", "ocean_lab")
    add_allocation_attribute(allocation, "Billing Note", "secret", is_private=True)


def attribute_names(response):
    return [attribute["name"] for attribute in response.json()["results"][0]["allocation_attributes"]]


@pytest.mark.parametrize("flags", [{"perms": [VIEW_ALL_ALLOCATIONS]}, {"view_any_person": True}, {"staff": True}])
def test_only_superusers_see_private_attributes(api_client, make_user, add_member, project, attributes, flags):
    caller = make_user("caller", **flags)
    add_member(project, caller, role="Manager")

    assert attribute_names(get_list(api_client, caller)) == ["Group"]


def test_the_pi_doesnt_see_private_attributes(api_client, pi, attributes):
    assert attribute_names(get_list(api_client, pi)) == ["Group"]


def test_superusers_see_private_attributes(api_client, make_user, allocation, attributes):
    caller = make_user("caller", superuser=True)

    assert attribute_names(get_list(api_client, caller)) == ["Billing Note", "Group"]
    assert [a["is_private"] for a in get_detail(api_client, caller, allocation).json()["allocation_attributes"]] == [
        True,
        False,
    ]


def test_a_single_allocation_hides_private_attributes_too(api_client, pi, allocation, attributes):
    response = get_detail(api_client, pi, allocation)

    assert [attribute["name"] for attribute in response.json()["allocation_attributes"]] == ["Group"]


# Filters


@pytest.fixture
def superuser(make_user):
    return make_user("admin", superuser=True)


@pytest.fixture
def spread(make_allocation, make_project, make_user, make_resource):
    """Allocations across resources and resource types (Storage and Cluster), keyed by a short name."""
    make_resource("HPC Cluster", resource_type="Cluster")
    make_resource("GPU Nodes", resource_type="Cluster")
    project = make_project(make_user("pi02"), title="Spread")
    return {
        "tier2": make_allocation(project, resources=["Tier 2 Storage"]),
        "tier1": make_allocation(project, resources=["Tier 1 RStore"]),
        "hpc": make_allocation(project, resources=["HPC Cluster"]),
        "gpu": make_allocation(make_project(make_user("pi03"), title="GPUs"), resources=["GPU Nodes"]),
    }


def ids_of(spread, *names):
    return [spread[name].pk for name in names]


def test_resource_type_matches_partially_and_ignores_case(api_client, superuser, spread):
    response = get_list(api_client, superuser, resource_type="STOR")

    assert listed_ids(response) == ids_of(spread, "tier2", "tier1")


def test_resource_matches_partially_and_ignores_case(api_client, superuser, spread):
    assert listed_ids(get_list(api_client, superuser, resource="tier 2")) == ids_of(spread, "tier2")


def test_a_repeated_filter_matches_any_value(api_client, superuser, spread):
    response = get_list(api_client, superuser, resource=["tier 2", "gpu"])

    assert listed_ids(response) == ids_of(spread, "tier2", "gpu")


def test_an_allocation_with_two_matching_resources_is_listed_once(api_client, superuser, make_allocation, project):
    allocation = make_allocation(project, resources=["Tier 2 Storage", "Tier 2 Backup Storage"])

    assert listed_ids(get_list(api_client, superuser, resource="tier 2")) == [allocation.pk]


def test_status(api_client, superuser, make_allocation, project):
    active = make_allocation(project)
    expired = make_allocation(project, status="Expired")
    make_allocation(project, status="Denied")

    assert listed_ids(get_list(api_client, superuser, status="Active")) == [active.pk]
    assert listed_ids(get_list(api_client, superuser, status=["Active", "Expired"])) == [active.pk, expired.pk]


def test_an_unknown_status_is_a_400(api_client, superuser, allocation):
    response = get_list(api_client, superuser, status="Retired")

    assert response.status_code == 400
    assert "status" in response.json()


def test_project(api_client, superuser, allocation, other_allocation):
    assert listed_ids(get_list(api_client, superuser, project=allocation.project_id)) == [allocation.pk]
    assert listed_ids(
        get_list(api_client, superuser, project=[allocation.project_id, other_allocation.project_id])
    ) == [allocation.pk, other_allocation.pk]


def test_a_project_that_isnt_a_number_is_a_400(api_client, superuser, allocation):
    response = get_list(api_client, superuser, project="ocean")

    assert response.status_code == 400
    assert "project" in response.json()


def test_username_matches_allocation_users_and_the_pi(
    api_client, superuser, make_allocation, make_project, add_allocation_user, allocation, other_allocation, smith
):
    smiths_own = make_allocation(make_project(smith, title="Smith Lab"))
    add_allocation_user(other_allocation, smith)

    response = get_list(api_client, superuser, username="smith01")

    assert listed_ids(response) == [other_allocation.pk, smiths_own.pk]


@pytest.mark.parametrize("status", ["Removed", "PendingEULA"])
def test_username_needs_an_active_allocation_user(
    api_client, superuser, add_allocation_user, other_allocation, smith, status
):
    add_allocation_user(other_allocation, smith, status=status)

    assert listed_ids(get_list(api_client, superuser, username="smith01")) == []


def test_filters_only_narrow_what_the_caller_sees(api_client, add_allocation_user, other_allocation, pi, smith):
    add_allocation_user(other_allocation, smith)

    assert listed_ids(get_list(api_client, pi, username="smith01")) == []


def test_filters_combine(api_client, superuser, spread):
    response = get_list(api_client, superuser, resource_type="storage", resource="tier 1")

    assert listed_ids(response) == ids_of(spread, "tier1")


def test_the_next_page_keeps_the_filters(api_client, superuser, spread):
    response = get_list(api_client, superuser, resource_type="storage", page_size=1)

    assert "resource_type=storage" in response.json()["next"]


# Logging


def test_a_service_accounts_list_is_logged(api_client, make_user, allocation, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_list(api_client, make_user("svc-dashboard", view_any_person=True), username="smith01")

    assert [(record.name, record.getMessage()) for record in caplog.records] == [
        ("rest_api.lookups", "svc-dashboard looked up allocations: /api/v2/allocations/?username=smith01")
    ]


def test_a_service_accounts_single_allocation_is_logged(api_client, make_user, allocation, caplog):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")

    get_detail(api_client, make_user("svc-dashboard", view_any_person=True), allocation)

    assert [record.getMessage() for record in caplog.records if record.name == "rest_api.lookups"] == [
        f"svc-dashboard looked up allocation {allocation.pk}: /api/v2/allocations/{allocation.pk}/"
    ]


@pytest.mark.parametrize("flags", [{}, {"superuser": True}, {"perms": [VIEW_ALL_ALLOCATIONS]}])
def test_other_callers_arent_logged(api_client, make_user, allocation, caplog, flags):
    caplog.set_level(logging.INFO, logger="rest_api.lookups")
    caller = make_user("caller", **flags)

    get_list(api_client, caller)
    get_detail(api_client, caller, allocation)

    assert [record for record in caplog.records if record.name == "rest_api.lookups"] == []


# Pages and queries


def test_pages(api_client, superuser, make_allocation, project):
    for _ in range(3):
        make_allocation(project)

    response = get_list(api_client, superuser, page_size=2)

    assert response.json()["count"] == 3
    assert len(response.json()["results"]) == 2
    assert response.json()["next"] is not None


@pytest.mark.parametrize("flags", [{"superuser": True}, {}])
def test_queries_dont_grow_with_allocations(
    api_client,
    make_user,
    make_project,
    make_allocation,
    add_member,
    add_allocation_user,
    add_allocation_attribute,
    django_assert_max_num_queries,
    flags,
):
    caller = make_user("caller", **flags)
    for number in range(10):
        project = make_project(make_user(f"pi{number:02}"), title=f"Project {number}")
        add_member(project, caller)
        allocation = make_allocation(project, resources=[f"Resource {number}", "Shared Storage"])
        add_allocation_user(allocation, caller)
        add_allocation_attribute(allocation, "Group", f"group{number}")
        add_allocation_attribute(allocation, "Storage Quota (TB)", "10", usage=number)

    api_client.force_authenticate(caller)
    with django_assert_max_num_queries(8):
        response = api_client.get(list_url())

    assert response.json()["count"] == 10
