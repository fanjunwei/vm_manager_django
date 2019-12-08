# -*- coding: utf-8 -*-
import datetime
import json
import logging
import random
import traceback
import uuid

import six
from concurrent import futures
from django.conf import settings
from django.db import connections
from django.http import Http404
from django.test import TransactionTestCase
from rest_framework import exceptions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

logger = logging.getLogger('default')


def gen_uuid():
    return str(uuid.uuid4())


class BaseTest(TransactionTestCase):
    def post(self, url, data=None, **extra):
        if data:
            data = json.dumps(data)
        return self.client.post(url, data=data,
                                content_type='application/json')

    def get(self, url, data=None, **extra):
        if data:
            data = json.dumps(data)
        return self.client.get(url, data=data, content_type='application/json')

    def put(self, url, data=None, **extra):
        if data:
            data = json.dumps(data)
        return self.client.put(url, data=data, content_type='application/json')

    def delete(self, url, data=None, **extra):
        if data:
            data = json.dumps(data)
        return self.client.delete(url, data=data,
                                  content_type='application/json')


class ServerError(exceptions.APIException):
    """
    self define exception
    自定义异常
    """
    pass


def common_except_log():
    logger.error('\n**common_except_log**\n' + traceback.format_exc())


_threadpool_map = {}


def callInThread(self, fn, *args, **kwargs):
    self.submit(fn, *args, **kwargs)


def get_threadpool(name='default'):
    global _threadpool_map
    _threadpool = _threadpool_map.get(name)
    if not _threadpool:
        futures.ThreadPoolExecutor.callInThread = callInThread
        _threadpool = futures.ThreadPoolExecutor(max_workers=20)
        _threadpool_map[name] = _threadpool
    return _threadpool


def create_immediate_task(func, args=None, kwargs=None):
    if hasattr(settings, 'IS_TEST') and settings.IS_TEST:
        return
    args = args or ()
    kwargs = kwargs or {}

    def task(*args, **kwargs):
        try:
            check_connection()
            func(*args, **kwargs)
        except Exception:
            common_except_log()

    get_threadpool().callInThread(task, *args, **kwargs)


def to_str(value):
    if isinstance(value, unicode):
        return value.encode('utf-8')
    elif isinstance(value, str):
        return value
    else:
        return str(value)


def to_unicode(value):
    if isinstance(value, str):
        return value.decode('utf-8')
    elif isinstance(value, unicode):
        return value
    else:
        return unicode(value)


def format_timedelta(dtime):
    if isinstance(dtime, datetime.timedelta):
        seconds = dtime.total_seconds()
    else:
        seconds = dtime
    res = []
    day_length = 60 * 60 * 24
    days = int(seconds / day_length)
    if days > 0:
        res.append("%d天" % days)
        seconds -= days * day_length

    hour_length = 60 * 60
    hours = int(seconds / hour_length)
    if days > 0 or hours > 0:
        res.append("%d小时" % hours)
        seconds -= hours * hour_length

    minutes_length = 60
    minutes = int(seconds / minutes_length)
    if days > 0 or hours > 0 or minutes > 0:
        res.append("%d分钟" % minutes)
        seconds -= minutes * minutes_length

    if days == 0 and hours == 0 and minutes == 0:
        res.append("%d秒钟" % seconds)

    return "".join(res)


def check_connection():
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()


def format_size(size, unit='B', rate=1024):
    if size is None or size == "":
        return ""
    us = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']
    index = 0
    while size >= rate:
        size = float(size) / rate
        index += 1

    return "%.2f%s%s" % (size, us[index], unit)


def empty_dict():
    return {}


def empty_list():
    return []


def get_error_message(detail):
    if isinstance(detail, (list, tuple)):
        values = []
        for i in detail:
            values.append(get_error_message(i))
        return ','.join(values)
    elif isinstance(detail, dict):
        values = []
        for k, v in detail.items():
            values.append("%s:%s" % (k, get_error_message(v)))
        return ','.join(values)
    elif isinstance(detail, (str, unicode)):
        return detail
    else:
        return str(detail)


def rest_exception_handler(exc, context):
    """
    Returns the response that should be used for any given exception.

    By default we handle the REST framework `APIException`, and also
    Django's built-in `Http404` and `PermissionDenied` exceptions.

    Any unhandled exceptions may return `None`, which will cause a 500 error
    to be raised.
    """
    try:
        from rest_framework.compat import set_rollback
    except Exception:
        from rest_framework.views import set_rollback
    if isinstance(exc, exceptions.APIException):
        headers = {}
        if getattr(exc, 'auth_header', None):
            headers['WWW-Authenticate'] = exc.auth_header
        if getattr(exc, 'wait', None):
            headers['Retry-After'] = '%d' % exc.wait

        message = ""
        if isinstance(exc.detail, (list, dict)):
            message = get_error_message(exc.detail)
        else:
            message = exc.detail
        data = {'message': message}
        error_code = None
        if hasattr(exc, 'error_code'):
            error_code = int(exc.error_code)
        elif exc.status_code == 403:
            if isinstance(exc, exceptions.NotAuthenticated):
                error_code = 1
        if error_code:
            data['error_code'] = error_code
        set_rollback()
        return Response(data, status=exc.status_code, headers=headers)

    elif isinstance(exc, Http404):
        msg = 'Not found.'
        data = {'message': six.text_type(msg)}

        set_rollback()
        return Response(data, status=status.HTTP_404_NOT_FOUND)

    elif isinstance(exc, PermissionDenied):
        msg = 'Permission denied.'
        data = {'message': six.text_type(msg)}

        set_rollback()
        return Response(data, status=status.HTTP_403_FORBIDDEN)

    # Note: Unhandled exceptions will raise a 500 error.
    return None


def new_mac():
    base = 'de:be:59'
    mac_list = []
    for i in range(3):
        random_str = "".join(random.sample("0123456789abcdef", 2))
        mac_list.append(random_str)
    res = ":".join(mac_list)
    return "{}:{}".format(base, res)
