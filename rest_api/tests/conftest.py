import pytest
from django.contrib.auth.models import Permission, User
from rest_framework.test import APIClient

from coldfront.core.test_helpers.factories import (
    FieldOfScienceFactory,
    PAttributeTypeFactory,
    ProjectAttributeFactory,
    ProjectAttributeTypeFactory,
    ProjectFactory,
    ProjectStatusChoiceFactory,
    ProjectUserFactory,
    ProjectUserRoleChoiceFactory,
    ProjectUserStatusChoiceFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def make_user(db):
    """A user by username; staff, superuser or holding view_any_person as asked."""

    def _make(username, *, staff=False, superuser=False, view_any_person=False):
        user = User.objects.create_user(username, f"{username}@example.com", "secret")
        user.is_staff = staff
        user.is_superuser = superuser
        user.save()
        if view_any_person:
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label="rest_api", codename="view_any_person")
            )
            # has_perm caches a user's permissions on first use, so hand back a fresh copy
            user = User.objects.get(pk=user.pk)
        return user

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
