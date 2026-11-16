from django.apps import AppConfig


class RestApiConfig(AppConfig):
    """The REST API plugin. See docs/rest-api-plan.md for what it will serve."""

    name = "rest_api"
    # the admin's name for the app; without it, the label "Rest_Api"
    verbose_name = "REST API"

    def ready(self):
        from rest_api import checks  # noqa: F401  (registers the system checks)
