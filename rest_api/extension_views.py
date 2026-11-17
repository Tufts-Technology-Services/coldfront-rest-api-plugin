"""
Plugin extensions: what plugins serve through the API, from coldfront_utils.api_extensions' registry.
See "Plugin extensions" in docs/rest-api-plan.md.

The API decides nothing about an extension's content. It finds the extension, looks up the person,
project or allocation the URL names, and asks the extension's allows() whether the caller may see
it: a missing target and a refusal are the same 404, so a caller can't tell who or what exists.
"""

import logging

from coldfront_utils.api_extensions import (
    ExtensionNotFound,
    ExtensionUnavailable,
    find_extension,
    registered_extensions,
)
from django.contrib.auth.models import User
from django.http import Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from coldfront.core.allocation.models import Allocation
from coldfront.core.project.models import Project

from rest_api.permissions import is_service_account

# who looked up whom, for service accounts, as for the API's own endpoints
lookup_logger = logging.getLogger("rest_api.lookups")
# extensions that failed, with the extension's name
logger = logging.getLogger("rest_api.extensions")


def get_or_404(model, **lookup):
    """The one model instance lookup finds, or a plain Http404. Not get_object_or_404, whose message
    names the model and would tell a missing target from a refused one."""
    instance = model.objects.filter(**lookup).first()
    if instance is None:
        raise Http404
    return instance


class ExtensionView(APIView):
    """
    GET <target>/<name>/ and <target>/<name>/<key>/: an extension's summary, or one of its items.
    A subclass serves one kind, and says how to find its target and how to log a service account's
    lookup of it.
    """

    permission_classes = [IsAuthenticated]
    # "person", "project" or "allocation"
    kind = None

    def get_target(self):
        """The person, project or allocation the URL names; Http404 if there's none."""
        raise NotImplementedError

    def target_description(self):
        """How rest_api.lookups names the target: a username, "project 12", "allocation 34"."""
        raise NotImplementedError

    def get(self, request, name, key=None, **kwargs):
        caller = request.user
        extension_class = find_extension(self.kind, name)
        if extension_class is None:
            raise Http404
        if is_service_account(caller):
            lookup_logger.info("%s looked up %s: %s", caller.username, self.target_description(), request.path)
        target = self.get_target()
        extension = extension_class()
        if not extension.allows(target, caller):
            raise Http404
        try:
            if key is None:
                data = extension.summary(target, caller)
            else:
                data = extension.item(target, key, caller)
        except ExtensionNotFound:
            raise Http404 from None
        except ExtensionUnavailable as unavailable:
            return Response({"detail": str(unavailable)}, status=503)
        except Exception:
            logger.exception(
                "The %s extension %s (%s) failed: %s", self.kind, name, extension_class.__name__, request.path
            )
            raise
        return Response(data)


class PersonExtensionView(ExtensionView):
    """users/<username>/<name>/[<key>/]"""

    kind = "person"

    def get_target(self):
        return get_or_404(User, username=self.kwargs["username"])

    def target_description(self):
        return self.kwargs["username"]


class ProjectExtensionView(ExtensionView):
    """projects/<pk>/<name>/[<key>/]"""

    kind = "project"

    def get_target(self):
        return get_or_404(Project, pk=self.kwargs["pk"])

    def target_description(self):
        return f"project {self.kwargs['pk']}"


class AllocationExtensionView(ExtensionView):
    """allocations/<pk>/<name>/[<key>/]"""

    kind = "allocation"

    def get_target(self):
        return get_or_404(Allocation, pk=self.kwargs["pk"])

    def target_description(self):
        return f"allocation {self.kwargs['pk']}"


class ExtensionListView(APIView):
    """
    GET extensions/: every registered extension, by kind, with its name, description, version and
    whether it's deprecated, so a caller can see what this deployment serves.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(
            {
                kind: [
                    {
                        "name": extension_class.name,
                        "description": extension_class.description,
                        "version": extension_class.version,
                        "deprecated": extension_class.deprecated,
                    }
                    for extension_class in extension_classes
                ]
                for kind, extension_classes in registered_extensions().items()
            }
        )
