"""Who may look up anyone, and who sees private attributes. See docs/rest-api-plan.md, "Who can see what"."""

VIEW_ANY_PERSON = "rest_api.view_any_person"


def can_view_any_person(user):
    """Staff, superusers and holders of rest_api.view_any_person may ask about anyone."""
    return user.is_staff or user.is_superuser or user.has_perm(VIEW_ANY_PERSON)


def is_service_account(user):
    """A caller who may ask about anyone only through view_any_person, whose lookups are logged."""
    return not (user.is_staff or user.is_superuser) and user.has_perm(VIEW_ANY_PERSON)


def sees_private_attributes(user):
    """Only superusers see private attributes, as on ColdFront's web pages."""
    return user.is_superuser
