"""The plugin loads alongside ColdFront and the DRF apps it relies on."""

from django.apps import apps


def test_plugin_is_installed():
    assert apps.get_app_config("rest_api").verbose_name == "REST API"


def test_drf_apps_are_installed():
    for label in ("rest_framework", "authtoken", "django_filters"):
        assert apps.is_installed(apps.get_app_config(label).name)
