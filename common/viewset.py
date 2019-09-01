# -*- coding: utf-8 -*-
import datetime
import json

from django.db import transaction
from django.db.models import Q
from rest_framework import exceptions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.response import Response

from .utils import logger


class OperatorRecordMixin(object):
    def __init__(self, *args, **kwargs):
        self.log_info = None
        self.alarm_type = None
        self.alarm_info = None
        self.objs = []
        super(OperatorRecordMixin, self).__init__(*args, **kwargs)

    def is_record_log(self):
        method = self.request.method
        if method != 'GET':
            return True
        else:
            return False

    def perform_create(self, serializer):
        res = super(OperatorRecordMixin, self).perform_create(serializer)
        self.objs = [serializer.instance]
        return res

    def get_object(self):
        instance = super(OperatorRecordMixin, self).get_object()
        self.objs = [instance]
        return instance

    def get_action_name(self):
        if hasattr(self, 'action'):
            if self.action == "create":
                return u"添加"
            elif self.action == "partial_update":
                return u"修改"
            elif self.action == "update":
                return u"修改"
            elif self.action == "destroy":
                return u"删除"
            elif self.action == "destroy_batch":
                return u"批量删除"

        return u"执行"

    def api_operating(self):
        if hasattr(self, 'action'):
            if self.action == "create":
                return "create"
            elif self.action == "partial_update":
                return "update"
            elif self.action == "update":
                return "update"
            elif self.action == "destroy":
                return "delete"
            elif self.action == "destroy_batch":
                return "delete"

        return "run"

    def get_model_name(self):
        if hasattr(self, 'get_queryset'):
            model = self.get_queryset().model
            name = getattr(model, "model_name", None)
            if not name:
                name = model.__name__
            return name

        return ""

    def get_log_info(self):
        if self.log_info:
            return self.log_info
        model_name = self.get_model_name()
        obj_str = ""
        if self.objs:
            obj_str = []
            for i in self.objs:
                if i:
                    obj_str.append(u"%s" % i)
            if not obj_str:
                obj_str = u""
            else:
                obj_str = u"[%s]" % ','.join(obj_str)
        return u"%s%s%s" % (self.get_action_name(), model_name, obj_str)

    def get_alarm_info(self):
        return None

    def dispatch(self, request, *args, **kwargs):

        with transaction.atomic():
            response = super(OperatorRecordMixin, self).dispatch(request, *args, **kwargs)
        if not self.is_record_log():
            return response
        operating = self.api_operating()
        # if hasattr(self, 'api_operating'):
        #     operating = self.api_operating()
        # if operating is None and hasattr(self, "api_permission"):
        #     api_permission = self.api_permission()
        #     if api_permission:
        #         operating = get_permission_name(api_permission)
        if operating:
            op_log = {}
            op_log["operating"] = operating
            try:
                op_log["kwargs"] = json.dumps(kwargs) if kwargs else None
            except:
                pass

            project_id = kwargs.get("project_id")
            if project_id:
                # project = Project.objects.get(id=project_id)
                op_log["project_id"] = project_id

            try:
                op_log["request_data"] = json.dumps(self.request.data) if self.request.data else None
            except:
                pass
            try:
                op_log["query_params"] = json.dumps(
                    self.request.query_params) if self.request.query_params else None
            except:
                pass
            op_log["log_info"] = self.get_log_info()
            op_log["alarm_info"] = self.get_alarm_info()
            response.op_log = op_log
        else:
            logger.debug("not operating url:%s" % request.path)

        return response


class DestroyBatchModelMixin(object):
    """
    批量删除
    """

    def destroy_batch(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        ids = request.data.get('ids')
        DoesNotExist = getattr(queryset.model, "DoesNotExist")
        instances = []
        for id in ids:
            try:
                instance = queryset.get(id=id)
            except DoesNotExist:
                raise exceptions.NotFound('Not Found %s' % id)
            else:
                self.perform_destroy_batch_one(instance)
                instances.append(instance)

        self.objs = instances
        self.perform_destroy_batch_complete(instances)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy_batch_one(self, instance):
        with transaction.atomic():
            if hasattr(self, 'perform_destroy'):
                self.perform_destroy(instance)
            else:
                instance.is_delete = True
                instance.delete_time = datetime.datetime.now()
                instance.save()

    def perform_destroy_batch_complete(self, instances):
        pass


class BaseViewSet(OperatorRecordMixin, DestroyBatchModelMixin, viewsets.ModelViewSet):
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
        return super(BaseViewSet, self).partial_update(request, *args, **kwargs)

    def api_permission(self):
        """
        获取接口所需权限
        """
        return None

    def perform_destroy(self, instance):
        instance.is_delete = True
        instance.delete_time = datetime.datetime.now()
        instance.save()
