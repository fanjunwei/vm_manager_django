# -*- coding: utf-8 -*-

import operator

import six
from six.moves import reduce
from django.db import models
from django.db.models.fields.related import RelatedField
from rest_framework.compat import distinct
from rest_framework.filters import SearchFilter as BaseSearchFilter, \
    OrderingFilter as BaseOrderingFilter

LOOKUP_SEP = '__'


class SearchFilter(BaseSearchFilter):
    query_params_lookup_prefixes = {
        '=': 'iexact',
        '@': 'icontains',
        '~': 'iregex',
    }

    def __init__(self):
        self.request = None

    def filter_queryset(self, request, queryset, view):
        self.request = request
        search_fields = getattr(view, 'search_fields', None)
        search_terms = self.get_search_terms(request)

        if not search_fields or not search_terms:
            return queryset

        orm_lookups = [
            self.construct_search(six.text_type(search_field))
            for search_field in search_fields
        ]

        base = queryset
        conditions = []
        sub_search = getattr(view, 'sub_search', None)
        if sub_search:
            sub_search = sub_search()
        for search_term in search_terms:
            queries = [
                models.Q(**{orm_lookup: search_term})
                for orm_lookup in orm_lookups
            ]
            if sub_search:
                queries += sub_search
            conditions.append(reduce(operator.or_, queries))
        queryset = queryset.filter(reduce(operator.and_, conditions))

        if self.must_call_distinct(queryset, search_fields):
            # Filtering against a many-to-many field requires us to
            # call queryset.distinct() in order to avoid duplicate items
            # in the resulting queryset.
            # We try to avoid this if possible, for performance reasons.
            queryset = distinct(queryset, base)
        return queryset

    def get_search_terms(self, request):
        params = request.query_params.get(self.search_param, '')
        if params:
            if params[0] in self.query_params_lookup_prefixes.keys():
                params = params[1:]
            if params:
                return [params]
            else:
                return []
        else:
            return []

    def construct_search(self, field_name):
        lookup = self.lookup_prefixes.get(field_name[0])
        if lookup:
            field_name = field_name[1:]
        params = self.request.query_params.get(self.search_param, '')
        lookup = self.query_params_lookup_prefixes.get(params[0]) or lookup
        if not lookup:
            lookup = 'icontains'
        return LOOKUP_SEP.join([field_name, lookup])


class OrderingFilter(BaseOrderingFilter):
    def get_all_fields(self, model, index=0, parent=()):
        if index < 5:
            for field in model._meta.fields:
                if isinstance(field, RelatedField):
                    for i in self.get_all_fields(field.related_model,
                                                 index + 1,
                                                 parent + (field.name,)):
                        yield i
                else:
                    yield "__".join(parent + (field.name,)), field.verbose_name

    def get_valid_fields(self, queryset, view, context=None):
        valid_fields = getattr(view, 'ordering_fields', self.ordering_fields)

        if valid_fields is None:
            # Default to allowing filtering on serializer fields
            return self.get_default_valid_fields(queryset, view,
                                                 context=context)

        elif valid_fields == '__all__':
            # View explicitly allows filtering on any model field
            valid_fields = [x for x in self.get_all_fields(queryset.model)]
            valid_fields += [
                (key, key.title().split('__'))
                for key in queryset.query.annotations.keys()
            ]
        else:
            valid_fields = [
                (item, item) if isinstance(item, six.string_types) else item
                for item in valid_fields
            ]

        return valid_fields
