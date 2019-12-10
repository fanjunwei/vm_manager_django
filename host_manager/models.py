# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django
from django.db import models

from common.models import BaseModel


class VncPorts(models.Model):
    value = models.IntegerField(unique=True)

    class Meta:
        ordering = ['-value']


def new_vnc_port():
    while True:
        port = VncPorts.objects.all().first()
        if port:
            new_port = port.value + 1
        else:
            new_port = 5900
        try:
            VncPorts.objects.create(value=new_port)
            return new_port
        except django.db.IntegrityError:
            continue


class Host(BaseModel):
    name = models.CharField(max_length=100)
    instance_uuid = models.CharField(max_length=50)
    instance_name = models.CharField(max_length=100)
    desc = models.CharField(max_length=200, null=True, blank=True)
    cpu_core = models.IntegerField()
    vnc_port = models.IntegerField()
    mem_size_kb = models.BigIntegerField()
    xml = models.TextField(null=True)
    last_task_id = models.CharField(max_length=50, null=True)
    last_task_name = models.CharField(max_length=100, null=True)

    class Meta:
        ordering = ['-create_time']


HOST_STORAGE_DEVICE_DISK = 'disk'
HOST_STORAGE_DEVICE_CDROM = 'cdrom'

HOST_STORAGE_DEVICES = (
    (HOST_STORAGE_DEVICE_DISK, '硬盘'),
    (HOST_STORAGE_DEVICE_CDROM, '光驱'),
)


class HostStorage(BaseModel):
    host = models.ForeignKey(Host)
    device = models.CharField(choices=HOST_STORAGE_DEVICES, max_length=10)
    dev = models.CharField(max_length=20)
    bus = models.CharField(max_length=20)
    path = models.CharField(max_length=300)

    class Meta:
        ordering = ['create_time']


class HostNetwork(BaseModel):
    host = models.ForeignKey(Host)
    mac = models.CharField(max_length=20)
    network_name = models.CharField(max_length=100)
    ip = models.CharField(max_length=50)

    class Meta:
        ordering = ['create_time']


class HostSnapshot(BaseModel):
    host = models.ForeignKey(Host)
    instance_name = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    desc = models.CharField(max_length=200, null=True, blank=True)
    parent_instance_name = models.CharField(max_length=100, null=True)
    state = models.CharField(max_length=20, null=True)

    class Meta:
        ordering = ['create_time']
