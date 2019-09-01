# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import random
import shutil
import uuid
from xml.etree import ElementTree as ET

import libvirt
from django.conf import settings
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import create_immediate_task


def new_mac():
    base = 'de:be:59'
    mac_list = []
    for i in range(3):
        random_str = "".join(random.sample("0123456789abcdef", 2))
        mac_list.append(random_str)
    res = ":".join(mac_list)
    return "{}:{}".format(base, res)


def new_define(name, memory, cpu, disk_name):
    mac = new_mac()
    disk_dir = os.path.join(settings.VM_DATA_DIR, name)
    if not os.path.exists(disk_dir):
        os.makedirs(disk_dir)
    disk_path = os.path.join(disk_dir, disk_name)
    shutil.copyfile(os.path.join(settings.VM_BASE_DISKS_DIR, disk_name), disk_path)

    memory = str(memory)
    cpu = str(cpu)
    with open("assets/vm.xml", 'r') as f:
        root = ET.fromstring(f.read())
        root.find("./uuid").text = str(uuid.uuid4())
        root.find("./name").text = name
        root.find("./memory").text = memory
        root.find("./currentMemory").text = memory
        root.find("./vcpu").text = cpu
        root.find("./devices/disk/source").attrib['file'] = disk_path
        root.find("./devices/interface/mac").attrib['address'] = mac

    return ET.tostring(root)


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

    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:

            name = self.request.data.get("name")
            try:
                conn.lookupByName(name)
            except:
                pass
            else:
                raise exceptions.ValidationError("名称已存在")
            memory = self.request.data.get("memory")
            cpu = self.request.data.get("cpu")
            disk_name = self.request.data.get("disk_name")
            res = new_define(name=name, memory=memory, cpu=cpu, disk_name=disk_name)
        #     conn.defineXML(res)
        return Response(data={"xml": res})


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


class BaseDisksView(APIView):
    def get(self, request, *args, **kwargs):
        path = settings.VM_BASE_DISKS_DIR

        files = []

        for n in os.listdir(path):
            if os.path.isfile(os.path.join(path, n)):
                files.append(n)

        return Response(data={
            "files": files
        })
