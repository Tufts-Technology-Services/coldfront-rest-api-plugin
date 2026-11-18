from django.db import models


class ApiAccess(models.Model):
    """
    No table: this exists only to carry the API's own permissions. use_api lets someone use the API
    at all (the rest_api_users group, made by migration 0002, carries it); view_any_person lets a
    service account look up anyone.

    A permission needs a content type, and a content type with no model behind it would be
    deleted, with the permission and every grant of it, by `manage.py remove_stale_contenttypes`.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("use_api", "Can use the REST API"),
            ("view_any_person", "Can look up any person through the REST API"),
        ]
        verbose_name = "API access"
