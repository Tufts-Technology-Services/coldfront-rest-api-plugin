"""
The API token page: a signed-in person creates, replaces or revokes their own DRF token.

These are web pages, not API views: they use the browser session and CSRF like the rest of
ColdFront. The full token is shown once, on the page after it is made, and only its last six
characters after that. See docs/rest-api-plan.md.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from rest_framework.authtoken.models import Token

# who made, replaced or revoked their token; an audit trail, like rest_api.lookups
token_logger = logging.getLogger("rest_api.tokens")

# Where a new token waits for the page that shows it once. Not a flash message: Django may keep
# those in a cookie.
NEW_TOKEN_SESSION_KEY = "rest_api_new_token"


def key_ending(token):
    """The last six characters of a token's key, which is all the page and the logs ever show."""
    return token.key[-6:]


class TokenPageView(LoginRequiredMixin, TemplateView):
    """The caller's token: whether they have one, its end and date, and the buttons to change it."""

    template_name = "rest_api/token.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        token = Token.objects.filter(user=user).first()
        new_key = self.request.session.pop(NEW_TOKEN_SESSION_KEY, None)
        context["token"] = token
        # only if it is still the token they have, and not one since replaced elsewhere
        context["new_key"] = new_key if token is not None and new_key == token.key else None
        context["key_ending"] = key_ending(token) if token is not None else None
        context["example_url"] = self.request.build_absolute_uri(
            reverse("rest_api:v2:user-projects", kwargs={"username": user.username})
        )
        return context


class RegenerateTokenView(LoginRequiredMixin, View):
    """Replace the caller's token with a new one (or create their first), then show it once."""

    def post(self, request):
        user = request.user
        with transaction.atomic():
            old_token = Token.objects.select_for_update().filter(user=user).first()
            # taken first: a token's key is its primary key, which delete() clears
            old_ending = key_ending(old_token) if old_token is not None else None
            if old_token is not None:
                old_token.delete()
            token = Token.objects.create(user=user)
        request.session[NEW_TOKEN_SESSION_KEY] = token.key
        if old_ending is None:
            token_logger.info("%s created an API token", user.username)
        else:
            token_logger.info("%s replaced their API token ending %s", user.username, old_ending)
        return redirect("rest_api:token")


class RevokeTokenView(LoginRequiredMixin, View):
    """Delete the caller's token, if they have one."""

    def post(self, request):
        user = request.user
        request.session.pop(NEW_TOKEN_SESSION_KEY, None)
        token = Token.objects.filter(user=user).first()
        if token is None:
            messages.info(request, "You don't have an API token.")
        else:
            ending = key_ending(token)
            token.delete()
            token_logger.info("%s revoked their API token ending %s", user.username, ending)
            messages.success(request, "API token revoked.")
        return redirect("rest_api:token")
