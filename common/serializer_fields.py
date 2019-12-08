# -*- coding: utf-8 -*-
import json

from rest_framework import exceptions
from rest_framework import serializers
from rest_framework.relations import ManyRelatedField, MANY_RELATION_KWARGS

from .validator import JsonValidator


class SerializerJSONField(serializers.Field):
    default_error_messages = {
        'invalid': 'Value must be valid JSON.'
    }

    def __init__(self, json_schema=None, **kwargs):
        super(SerializerJSONField, self).__init__(**kwargs)
        if json_schema:
            validator = JsonValidator(json_schema)
            self.validators.append(validator)

    def to_internal_value(self, data):
        try:
            data = json.dumps(data)
        except (TypeError, ValueError):
            self.fail('invalid')
        return data

    def to_representation(self, value):
        if isinstance(value, (str, unicode)):
            value = json.loads(value)

        return value


class SerializerGetSetField(serializers.Field):
    def __init__(self, get_method_name=None, set_method_name=None, **kwargs):
        self.get_method_name = get_method_name
        self.set_method_name = set_method_name
        super(SerializerGetSetField, self).__init__(**kwargs)

    def bind(self, field_name, parent):
        # In order to enforce a consistent style, we error if a redundant
        # 'get_method_name set_method_name' argument has been used.
        # For example:
        # my_field = serializer.CharField(source='my_field')
        default_get_method_name = 'get_{field_name}'.format(
            field_name=field_name)
        assert self.get_method_name != default_get_method_name, (
                "It is redundant to specify `%s` on SerializerMethodField "
                "'%s' in serializer '%s', because it is the same as the "
                "default method name. Remove the `get_method_name` argument." %
                (self.get_method_name, field_name, parent.__class__.__name__)
        )

        # The method name should default to `get_{field_name}`.
        if self.get_method_name is None:
            self.get_method_name = default_get_method_name

        default_set_method_name = 'set_{field_name}'.format(
            field_name=field_name)
        assert self.set_method_name != default_set_method_name, (
                "It is redundant to specify `%s` on SerializerMethodField "
                "'%s' in serializer '%s', because it is the same as the "
                "default method name. Remove the `set_method_name` argument." %
                (self.set_method_name, field_name, parent.__class__.__name__)
        )

        # The method name should default to `get_{field_name}`.
        if self.set_method_name is None:
            self.set_method_name = default_set_method_name

        super(SerializerGetSetField, self).bind(field_name, parent)

    def to_representation(self, value):
        method = getattr(self.parent, self.get_method_name)
        return method(value)

    def to_internal_value(self, value):
        method = getattr(self.parent, self.set_method_name)
        return method(value)


class ManyRelatedFieldForDelete(ManyRelatedField):
    def __init__(self, no_is_delete, *args, **kwargs):
        self.no_is_delete = no_is_delete
        super(ManyRelatedFieldForDelete, self).__init__(*args, **kwargs)

    def to_representation(self, iterable):
        if self.no_is_delete:
            return [
                self.child_relation.to_representation(value)
                for value in iterable if not value.is_delete
            ]
        else:
            return [
                self.child_relation.to_representation(value)
                for value in iterable
            ]


class SerializerForeignField(serializers.RelatedField):
    """
    处理外键字段
    """

    def __init__(self, fields, no_is_delete=False, **kwargs):
        self.fields = fields
        self.no_is_delete = no_is_delete
        super(SerializerForeignField, self).__init__(**kwargs)

    @classmethod
    def many_init(cls, *args, **kwargs):
        """
        This method handles creating a parent `ManyRelatedField` instance
        when the `many=True` keyword argument is passed.

        Typically you won't need to override this method.

        Note that we're over-cautious in passing most arguments to both parent
        and child classes in order to try to cover the general case. If you're
        overriding this method you'll probably want something much simpler, eg:

        @classmethod
        def many_init(cls, *args, **kwargs):
            kwargs['child'] = cls()
            return CustomManyRelatedField(*args, **kwargs)
        """
        no_is_delete = kwargs.pop('no_is_delete', False)
        list_kwargs = {'child_relation': cls(*args, **kwargs),
                       "no_is_delete": no_is_delete}
        for key in kwargs.keys():
            if key in MANY_RELATION_KWARGS:
                list_kwargs[key] = kwargs[key]
        return ManyRelatedFieldForDelete(**list_kwargs)

    def bind(self, field_name, parent):
        if self.queryset is None and not self.read_only:
            model = parent.Meta.model
            field = getattr(model, field_name)
            self.foreign_model = field.field.related_model
        super(SerializerForeignField, self).bind(field_name, parent)

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset
        else:
            return self.foreign_model.objects.all()

    def obj_attr(self, obj, keys):
        for key in keys:
            obj = getattr(obj, key)
        return obj

    def to_representation(self, value):
        res = {}
        if value is None:
            return None
        for i in self.fields:
            res[i] = self.obj_attr(value, i.split("__"))
        return res

    def to_internal_value(self, value):
        if isinstance(value, dict):
            id = value.get("id")
        else:
            id = value
        if not id:
            return None

        return self.get_queryset().get(pk=id)


class SerializerApiForeignField(serializers.RelatedField):
    """
    处理外键字段
    """

    def __init__(self, fields, api, **kwargs):
        self.fields = fields
        super(SerializerApiForeignField, self).__init__(**kwargs)

    def to_representation(self, value):
        res = {}

        if value is None:
            return None
        for i in self.fields:
            res[i] = self.obj_attr(value, i.split("__"))
        return res

    def to_internal_value(self, value):
        if isinstance(value, dict):
            id = value.get("id")
        else:
            id = value
        if not id:
            return None
        return self.get_queryset().get(pk=id)


class SerializerChoicesField(serializers.Field):
    def __init__(self, choices=None, **kwargs):
        self.model_choices = None
        self.choices = choices
        super(SerializerChoicesField, self).__init__(**kwargs)

    def bind(self, field_name, parent):
        if not self.choices:
            model = parent.Meta.model
            for i in model._meta.fields:
                if i.column == field_name:
                    self.model_choices = i.choices
            assert self.model_choices, ("请提供choices参数或在model中设置choices")
        super(SerializerChoicesField, self).bind(field_name, parent)

    def to_representation(self, value):
        if self.choices:
            for i in self.choices:
                if i[0] == value:
                    return i[1]

        if self.model_choices:
            for i in self.model_choices:
                if i[0] == value:
                    return i[2]

    def to_internal_value(self, value):
        if self.choices:
            for i in self.choices:
                if i[1] == value:
                    return i[0]

            keys = []
            for i in self.choices:
                keys.append(i[1])
            raise exceptions.ValidationError('请从%s中选择' % ','.join(keys))

        if self.model_choices:
            for i in self.model_choices:
                if i[2] == value:
                    return i[0]

            keys = []
            for i in self.model_choices:
                keys.append(i[2])
            raise exceptions.ValidationError('请从%s中选择' % ','.join(keys))
