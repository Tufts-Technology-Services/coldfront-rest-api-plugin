"""
The API's filters (django-filter FilterSets). See docs/rest-api-plan.md for each endpoint's.

They only narrow what a caller may see: each view decides who is listed, then these filter that.
Every filter can be repeated to match any of several values (?resource=A&resource=B).
"""

from django import forms
from django.db.models import Q
from django_filters import rest_framework as filters

from coldfront.core.allocation.models import Allocation, AllocationStatusChoice
from coldfront.core.project.models import Project, ProjectStatusChoice

# The project statuses ColdFront's main project list, and its allocation list for an ordinary
# user, show. Archived projects are on a page of their own in ColdFront; the projects endpoint
# gives them with ?status=Archived.
LISTED_PROJECT_STATUSES = ["New", "Active"]


class AnyValuesField(forms.MultipleChoiceField):
    """Any number of values for one parameter, with no fixed list of choices to check them against."""

    def valid_value(self, value):
        return True


class WholeNumbersField(AnyValuesField):
    """Like AnyValuesField, but each value must be a whole number, such as an id."""

    def clean(self, value):
        values = super().clean(value)
        try:
            return [int(number) for number in values]
        except ValueError:
            raise forms.ValidationError("Enter whole numbers.") from None


class AnyValuesFilter(filters.MultipleChoiceFilter):
    """A repeatable filter matching any of its values (an OR), with the filter's lookup."""

    field_class = AnyValuesField


class WholeNumbersFilter(AnyValuesFilter):
    field_class = WholeNumbersField


class UserProjectFilter(filters.FilterSet):
    """
    ?status=, repeatable, by status name. Without it, New and Active projects, as ColdFront's
    project list shows; with it, exactly the statuses named. An unknown name is a 400.
    """

    status = filters.ModelMultipleChoiceFilter(
        field_name="status__name", to_field_name="name", queryset=ProjectStatusChoice.objects.all()
    )

    class Meta:
        model = Project
        fields = ["status"]

    def filter_queryset(self, queryset):
        if not self.form.cleaned_data.get("status"):
            queryset = queryset.filter(status__name__in=LISTED_PROJECT_STATUSES)
        return super().filter_queryset(queryset)


class AllocationFilter(filters.FilterSet):
    """
    The allocation list's filters. resource_type and resource match any of the allocation's
    resources, case-insensitively and in part; status by name (an unknown one is a 400); project
    by id; username an Active allocation user or the project's PI.
    """

    resource_type = AnyValuesFilter(field_name="resources__resource_type__name", lookup_expr="icontains")
    resource = AnyValuesFilter(field_name="resources__name", lookup_expr="icontains")
    status = filters.ModelMultipleChoiceFilter(
        field_name="status__name", to_field_name="name", queryset=AllocationStatusChoice.objects.all()
    )
    project = WholeNumbersFilter(field_name="project_id")
    username = AnyValuesFilter(method="filter_username")

    class Meta:
        model = Allocation
        fields = ["resource_type", "resource", "status", "project", "username"]

    def filter_username(self, queryset, name, usernames):
        # one Q for the allocation user and their status, so both are about the same row
        return queryset.filter(
            Q(allocationuser__user__username__in=usernames, allocationuser__status__name="Active")
            | Q(project__pi__username__in=usernames)
        ).distinct()
