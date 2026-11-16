"""
The API's URLs. The deployment mounts this module at api/.

ColdFront's built-in API, which used to be at /api/, counts as v1, so this API is v2. Each
version's routes are served at /api/<version>/ and, for the newest version, at /api/latest/ and
at /api/ with no version, so callers can pin a version or follow the newest. A new version adds
its own routes and moves latest/ and the unversioned paths to them; earlier versions stay where
they are. Each prefix is its own namespace: reverse("rest_api:v2:user-projects").

The token page (token/) is a web page for people signed in to ColdFront, not part of any API
version, so it sits outside the version prefixes: reverse("rest_api:token").
"""

from django.urls import include, path

from rest_api.token_views import RegenerateTokenView, RevokeTokenView, TokenPageView
from rest_api.views import AllocationDetailView, AllocationListView, UserProjectsView

app_name = "rest_api"

v2_routes = [
    path("users/<str:username>/projects/", UserProjectsView.as_view(), name="user-projects"),
    path("allocations/", AllocationListView.as_view(), name="allocation-list"),
    path("allocations/<int:pk>/", AllocationDetailView.as_view(), name="allocation-detail"),
]

latest_routes = v2_routes

urlpatterns = [
    path("token/", TokenPageView.as_view(), name="token"),
    path("token/regenerate/", RegenerateTokenView.as_view(), name="token-regenerate"),
    path("token/revoke/", RevokeTokenView.as_view(), name="token-revoke"),
    path("v2/", include((v2_routes, "v2"))),
    path("latest/", include((latest_routes, "latest"))),
    path("", include((latest_routes, "unversioned"))),
]
