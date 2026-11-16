import logging

from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated

from coldfront.core.project.models import Project, ProjectAttribute, ProjectUser

from rest_api.filters import UserProjectFilter
from rest_api.pagination import ApiPagination
from rest_api.permissions import can_view_all_projects, is_service_account, sees_private_attributes
from rest_api.serializers import UserProjectSerializer

# who looked up whom, for service accounts; see docs/rest-api-plan.md
lookup_logger = logging.getLogger("rest_api.lookups")


class PersonLookupMixin:
    """
    For views about the person `<username>` names: who may ask, and the record of who asked.
    `can_view_all` is the permissions check that lets a caller ask about someone else.
    """

    can_view_all = None

    def get_person(self):
        """
        The person the URL names. A 404 for an unknown username, and for anyone the caller may not
        look up whether they exist or not, so the API doesn't confirm who exists.
        """
        caller = self.request.user
        username = self.kwargs["username"]
        if is_service_account(caller):
            lookup_logger.info("%s looked up %s: %s", caller.username, username, self.request.path)
        if username != caller.username and not self.can_view_all(caller):
            raise Http404
        return get_object_or_404(User, username=username)


class UserProjectsView(PersonLookupMixin, ListAPIView):
    """
    GET /api/v2/users/<username>/projects/: the projects a person is an Active member or PI of.
    New and Active ones unless ?status= names others (UserProjectFilter), as in ColdFront.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = ApiPagination
    serializer_class = UserProjectSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = UserProjectFilter
    can_view_all = staticmethod(can_view_all_projects)

    def get_queryset(self):
        person = self.get_person()
        active_memberships = ProjectUser.objects.filter(user=person, status__name="Active")
        attributes = ProjectAttribute.objects.select_related("proj_attr_type").order_by("proj_attr_type__name", "pk")
        if not sees_private_attributes(self.request.user):
            attributes = attributes.filter(proj_attr_type__is_private=False)
        return (
            Project.objects.filter(Q(pi=person) | Q(pk__in=active_memberships.values("project")))
            .select_related("pi", "status")
            .prefetch_related(
                Prefetch(
                    "projectuser_set",
                    queryset=active_memberships.select_related("role", "status"),
                    to_attr="person_memberships",
                ),
                Prefetch("projectattribute_set", queryset=attributes, to_attr="visible_attributes"),
            )
            .order_by("title", "pk")
        )
