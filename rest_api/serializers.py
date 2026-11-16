# Adapted from ColdFront's coldfront/plugins/api/serializers.py (ProjectSerializer,
# ProjectUserSerializer, ProjectAttributeSerializer), (C) ColdFront Authors, AGPL-3.0-or-later.

from rest_framework import serializers

from coldfront.core.project.models import Project, ProjectAttribute, ProjectUser


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
