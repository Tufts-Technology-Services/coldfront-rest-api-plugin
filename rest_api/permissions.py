"""
Who may look up anyone, and who sees private attributes. See docs/rest-api-plan.md, "Who can see
what".

The rules are ColdFront's own. Seeing everyone's projects takes superuser or ColdFront's
can_view_all_projects, and everyone's allocations superuser or can_view_all_allocations; the
staff flag alone isn't enough. Service accounts hold the API's own rest_api.view_any_person,
which opens both without opening ColdFront's web pages.

Before any of that, a caller needs the API's rest_api.use_api, which the rest_api_users group
carries; superusers have it anyway. Without it, every API route and the token page refuse them,
even with a token.
"""

from rest_framework.permissions import BasePermission

USE_API = "rest_api.use_api"
# made by migration 0002 with use_api; admins add people to it
API_USERS_GROUP = "rest_api_users"
VIEW_ANY_PERSON = "rest_api.view_any_person"
VIEW_ALL_PROJECTS = "project.can_view_all_projects"
VIEW_ALL_ALLOCATIONS = "allocation.can_view_all_allocations"


def can_use_api(user):
    """Whether this person may use the API at all: holders of use_api (members of rest_api_users) and superusers."""
    # has_perm is True for any active superuser, and False for anyone inactive
    return user.has_perm(USE_API)


class CanUseApi(BasePermission):
    """DRF's check for every API view: signed in, by token or session, and allowed to use the API."""

    message = "Your account doesn't have access to the REST API."

    def has_permission(self, request, view):
        # signed in first: without it, DRF answers 401 (no credentials), not this 403
        return bool(request.user and request.user.is_authenticated and can_use_api(request.user))


def can_view_all_projects(user):
    """Superusers, holders of ColdFront's can_view_all_projects, and service accounts."""
    return user.is_superuser or user.has_perm(VIEW_ALL_PROJECTS) or user.has_perm(VIEW_ANY_PERSON)


def can_view_all_allocations(user):
    """Superusers, holders of ColdFront's can_view_all_allocations, and service accounts."""
    return user.is_superuser or user.has_perm(VIEW_ALL_ALLOCATIONS) or user.has_perm(VIEW_ANY_PERSON)


def is_service_account(user):
    """A caller who sees everyone through view_any_person rather than as a superuser; their lookups are logged."""
    return not user.is_superuser and user.has_perm(VIEW_ANY_PERSON)


def sees_private_attributes(user):
    """Only superusers see private attributes, as on ColdFront's web pages."""
    return user.is_superuser
