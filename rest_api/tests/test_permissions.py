"""
Who may look up anyone's projects or allocations, and who sees private attributes.

The rules are ColdFront's: superusers, and holders of ColdFront's can_view_all_projects or
can_view_all_allocations for that kind of data. The staff flag alone isn't enough. Service
accounts hold the API's own rest_api.view_any_person, which opens both.
"""

import pytest
from django.contrib.auth.models import Permission

from rest_api.permissions import (
    can_view_all_allocations,
    can_view_all_projects,
    is_service_account,
    sees_private_attributes,
)

VIEW_ALL_PROJECTS = "project.can_view_all_projects"
VIEW_ALL_ALLOCATIONS = "allocation.can_view_all_allocations"


def test_the_view_any_person_permission_exists(db):
    permission = Permission.objects.get(content_type__app_label="rest_api", codename="view_any_person")

    assert permission.name == "Can look up any person through the REST API"


def test_defining_the_permission_creates_no_table(db):
    from django.db import connection

    from rest_api.models import ApiAccess

    assert ApiAccess._meta.managed is False
    assert ApiAccess._meta.db_table not in connection.introspection.table_names()


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, False),
        ({"staff": True}, False),
        ({"perms": [VIEW_ALL_ALLOCATIONS]}, False),
        ({"superuser": True}, True),
        ({"perms": [VIEW_ALL_PROJECTS]}, True),
        ({"view_any_person": True}, True),
    ],
)
def test_can_view_all_projects(make_user, flags, expected):
    assert can_view_all_projects(make_user("caller", **flags)) is expected


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, False),
        ({"staff": True}, False),
        ({"perms": [VIEW_ALL_PROJECTS]}, False),
        ({"superuser": True}, True),
        ({"perms": [VIEW_ALL_ALLOCATIONS]}, True),
        ({"view_any_person": True}, True),
    ],
)
def test_can_view_all_allocations(make_user, flags, expected):
    assert can_view_all_allocations(make_user("caller", **flags)) is expected


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, False),
        ({"superuser": True}, False),
        ({"perms": [VIEW_ALL_PROJECTS, VIEW_ALL_ALLOCATIONS]}, False),
        ({"view_any_person": True}, True),
        ({"view_any_person": True, "staff": True}, True),
    ],
)
def test_service_accounts_are_view_any_person_holders_who_arent_superusers(make_user, flags, expected):
    assert is_service_account(make_user("caller", **flags)) is expected


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, False),
        ({"staff": True}, False),
        ({"view_any_person": True}, False),
        ({"perms": [VIEW_ALL_PROJECTS, VIEW_ALL_ALLOCATIONS]}, False),
        ({"superuser": True}, True),
    ],
)
def test_only_superusers_see_private_attributes(make_user, flags, expected):
    assert sees_private_attributes(make_user("caller", **flags)) is expected
