# -*- coding: utf-8 -*-
from rest_framework.pagination import LimitOffsetPagination


def _get_count(queryset):
    """
    Determine an object count, supporting either querysets or regular lists.
    """
    try:
        return queryset.count()
    except (AttributeError, TypeError):
        return len(queryset)


class AllResultPagination(LimitOffsetPagination):
    def paginate_queryset(self, queryset, request, view=None):
        self.display_page_controls = False
        self.count = _get_count(queryset)
        return list(queryset)

    def get_previous_link(self):
        return None

    def get_next_link(self):
        return None

    def get_fields(self, view):
        return []


class LimitOffsetAndAllPagination(LimitOffsetPagination):
    def get_limit(self, request):
        if request.query_params.get(self.limit_query_param) == 'all':
            return 'all'
        else:
            return super(LimitOffsetAndAllPagination, self).get_limit(request)

    def paginate_queryset(self, queryset, request, view=None):
        self.limit = self.get_limit(request)
        if self.limit is None:
            return None
        self.offset = self.get_offset(request)
        self.count = _get_count(queryset)
        self.request = request
        if self.limit != 'all':
            if self.count > self.limit and self.template is not None:
                self.display_page_controls = True
            return list(queryset[self.offset:self.offset + self.limit])
        else:
            self.display_page_controls = False
            return list(queryset[self.offset:])

    def get_previous_link(self):
        if self.limit and self.limit != 'all':
            return super(LimitOffsetAndAllPagination, self).get_previous_link()
        else:
            return None

    def get_next_link(self):
        if self.limit and self.limit != 'all':
            return super(LimitOffsetAndAllPagination, self).get_next_link()
        else:
            return None
