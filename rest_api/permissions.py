"""
Who may look up anyone, and who sees private attributes. See docs/rest-api-plan.md, "Who can see
what".

The rules are ColdFront's own. Seeing everyone's projects takes superuser or ColdFront's
can_view_all_projects, and everyone's allocations superuser or can_view_all_allocations; the
staff flag alone isn't enough. Service accounts hold the API's own rest_api.view_any_person,
which opens both without opening ColdFront's web pages.
"""

VIEW_ANY_PERSON = "rest_api.view_any_person"
VIEW_ALL_PROJECTS = "project.can_view_all_projects"
VIEW_ALL_ALLOCATIONS = "allocation.can_view_all_allocations"


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
