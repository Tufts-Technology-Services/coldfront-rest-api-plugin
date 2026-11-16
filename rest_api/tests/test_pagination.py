"""Lists come a page at a time: 100 by default, up to 1000 on request."""

from rest_api.pagination import ApiPagination


def test_page_sizes():
    assert ApiPagination.page_size == 100
    assert ApiPagination.page_size_query_param == "page_size"
    assert ApiPagination.max_page_size == 1000
