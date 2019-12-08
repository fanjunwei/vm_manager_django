# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models

from common.models import BaseModel


class Host(BaseModel):
    name = models.CharField(max_length=100)
