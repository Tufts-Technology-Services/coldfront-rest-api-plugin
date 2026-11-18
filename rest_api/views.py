import logging

from django.contrib.auth.models import User
from django.db.models import Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.generics import ListAPIView, RetrieveAPIView

from coldfront.core.allocation.models import Allocation, AllocationAttribute, AllocationPermission
from coldfront.core.project.models import Project, ProjectAttribute, ProjectUser
from coldfront.core.resource.models import Resource

from rest_api.filters import LISTED_PROJECT_STATUSES, AllocationFilter, UserProjectFilter
from rest_api.pagination import ApiPagination
from rest_api.permissions import (
    CanUseApi,
    can_view_all_allocations,
    can_view_all_projects,
    is_service_account,
    sees_private_attributes,
)
from rest_api.serializers import AllocationSerializer, UserProjectSerializer

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

    permission_classes = [CanUseApi]
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


def allocations_with_details(caller):
    """Allocations with what AllocationSerializer shows prefetched, and only the attributes the caller may see."""
    attributes = AllocationAttribute.objects.select_related(
        "allocation_attribute_type", "allocationattributeusage"
    ).order_by("allocation_attribute_type__name", "pk")
    if not sees_private_attributes(caller):
        attributes = attributes.filter(allocation_attribute_type__is_private=False)
    return Allocation.objects.select_related("project__pi", "status").prefetch_related(
        Prefetch(
            "resources",
            queryset=Resource.objects.select_related("resource_type").order_by("name"),
            to_attr="listed_resources",
        ),
        Prefetch("allocationattribute_set", queryset=attributes, to_attr="visible_attributes"),
    )


def allocations_listed_for(user):
    """
    The allocations ColdFront's allocation list shows someone who can't see them all: on a New or
    Active project where they have an Active ProjectUser row, and either that row is a Manager's
    or they are an Active or PendingEULA user of the allocation. One filter() call, as in
    ColdFront, so the role and status are about the same ProjectUser row.
    """
    return Allocation.objects.filter(
        Q(project__status__name__in=LISTED_PROJECT_STATUSES)
        & Q(project__projectuser__user=user)
        & Q(project__projectuser__status__name="Active")
        & (
            Q(project__projectuser__role__name="Manager")
            | Q(allocationuser__user=user) & Q(allocationuser__status__name__in=["Active", "PendingEULA"])
        )
    )


class AllocationListView(ListAPIView):
    """
    GET /api/v2/allocations/: the allocations ColdFront's allocation list would show the caller,
    narrowed by AllocationFilter. Those who can see all allocations get every one, as ColdFront's
    "show all allocations" does, whatever its project's status.
    """

    permission_classes = [CanUseApi]
    pagination_class = ApiPagination
    serializer_class = AllocationSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = AllocationFilter

    def get(self, request, *args, **kwargs):
        if is_service_account(request.user):
            lookup_logger.info("%s looked up allocations: %s", request.user.username, request.get_full_path())
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        caller = self.request.user
        allocations = allocations_with_details(caller)
        if not can_view_all_allocations(caller):
            allocations = allocations.filter(pk__in=allocations_listed_for(caller).values("pk"))
        return allocations.order_by("pk")


class AllocationDetailView(RetrieveAPIView):
    """
    GET /api/v2/allocations/<id>/: one allocation, if ColdFront's allocation page would show it to
    the caller: those who can see all allocations, and anyone Allocation.has_perm gives USER.
    Anyone else gets the same 404 as for an allocation that doesn't exist.
    """

    permission_classes = [CanUseApi]
    serializer_class = AllocationSerializer

    def get(self, request, *args, **kwargs):
        if is_service_account(request.user):
            lookup_logger.info(
                "%s looked up allocation %s: %s", request.user.username, self.kwargs["pk"], request.get_full_path()
            )
        return super().get(request, *args, **kwargs)

    def get_object(self):
        caller = self.request.user
        # not get_object_or_404, whose message names the model: a missing allocation and a refused
        # one would then differ, telling anyone which ids exist
        allocation = allocations_with_details(caller).filter(pk=self.kwargs["pk"]).first()
        if allocation is None:
            raise Http404
        if not (can_view_all_allocations(caller) or allocation.has_perm(caller, AllocationPermission.USER)):
            raise Http404
        return allocation
