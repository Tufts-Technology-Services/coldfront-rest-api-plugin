"""
GET /api/v2/users/<username>/storage/ and /storage/<area>/: a person's own storage areas and, for
one area, their quota and usage there. See rest_api.user_storage and docs/rest-api-plan.md.
"""

import logging

from django.http import Http404
from django.urls import reverse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_api.permissions import can_view_all_storage
from rest_api.user_storage import StorageLookupsOff, StorageUnavailable, configured_areas, lookup_user_storage
from rest_api.views import PersonLookupMixin

logger = logging.getLogger(__name__)

LOOKUPS_OFF = "Storage lookups are off on this host."
# VAST's own error text names the VMS, so callers get this instead; the log has the rest
UNAVAILABLE = "The storage system didn't answer. Try again later."


class UserStorageAreasView(PersonLookupMixin, APIView):
    """The configured areas, each with the URL to ask about it, on the prefix the caller used."""

    permission_classes = [IsAuthenticated]
    can_view_all = staticmethod(can_view_all_storage)

    def get(self, request, username):
        person = self.get_person()
        namespace = request.resolver_match.namespace
        areas = [
            {
                "name": name,
                "url": request.build_absolute_uri(
                    reverse(f"{namespace}:user-storage-area", kwargs={"username": person.username, "area": name})
                ),
            }
            for name in configured_areas()
        ]
        return Response({"username": person.username, "areas": areas})


class UserStorageAreaView(PersonLookupMixin, APIView):
    """One area: the person's limits and usage, a 404 for an area that isn't configured, a 503 if VAST can't say."""

    permission_classes = [IsAuthenticated]
    can_view_all = staticmethod(can_view_all_storage)

    def get(self, request, username, area):
        person = self.get_person()
        if area not in configured_areas():
            raise Http404
        try:
            return Response(lookup_user_storage(area, person.username))
        except StorageLookupsOff:
            return Response({"detail": LOOKUPS_OFF}, status=503)
        except StorageUnavailable as error:
            logger.error("storage lookup failed: %s", error)
            return Response({"detail": UNAVAILABLE}, status=503)
