from rest_framework.pagination import PageNumberPagination


class ApiPagination(PageNumberPagination):
    """Lists a page at a time: 100 by default, up to 1000 with ?page_size=."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000
