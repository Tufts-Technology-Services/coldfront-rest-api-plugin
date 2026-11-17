"""The system checks stop ColdFront starting without the apps the API needs, or with ColdFront's own API."""

import pytest
from django.apps import apps

from rest_api.checks import check_installed_apps


def error_ids():
    return [error.id for error in check_installed_apps(None)]


def pretend_installed(monkeypatch, *, missing=(), extra=()):
    """Make apps.is_installed answer as if `missing` weren't installed and `extra` were."""
    really_installed = apps.is_installed
    monkeypatch.setattr(
        apps, "is_installed", lambda name: name in extra or (name not in missing and really_installed(name))
    )


def test_the_test_settings_pass():
    assert error_ids() == []


@pytest.mark.parametrize("app", ["rest_framework", "rest_framework.authtoken", "django_filters"])
def test_a_missing_drf_app_is_an_error(monkeypatch, app):
    pretend_installed(monkeypatch, missing=[app])

    errors = check_installed_apps(None)

    assert [error.id for error in errors] == ["rest_api.E001"]
    assert app in errors[0].msg


def test_each_missing_app_is_its_own_error(monkeypatch):
    pretend_installed(monkeypatch, missing=["rest_framework", "rest_framework.authtoken"])

    assert error_ids() == ["rest_api.E001", "rest_api.E001"]


def test_coldfronts_own_api_is_an_error(monkeypatch):
    pretend_installed(monkeypatch, extra=["coldfront.plugins.api"])

    assert error_ids() == ["rest_api.E002"]


def test_the_check_is_registered():
    from django.core import checks

    assert check_installed_apps in checks.registry.registry.get_checks()


# USER_STORAGE_AREAS: optional, but well formed if set


def storage_error_messages(settings, areas, clients=({"client_key": "hpc"},)):
    from rest_api.checks import check_user_storage_areas

    settings.USER_STORAGE_AREAS = areas
    settings.STORAGE_PLUGIN_CLIENTS = list(clients)
    errors = check_user_storage_areas(None)
    assert {error.id for error in errors} <= {"rest_api.E003"}
    return [error.msg for error in errors]


def test_no_storage_areas_is_fine(settings):
    from rest_api.checks import check_user_storage_areas

    assert check_user_storage_areas(None) == []


def test_well_formed_storage_areas_are_fine(settings):
    areas = {"home": {"client": "hpc", "path": "/homedir"}, "scratch": {"client": "hpc", "path": "/scratch"}}

    assert storage_error_messages(settings, areas) == []


@pytest.mark.parametrize(
    "areas, mentioned",
    [
        (["home"], "dict"),
        ({"home": "/homedir"}, "home"),
        ({"home": {"path": "/homedir"}}, "client"),
        ({"home": {"client": "hpc"}}, "path"),
        ({"home": {"client": "hpc", "path": "homedir"}}, "path"),
        ({"home": {"client": "rstore", "path": "/homedir"}}, "rstore"),
        ({"home/x": {"client": "hpc", "path": "/homedir"}}, "home/x"),
    ],
    ids=[
        "not a dict",
        "an area that isn't a dict",
        "no client",
        "no path",
        "a relative path",
        "an unknown client",
        "a name with a slash",
    ],
)
def test_a_malformed_storage_area_is_an_error(settings, areas, mentioned):
    messages = storage_error_messages(settings, areas)

    assert len(messages) == 1
    assert mentioned in messages[0]


def test_the_storage_check_is_registered():
    from django.core import checks

    from rest_api.checks import check_user_storage_areas

    assert check_user_storage_areas in checks.registry.registry.get_checks()
