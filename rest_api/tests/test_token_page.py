"""The API token page, /api/token/: a signed-in person creates, replaces or revokes their own token."""

import logging

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework.authtoken.models import Token

KEY = "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
ENDING = KEY[-6:]


@pytest.fixture
def smith(make_user):
    return make_user("smith01")


@pytest.fixture
def signed_in(client, smith):
    client.force_login(smith)
    return client


def page_text(response):
    return response.content.decode()


def test_the_urls():
    assert reverse("rest_api:token") == "/api/token/"
    assert reverse("rest_api:token-regenerate") == "/api/token/regenerate/"
    assert reverse("rest_api:token-revoke") == "/api/token/revoke/"


@pytest.mark.parametrize("name, method", [("token", "get"), ("token-regenerate", "post"), ("token-revoke", "post")])
def test_needs_signing_in(client, db, name, method):
    response = getattr(client, method)(reverse(f"rest_api:{name}"))

    assert response.status_code == 302
    assert "login" in response["Location"]


@pytest.mark.parametrize("name", ["token-regenerate", "token-revoke"])
def test_changes_are_post_only(signed_in, name):
    assert signed_in.get(reverse(f"rest_api:{name}")).status_code == 405


@pytest.mark.parametrize("name", ["token-regenerate", "token-revoke"])
def test_changes_need_the_csrf_token(smith, name):
    client = Client(enforce_csrf_checks=True)
    client.force_login(smith)

    assert client.post(reverse(f"rest_api:{name}")).status_code == 403


# The page


def test_without_a_token(signed_in):
    response = signed_in.get(reverse("rest_api:token"))

    assert response.status_code == 200
    text = page_text(response)
    assert "You don't have an API token." in text
    assert f'action="{reverse("rest_api:token-regenerate")}"' in text
    assert "Create token" in text
    assert "Revoke token" not in text


def test_with_a_token_shows_only_its_end(signed_in, smith):
    Token.objects.create(user=smith, key=KEY)

    text = page_text(signed_in.get(reverse("rest_api:token")))

    assert f"<code>{ENDING}</code>" in text
    assert KEY not in text
    assert "Regenerate token" in text
    assert f'action="{reverse("rest_api:token-revoke")}"' in text


def test_shows_how_to_call_the_api(signed_in):
    text = page_text(signed_in.get(reverse("rest_api:token")))

    assert "http://testserver/api/v2/users/smith01/projects/" in text


# Creating and replacing


def test_creating_a_token(signed_in, smith):
    response = signed_in.post(reverse("rest_api:token-regenerate"))

    assert response.status_code == 302
    assert response["Location"] == reverse("rest_api:token")
    assert Token.objects.filter(user=smith).count() == 1


def test_the_new_token_is_shown_once(signed_in, smith):
    signed_in.post(reverse("rest_api:token-regenerate"))
    key = Token.objects.get(user=smith).key

    first = page_text(signed_in.get(reverse("rest_api:token")))
    second = page_text(signed_in.get(reverse("rest_api:token")))

    assert key in first
    assert "it won't be shown again" in first
    assert key not in second
    assert f"<code>{key[-6:]}</code>" in second


def test_regenerating_replaces_the_old_token(signed_in, smith):
    Token.objects.create(user=smith, key=KEY)

    signed_in.post(reverse("rest_api:token-regenerate"))

    assert list(Token.objects.filter(user=smith).values_list("key", flat=True)) != [KEY]
    assert Token.objects.filter(user=smith).count() == 1


def test_the_new_token_opens_the_api(signed_in, smith, api_client):
    signed_in.post(reverse("rest_api:token-regenerate"))
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get(user=smith).key}")

    response = api_client.get(reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"}))

    assert response.status_code == 200


def test_the_old_token_stops_working(signed_in, smith, api_client):
    Token.objects.create(user=smith, key=KEY)
    signed_in.post(reverse("rest_api:token-regenerate"))
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {KEY}")

    response = api_client.get(reverse("rest_api:v2:user-projects", kwargs={"username": "smith01"}))

    assert response.status_code == 401


def test_only_the_callers_own_token_changes(signed_in, make_user):
    jones = make_user("jones01")
    Token.objects.create(user=jones, key=KEY)

    signed_in.post(reverse("rest_api:token-regenerate"))
    signed_in.post(reverse("rest_api:token-revoke"))

    assert Token.objects.get(user=jones).key == KEY


# Revoking


def test_revoking(signed_in, smith):
    Token.objects.create(user=smith, key=KEY)

    response = signed_in.post(reverse("rest_api:token-revoke"))

    assert response.status_code == 302
    assert response["Location"] == reverse("rest_api:token")
    assert not Token.objects.filter(user=smith).exists()
    assert "API token revoked." in page_text(signed_in.get(reverse("rest_api:token")))


def test_revoking_without_a_token(signed_in, smith):
    response = signed_in.post(reverse("rest_api:token-revoke"))

    assert response.status_code == 302
    assert not Token.objects.filter(user=smith).exists()


# Logging


@pytest.fixture
def token_log(caplog):
    caplog.set_level(logging.INFO, logger="rest_api.tokens")

    def messages():
        return [record.getMessage() for record in caplog.records if record.name == "rest_api.tokens"]

    return messages


def test_creating_is_logged(signed_in, token_log):
    signed_in.post(reverse("rest_api:token-regenerate"))

    assert token_log() == ["smith01 created an API token"]


def test_replacing_is_logged(signed_in, smith, token_log):
    Token.objects.create(user=smith, key=KEY)

    signed_in.post(reverse("rest_api:token-regenerate"))

    assert token_log() == [f"smith01 replaced their API token ending {ENDING}"]


def test_revoking_is_logged(signed_in, smith, token_log):
    Token.objects.create(user=smith, key=KEY)

    signed_in.post(reverse("rest_api:token-revoke"))

    assert token_log() == [f"smith01 revoked their API token ending {ENDING}"]


def test_revoking_nothing_isnt_logged(signed_in, token_log):
    signed_in.post(reverse("rest_api:token-revoke"))

    assert token_log() == []


# The profile page's row, which the site's user_profile.html includes


def test_profile_row_with_a_token(smith, render_profile_row):
    Token.objects.create(user=smith, key=KEY)

    row = render_profile_row(smith, smith)

    assert "API Token" in row
    assert f"<code>{ENDING}</code>" in row
    assert KEY not in row
    assert f'href="{reverse("rest_api:token")}"' in row


def test_profile_row_without_a_token(smith, render_profile_row):
    row = render_profile_row(smith, smith)

    assert "None" in row
    assert f'href="{reverse("rest_api:token")}"' in row


def test_profile_row_is_only_on_your_own_profile(smith, make_user, render_profile_row):
    Token.objects.create(user=smith, key=KEY)

    assert render_profile_row(make_user("jones01", superuser=True), smith) == ""
