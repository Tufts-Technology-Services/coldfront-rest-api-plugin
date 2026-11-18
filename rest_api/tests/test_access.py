"""
Who may use the API at all: holders of rest_api.use_api, which the rest_api_users group carries,
and superusers. Everyone else gets a 403 from every API route, even with a token, and from the
token page, and sees no token row on their profile.
"""

import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import URLPattern, URLResolver, reverse
from rest_framework.authtoken.models import Token
from rest_framework.views import APIView

from rest_api import urls as api_urls
from rest_api.permissions import API_USERS_GROUP, USE_API, CanUseApi, can_use_api

# every API route, with arguments; a refusal comes before any lookup, so none of these need exist
API_ROUTES = [
    ("user-projects", {"username": "smith01"}),
    ("user-projects", {"username": "someone"}),
    ("allocation-list", {}),
    ("allocation-detail", {"pk": 1}),
    ("extension-list", {}),
    ("person-extension", {"username": "smith01", "name": "notes"}),
    ("person-extension-item", {"username": "smith01", "name": "notes", "key": "a"}),
    ("project-extension", {"pk": 1, "name": "notes"}),
    ("project-extension-item", {"pk": 1, "name": "notes", "key": "a"}),
    ("allocation-extension", {"pk": 1, "name": "notes"}),
    ("allocation-extension-item", {"pk": 1, "name": "notes", "key": "a"}),
]


# The permission and the group


def test_the_use_api_permission_exists(db):
    permission = Permission.objects.get(content_type__app_label="rest_api", codename="use_api")

    assert permission.name == "Can use the REST API"
    assert USE_API == "rest_api.use_api"


def test_the_group_carries_only_that_permission(db):
    group = Group.objects.get(name="rest_api_users")

    assert API_USERS_GROUP == "rest_api_users"
    assert [f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()] == [USE_API]


@pytest.mark.parametrize(
    "flags, expected",
    [
        ({}, True),
        ({"api_user": False}, False),
        ({"api_user": False, "superuser": True}, True),
        ({"api_user": False, "staff": True}, False),
        ({"api_user": False, "view_any_person": True}, False),
        ({"api_user": False, "perms": ["rest_api.use_api"]}, True),
    ],
)
def test_can_use_api(make_user, flags, expected):
    assert can_use_api(make_user("smith01", **flags)) is expected


def test_an_inactive_member_cannot(make_user):
    user = make_user("smith01")
    user.is_active = False

    assert can_use_api(user) is False


# The API's routes


def every_view_class(patterns):
    """The view class behind each route in a URLconf's patterns, included ones too."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from every_view_class(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern.callback.view_class


def test_every_api_view_requires_use_api():
    """So a route added later can't forget the check."""
    view_classes = [view for view in every_view_class(api_urls.urlpatterns) if issubclass(view, APIView)]

    assert view_classes
    for view_class in view_classes:
        assert CanUseApi in view_class.permission_classes, view_class.__name__


@pytest.mark.parametrize("prefix", ["v2", "latest", "unversioned"])
@pytest.mark.parametrize("name, kwargs", API_ROUTES)
def test_a_token_without_use_api_gets_a_403(api_client, make_user, prefix, name, kwargs):
    token = Token.objects.create(user=make_user("smith01", api_user=False))
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = api_client.get(reverse(f"rest_api:{prefix}:{name}", kwargs=kwargs))

    assert response.status_code == 403
    assert response.json() == {"detail": "Your account doesn't have access to the REST API."}


def test_a_signed_in_session_without_use_api_gets_a_403(client, make_user):
    client.force_login(make_user("smith01", api_user=False))

    assert client.get(reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"})).status_code == 403


def test_a_service_account_needs_use_api_as_well(api_client, make_user):
    api_client.force_authenticate(make_user("svc01", api_user=False, view_any_person=True))

    assert api_client.get(reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"})).status_code == 403


def test_a_member_of_the_group_gets_in(api_client, make_user):
    token = Token.objects.create(user=make_user("smith01"))
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    assert api_client.get(reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"})).status_code == 200


def test_a_superuser_gets_in_without_the_group(api_client, make_user):
    api_client.force_authenticate(make_user("root01", superuser=True, api_user=False))

    assert api_client.get(reverse("rest_api:v2:allocation-list")).status_code == 200


def test_leaving_the_group_shuts_out_an_existing_token(api_client, make_user):
    user = make_user("smith01")
    token = Token.objects.create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    url = reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"})
    assert api_client.get(url).status_code == 200

    user.groups.clear()

    assert api_client.get(url).status_code == 403


def test_no_credentials_is_still_a_401(api_client, db):
    assert api_client.get(reverse("rest_api:v2:allocation-list")).status_code == 401


# The token page


@pytest.fixture
def outsider_signed_in(client, make_user):
    client.force_login(make_user("smith01", api_user=False))
    return client


def test_the_token_page_is_a_403_without_use_api(outsider_signed_in):
    assert outsider_signed_in.get(reverse("rest_api:token")).status_code == 403


def test_creating_a_token_is_a_403_without_use_api(outsider_signed_in):
    response = outsider_signed_in.post(reverse("rest_api:token-regenerate"))

    assert response.status_code == 403
    assert not Token.objects.exists()


def test_revoking_is_a_403_without_use_api(outsider_signed_in, make_user):
    token = Token.objects.create(user=make_user("jones01", api_user=False))

    assert outsider_signed_in.post(reverse("rest_api:token-revoke")).status_code == 403
    assert Token.objects.filter(pk=token.pk).exists()


def test_a_superuser_gets_the_token_page_without_the_group(client, make_user):
    client.force_login(make_user("root01", superuser=True, api_user=False))

    assert client.get(reverse("rest_api:token")).status_code == 200


def test_no_profile_row_without_use_api(make_user, render_profile_row):
    smith = make_user("smith01", api_user=False)

    assert render_profile_row(smith, smith) == ""
