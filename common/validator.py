# -*- coding: utf-8 -*-
import functools
import json
import re

import django
import jsonschema
from jsonschema.exceptions import FormatError
from rest_framework import exceptions


class FormatChecker(object):
    def check(self, instance, format):
        if format == "date-time":
            if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", instance):
                return
        elif format == "date":
            if re.match(r"^\d{4}-\d{2}-\d{2}$", instance):
                return
        elif format == "date-time-blank":
            if not instance or re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", instance):
                return
        elif format == "date-blank":
            if not instance or re.match(r"^\d{4}-\d{2}-\d{2}$", instance):
                return
        else:
            return
        raise FormatError(
            "%r is not a %r" % (instance, format),
        )


class JsonValidator(object):
    json_schema = ''
    code = 'invalid'

    def __init__(self, json_schema=None):
        if json_schema is not None:
            self.json_schema = json_schema

    def __call__(self, value):
        """
        Validates that the input matches the regular expression
        if inverse_match is False, otherwise raises ValidationError.
        """
        try:
            if isinstance(value, (str, unicode)):
                value = json.loads(value)
            jsonschema.validate(value, self.json_schema, format_checker=FormatChecker())
        except jsonschema.ValidationError as ex:
            raise django.core.exceptions.ValidationError(ex.message, code=self.code)


def validateJSON(value, json_schema):
    try:
        jsonschema.validate(value, json_schema, format_checker=FormatChecker())
        return True, None
    except jsonschema.ValidationError as ex:
        return False, unicode(ex)


def json_check(json_schema=None):
    def check(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            data = self.request.data
            if json_schema:
                success, message = validateJSON(data, json_schema)
                if not success:
                    raise exceptions.ValidationError(message)
            return func(self, *args, **kwargs)

        return wrapper

    return check
