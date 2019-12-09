# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import os
import uuid
from xml.etree import ElementTree as ET

import libvirt
from django.conf import settings
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import create_immediate_task
from common.viewset import BaseViewSet
from host_manager.models import Host, new_vnc_port
from host_manager.serializers import HostSerializer
from host_manager.tasks import host_action


class HostViewSet(BaseViewSet):
    search_fields = ('name',)
    serializer_class = HostSerializer
    check_unique_fields = [('name', '名称')]

    def create(self, request, *args, **kwargs):
        instance_uuid = str(uuid.uuid4())
        self.request.data['instance_uuid'] = instance_uuid
        self.request.data['instance_name'] = 'instance_' + instance_uuid
        self.request.data['vnc_port'] = new_vnc_port()
        h = Host.objects.filter(is_delete=False).order_by('-vnc_port').first()
        if h:
            self.request.data['vnc_port'] = h.vnc_port + 1
        return super(HostViewSet, self).create(request, *args, **kwargs)

    def perform_destroy(self, instance):
        task = host_action.delay(instance.id, 'delete')
        instance.last_task_id = task.id
        instance.last_task_name = "删除虚拟机"
        instance.save()

    def get_queryset(self):
        return Host.objects.filter(is_delete=False)


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

    def put(self, request, *args, **kwargs):
        xml = self.request.data.get("xml")
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            vm_root = ET.fromstring(xml)
            new_uuid = vm_root.find('./uuid').text
            if uuid != new_uuid:
                raise exceptions.ValidationError("uuid 禁止修改")
            try:
                conn.defineXML(xml)
            except Exception as ex:
                raise exceptions.ValidationError(str(ex))
        return Response()


def attach_disk(uuid, size):
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(uuid)
        except libvirt.libvirtError:
            return
        name = domain.name()
        vm_data_dir = os.path.join(settings.VM_DATA_DIR, name)
        if not os.path.exists(vm_data_dir):
            os.makedirs(vm_data_dir)
        for i in range(100):
            disk_path = os.path.join(vm_data_dir, "disk{}.qcow2".format(i))
            if not os.path.exists(disk_path):
                break
        os.system("qemu-img create -f qcow2 '{}' {}G".format(disk_path, size))
        xml_path = os.path.join(settings.BASE_DIR, 'assets/disk.xml')
        info = domain.info()
        state = info[0]
        vm_xml_str = domain.XMLDesc(0)
        vm_root = ET.fromstring(vm_xml_str)
        disks = vm_root.findall("./devices/disk")
        devs = []
        for disk in disks:
            devs.append(disk.find("./target").attrib['dev'])

        for i in range(26):
            new_dev = "vd{}".format(chr(0x61 + i))
            if new_dev not in devs:
                break

        with open(xml_path, 'r') as f:
            disk_node = ET.fromstring(f.read())
            disk_node.find("./source").attrib['file'] = disk_path
            disk_node.find("./target").attrib['dev'] = new_dev

        if state == 1:
            domain.attachDevice(ET.tostring(disk_node))

        vm_root.find("./devices").append(disk_node)
        conn.defineXML(ET.tostring(vm_root))


def detach_disk(uuid, dev):
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(uuid)
        except libvirt.libvirtError:
            return
        info = domain.info()
        state = info[0]
        vm_root = ET.fromstring(domain.XMLDesc(0))
        disks = vm_root.findall("./devices/disk")
        devices_node = vm_root.find('./devices')
        find_disk = None
        for disk in disks:
            if disk.find('./target').get("dev") == dev:
                find_disk = disk
                break
        if find_disk:
            if state == 1:
                domain.detachDevice(ET.tostring(find_disk))
            devices_node.remove(find_disk)
            conn.defineXML(ET.tostring(vm_root))


class HostDomainsView(APIView):
    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")
        action = self.request.data.get("action")
        instance = Host.objects.filter(id=pk).first()
        if not instance:
            raise exceptions.NotFound()
        action_map = {
            "shutdown": "关机",
            "destroy": "强制关机",
            "reboot": "重启",
            "start": "开机",
        }
        task = host_action.delay(pk, action)
        instance.last_task_id = task.id
        instance.last_task_name = action_map[action]
        instance.save()
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


class IsoView(APIView):
    def get(self, request, *args, **kwargs):
        path = settings.VM_ISO_DIR

        files = []

        for n in os.listdir(path):
            if os.path.isfile(os.path.join(path, n)):
                files.append(n)

        return Response(data={
            "files": files
        })


# class TaskView(APIView):
#     permission_classes = (AllowAny,)
#
#     def get(self, request, *args, **kwargs):
#         task_id = kwargs.get("task_id")
#         if not task_id:
#             task = add.delay(2, 2)
#
#             def callback(*args, **kwargs):
#                 print ("in")
#                 print(args)
#                 print(kwargs)
#
#             result = AsyncResult(task.id)
#             result.then(callback)
#             # task_id = task.id
#             # result = AsyncResult(task_id)
#             print ("out")
#             return Response(data={
#                 # "result": result.get(timeout=1),
#                 "task_id": task.id,
#                 # "status": result.state
#             })
#         else:
#             result = AsyncResult(task_id)
#             data = {
#                 "state": result.state,
#             }
#             if result.state == 'SUCCESS':
#                 data['result'] = result.get(timeout=1)
#             else:
#                 try:
#                     data['result'] = result.get(timeout=1)
#                 except Exception as ex:
#                     data['result'] = str(ex)
#             return Response(data=data)


class AttachDiskView(APIView):
    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            size = self.request.data.get("size")
            try:
                size = float(size)
            except Exception:
                raise exceptions.ValidationError("size应为数字")
            if size < 0:
                raise exceptions.ValidationError("size应为大于0的数字")
            try:
                conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
        create_immediate_task(func=attach_disk, args=(uuid, size))

        return Response()


class DetachDiskView(APIView):
    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            dev = self.request.data.get("dev")
            try:
                domain = conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
            info = domain.info()
            state = info[0]
            vm_root = ET.fromstring(domain.XMLDesc(0))
            disks = vm_root.findall("./devices/disk")
            devices_node = vm_root.find('./devices')
            find_disk = None
            for disk in disks:
                if disk.find('./target').get("dev") == dev:
                    find_disk = disk
                    break
            if find_disk:
                if state == 1:
                    if find_disk.get('device') == 'cdrom':
                        raise exceptions.ValidationError("卸载光盘镜像需要关闭虚拟机")
                    domain.detachDevice(ET.tostring(find_disk))
                devices_node.remove(find_disk)
                if find_disk.get('device') == 'disk':
                    file_name = find_disk.find("./source").attrib['file']
                    if os.path.exists(file_name):
                        os.remove(file_name)
                conn.defineXML(ET.tostring(vm_root))

        return Response()
