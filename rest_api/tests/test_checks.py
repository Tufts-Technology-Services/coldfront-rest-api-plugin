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
