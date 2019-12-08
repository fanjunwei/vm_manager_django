# -*- coding: utf-8 -*-

from django.db import models
from django.utils import timezone

from .utils import gen_uuid


class BaseModel(models.Model):
    id = models.CharField(max_length=50, verbose_name=u'uuid 唯一标示符',
                          null=False, primary_key=True,
                          default=gen_uuid)
    create_time = models.DateTimeField(default=timezone.now, db_index=True,
                                       verbose_name=u'创建时间')
    modify_time = models.DateTimeField(auto_now=True, null=True, db_index=True,
                                       verbose_name=u'修改时间')
    is_delete = models.BooleanField(default=False, db_index=True,
                                    verbose_name=u'删除标记')
    delete_time = models.DateTimeField(null=True, db_index=True,
                                       verbose_name=u'删除时间')

    class Meta:
        abstract = True
