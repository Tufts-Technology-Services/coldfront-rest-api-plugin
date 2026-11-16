"""
The API's URLs. The deployment mounts this module at api/.

ColdFront's built-in API, which used to be at /api/, counts as v1, so this API is v2. Each
version's routes are served at /api/<version>/ and, for the newest version, at /api/latest/ and
at /api/ with no version, so callers can pin a version or follow the newest. A new version adds
its own routes and moves latest/ and the unversioned paths to them; earlier versions stay where
they are. Each prefix is its own namespace: reverse("rest_api:v2:user-projects").
"""

from django.urls import include, path

from rest_api.views import UserProjectsView

app_name = "rest_api"

v2_routes = [
    path("users/<str:username>/projects/", UserProjectsView.as_view(), name="user-projects"),
]

latest_routes = v2_routes

urlpatterns = [
    path("v2/", include((v2_routes, "v2"))),
    path("latest/", include((latest_routes, "latest"))),
    path("", include((latest_routes, "unversioned"))),
]
