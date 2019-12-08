# -*- coding: utf-8 -*-
import datetime

from django.db.models import Q
from rest_framework import exceptions
from rest_framework import viewsets


class BaseViewSet(viewsets.ModelViewSet):
    ordering_fields = '__all__'
    check_unique_fields = []

    @classmethod
    def as_list(cls):
        return cls.as_view({
            'get': 'list',
            'post': 'create',
            # 'delete': 'destroy_batch'
        })

    @classmethod
    def as_detail(cls):
        return cls.as_view({
            'get': 'retrieve',
            'put': 'partial_update',
            'delete': 'destroy',
        })

    def _check_unique(self):
        project_id = self.kwargs.get("project_id")
        pk = self.kwargs.get('pk')
        for f in self.check_unique_fields:
            field = f[0]
            field_name = f[1]
            value = self.request.data.get(field)
            q = Q(**{field: value})
            if isinstance(value, (str, unicode)):
                q.add(Q(**{field: value.strip()}), Q.OR)
            query = self.get_queryset().filter(q)
            if project_id:
                query = query.filter(project_id=project_id)
            if pk:
                query = query.exclude(pk=pk)
            if query.exists():
                raise exceptions.ValidationError(u'{}已存在'.format(field_name))

    def create(self, request, *args, **kwargs):
        self._check_unique()
        return super(BaseViewSet, self).create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._check_unique()
        return super(BaseViewSet, self).partial_update(request, *args,
                                                       **kwargs)

    def api_permission(self):
        """
        获取接口所需权限
        """
        return None

    def perform_destroy(self, instance):
        instance.is_delete = True
        instance.delete_time = datetime.datetime.now()
        instance.save()
