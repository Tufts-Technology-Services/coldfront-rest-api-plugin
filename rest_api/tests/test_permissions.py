"""Who may look up anyone, and who sees private attributes."""

import pytest
from django.contrib.auth.models import Permission, User

from rest_api.permissions import can_view_any_person, sees_private_attributes


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
        ({"staff": True}, True),
        ({"superuser": True}, True),
        ({"view_any_person": True}, True),
    ],
)
def test_can_view_any_person(make_user, flags, expected):
    assert can_view_any_person(make_user("caller", **flags)) is expected


def test_coldfronts_view_all_permissions_dont_count(make_user):
    user = make_user("browser")
    user.user_permissions.add(
        Permission.objects.get(codename="can_view_all_projects"),
        Permission.objects.get(codename="can_view_all_allocations"),
    )

    assert can_view_any_person(User.objects.get(pk=user.pk)) is False


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, False),
        ({"staff": True}, False),
        ({"view_any_person": True}, False),
        ({"superuser": True}, True),
    ],
)
def test_only_superusers_see_private_attributes(make_user, flags, expected):
    assert sees_private_attributes(make_user("caller", **flags)) is expected
