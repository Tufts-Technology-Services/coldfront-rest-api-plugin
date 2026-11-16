# Adapted from ColdFront's coldfront/plugins/api/serializers.py (ProjectSerializer,
# ProjectUserSerializer, ProjectAttributeSerializer, AllocationSerializer,
# AllocationAttributeSerializer), (C) ColdFront Authors, AGPL-3.0-or-later.

from rest_framework import serializers

from coldfront.core.allocation.models import Allocation, AllocationAttribute
from coldfront.core.project.models import Project, ProjectAttribute, ProjectUser
from coldfront.core.resource.models import Resource


class ProjectAttributeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="proj_attr_type.name")
    is_private = serializers.BooleanField(source="proj_attr_type.is_private")

    class Meta:
        model = ProjectAttribute
        fields = ("name", "value", "is_private")


class MembershipSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="name", read_only=True)
    status = serializers.SlugRelatedField(slug_field="name", read_only=True)

    class Meta:
        model = ProjectUser
        fields = ("role", "status")


class UserProjectSerializer(serializers.ModelSerializer):
    """
    A project as the projects endpoint lists it, with the looked-up person's membership.

    Expects the view's prefetches: `person_memberships` (the person's Active ProjectUser rows) and
    `visible_attributes` (the attributes the caller may see).
    """

    pi = serializers.SlugRelatedField(slug_field="username", read_only=True)
    status = serializers.SlugRelatedField(slug_field="name", read_only=True)
    membership = serializers.SerializerMethodField()
    project_attributes = ProjectAttributeSerializer(source="visible_attributes", many=True, read_only=True)

    class Meta:
        model = Project
        fields = ("id", "title", "status", "pi", "membership", "project_attributes")

    def get_membership(self, project):
        """The person's own ProjectUser row, or None for a PI without one."""
        memberships = project.person_memberships
        return MembershipSerializer(memberships[0]).data if memberships else None


class AllocationAttributeSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="allocation_attribute_type.name")
    usage = serializers.SerializerMethodField()
    is_private = serializers.BooleanField(source="allocation_attribute_type.is_private")

    class Meta:
        model = AllocationAttribute
        fields = ("name", "value", "usage", "is_private")

    def get_usage(self, attribute):
        """The attribute's AllocationAttributeUsage value, or None for an attribute without one."""
        usage = getattr(attribute, "allocationattributeusage", None)
        return usage.value if usage is not None else None


class AllocationProjectSerializer(serializers.ModelSerializer):
    pi = serializers.SlugRelatedField(slug_field="username", read_only=True)

    class Meta:
        model = Project
        fields = ("id", "title", "pi")


class ResourceSerializer(serializers.ModelSerializer):
    resource_type = serializers.SlugRelatedField(slug_field="name", read_only=True)

    class Meta:
        model = Resource
        fields = ("name", "resource_type")


class AllocationSerializer(serializers.ModelSerializer):
    """
    An allocation, in the list and on its own.

    Expects the view's prefetches: `listed_resources` (its resources, by name) and
    `visible_attributes` (the attributes the caller may see).
    """

    project = AllocationProjectSerializer(read_only=True)
    status = serializers.SlugRelatedField(slug_field="name", read_only=True)
    resources = ResourceSerializer(source="listed_resources", many=True, read_only=True)
    allocation_attributes = AllocationAttributeSerializer(source="visible_attributes", many=True, read_only=True)

    class Meta:
        model = Allocation
        fields = ("id", "project", "status", "resources", "start_date", "end_date", "allocation_attributes")
