import pytest
from django.contrib.auth.models import Permission, User
from rest_framework.test import APIClient

from coldfront.core.test_helpers.factories import (
    AAttributeTypeFactory,
    AllocationAttributeFactory,
    AllocationAttributeTypeFactory,
    AllocationAttributeUsageFactory,
    AllocationFactory,
    AllocationStatusChoiceFactory,
    AllocationUserFactory,
    AllocationUserStatusChoiceFactory,
    FieldOfScienceFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectAttributeTypeFactory,
    ProjectFactory,
    ProjectStatusChoiceFactory,
    ProjectUserFactory,
    ProjectUserRoleChoiceFactory,
    ProjectUserStatusChoiceFactory,
    ResourceFactory,
    ResourceTypeFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    """
    A user by username; staff or superuser as asked, holding view_any_person if asked, and any
    other permissions named "app_label.codename" in perms (ColdFront's can_view_all_*, say).
    """

    def _make(username, *, staff=False, superuser=False, view_any_person=False, perms=()):
        user = User.objects.create_user(username, f"{username}@example.com", "secret")
        user.is_staff = staff
        user.is_superuser = superuser
        user.save()
        names = list(perms) + (["rest_api.view_any_person"] if view_any_person else [])
        for name in names:
            app_label, codename = name.split(".")
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        # has_perm caches a user's permissions on first use, so hand back a fresh copy
        return User.objects.get(pk=user.pk) if names else user

    return _make


@pytest.fixture
def make_project(db):
    """A project with the given PI, in the named status (Active unless given)."""

    def _make(pi, title="Ocean Modelling", status="Active"):
        return ProjectFactory(
            pi=pi,
            title=title,
            status=ProjectStatusChoiceFactory(name=status),
            field_of_science=FieldOfScienceFactory(description="Other"),
        )

    return _make


@pytest.fixture
def add_member(db):
    """Put a user on a project, with the named role and membership status."""

    def _add(project, user, role="User", status="Active"):
        return ProjectUserFactory(
            project=project,
            user=user,
            role=ProjectUserRoleChoiceFactory(name=role),
            status=ProjectUserStatusChoiceFactory(name=status),
        )

    return _add


@pytest.fixture
def add_project_attribute(db):
    """Give a project an attribute, creating its type (public unless is_private) if needed."""

    def _add(project, name, value, is_private=False):
        attribute_type = ProjectAttributeTypeFactory(
            name=name, attribute_type=PAttributeTypeFactory(name="Text"), is_private=is_private
        )
        return ProjectAttributeFactory(project=project, proj_attr_type=attribute_type, value=value)

    return _add


@pytest.fixture
def make_resource(db):
    """A resource by name, of the named resource type (Storage unless given)."""

    def _make(name, resource_type="Storage"):
        return ResourceFactory(name=name, resource_type=ResourceTypeFactory(name=resource_type))

    return _make


@pytest.fixture
def make_allocation(db, make_resource):
    """An allocation on a project, of the named resources, in the named status (Active unless given)."""

    def _make(project, resources=("Tier 2 Storage",), status="Active", start_date=None, end_date=None):
        allocation = AllocationFactory(
            project=project,
            status=AllocationStatusChoiceFactory(name=status),
            start_date=start_date,
            end_date=end_date,
        )
        allocation.resources.set([make_resource(name) for name in resources])
        return allocation

    return _make


@pytest.fixture
def add_allocation_user(db):
    """Put a user on an allocation, with the named status (Active unless given)."""

    def _add(allocation, user, status="Active"):
        return AllocationUserFactory(
            allocation=allocation, user=user, status=AllocationUserStatusChoiceFactory(name=status)
        )

    return _add


@pytest.fixture
def add_allocation_attribute(db):
    """Give an allocation an attribute, creating its type (public unless is_private) if needed, and its usage if given."""

    def _add(allocation, name, value, is_private=False, usage=None):
        attribute_type = AllocationAttributeTypeFactory(
            name=name, attribute_type=AAttributeTypeFactory(name="Text"), is_private=is_private
        )
        attribute = AllocationAttributeFactory(
            allocation=allocation, allocation_attribute_type=attribute_type, value=value
        )
        if usage is not None:
            AllocationAttributeUsageFactory(allocation_attribute=attribute, value=usage)
        return attribute

    return _add
