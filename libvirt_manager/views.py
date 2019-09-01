# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from xml.etree import ElementTree as ET

import libvirt
from django.conf import settings
# Create your views here.
from rest_framework.response import Response
from rest_framework.views import APIView

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


class OverviewView(APIView):
    def get(self, request, format=None):
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
