"""
The API's filters (django-filter FilterSets). See docs/rest-api-plan.md for each endpoint's.

They only narrow what a caller may see: each view decides who is listed, then these filter that.
"""

from django_filters import rest_framework as filters

from coldfront.core.project.models import Project, ProjectStatusChoice

# The project statuses ColdFront's main project list, and its allocation list for an ordinary
# user, show. Archived projects are on a page of their own in ColdFront; the projects endpoint
# gives them with ?status=Archived.
LISTED_PROJECT_STATUSES = ["New", "Active"]


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
