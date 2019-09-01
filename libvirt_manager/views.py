# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from xml.etree import ElementTree as ET

import libvirt
from django.conf import settings
# Create your views here.
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import create_immediate_task

status_map = {
    0: "no state",
    1: "running",
    2: "blocked on resource",
    3: "paused by user",
    4: "being shut down",
    5: 'shut off',
    6: 'crashed',
    7: 'suspended by guest power management',

}


class DomainsView(APIView):
    def get(self, request, *args, **kwargs):
        result = []
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            domains = conn.listAllDomains()
            for domain in domains:
                vmXml = domain.XMLDesc(0)
                root = ET.fromstring(vmXml)
                graphics = root.find('./devices/graphics')
                port = graphics.get('port')
                if port:
                    port = int(port)
                    if port < 0:
                        port = ""
                else:
                    port = ""
                info = domain.info()
                item = {
                    "uuid": domain.UUIDString(),
                    "name": domain.name(),
                    "state": status_map[info[0]],
                    "mem_kb": info[1],
                    "cpu": info[3],
                    "vnc_port": port,
                }
                result.append(item)
        return Response(data=result)


class DomainsXmlView(APIView):
    def get(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            try:
                domain = conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
            vmXml = domain.XMLDesc(0)
        return Response(data={"xml": vmXml})


def domain_action(uuid, action):
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(uuid)
        except libvirt.libvirtError:
            return
        if action == 'shutdown':
            domain.shutdown()
        elif action == 'destroy':
            domain.destroy()
        elif action == 'delete':
            domain.undefine()
        elif action == 'reboot':
            domain.reboot()
        elif action == 'start':
            domain.create()


class ActionDomainsView(APIView):
    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            try:
                conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
            action = self.request.data.get("action")
        create_immediate_task(func=domain_action, args=(uuid, action))

        return Response()


class OverviewView(APIView):
    def get(self, request, *args, **kwargs):
        vm_count = 0
        total_cpu = 0
        total_mem = 0
        vm_running_count = 0
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            domains = conn.listAllDomains()
            for domain in domains:
                vm_count += 1
                info = domain.info()
                if info[0] == 1:
                    vm_running_count += 1
                total_cpu += info[3]
                total_mem += info[1]

        return Response(data={
            "vm_count": vm_count,
            "total_cpu": total_cpu,
            "total_mem": total_mem,
            "vm_running_count": vm_running_count,
        })
