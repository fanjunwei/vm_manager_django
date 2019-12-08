# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import random
import shutil
import uuid
from xml.etree import ElementTree as ET

import libvirt
from celery.result import AsyncResult
from django.conf import settings
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import create_immediate_task
from host_manager.tasks import add


def new_mac():
    base = 'de:be:59'
    mac_list = []
    for i in range(3):
        random_str = "".join(random.sample("0123456789abcdef", 2))
        mac_list.append(random_str)
    res = ":".join(mac_list)
    return "{}:{}".format(base, res)


def new_define(name, description, memory, cpu, disk_name, is_from_iso,
               iso_names, disk_size):
    mac = new_mac()
    vm_data_dir = os.path.join(settings.VM_DATA_DIR, name)
    if not os.path.exists(vm_data_dir):
        os.makedirs(vm_data_dir)
    if not is_from_iso:
        disk_path = os.path.join(vm_data_dir, disk_name)
        shutil.copyfile(os.path.join(settings.VM_BASE_DISKS_DIR, disk_name),
                        disk_path)
    else:
        disk_path = ""
        for i in range(100):
            disk_path = os.path.join(vm_data_dir,
                                     "root_disk{}.qcow2".format(i))
            if not os.path.exists(disk_path):
                break
        os.system(
            "qemu-img create -f qcow2 '{}' {}G".format(disk_path, disk_size))

    memory = str(memory)
    cpu = str(cpu)
    vm_xml_path = os.path.join(settings.BASE_DIR, 'assets/vm.xml')
    disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/disk.xml')
    iso_disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/ios_disk.xml')
    with open(disk_xml_path, 'r') as f:
        disk_root = ET.fromstring(f.read())
        disk_root.find("./source").attrib['file'] = disk_path
    if is_from_iso:
        iso_disk_root_list = []
        for index, item in enumerate(iso_names):
            dev = "hd{}".format(chr(0x61 + index))
            with open(iso_disk_xml_path, 'r') as f:
                iso_disk_root = ET.fromstring(f.read())
                iso_disk_root.find("./source").attrib['file'] = os.path.join(
                    settings.VM_ISO_DIR, item)
                iso_disk_root.find("./target").attrib['dev'] = dev
                iso_disk_root_list.append(iso_disk_root)

    with open(vm_xml_path, 'r') as f:
        vm_root = ET.fromstring(f.read())
        vm_root.find("./uuid").text = str(uuid.uuid4())
        vm_root.find("./name").text = name
        vm_root.find("./description").text = description
        vm_root.find("./memory").text = memory
        vm_root.find("./currentMemory").text = memory
        vm_root.find("./vcpu").text = cpu
        vm_root.find("./devices").append(disk_root)
        if is_from_iso:
            for i in iso_disk_root_list:
                vm_root.find("./devices").append(i)
        vm_root.find("./devices/interface/mac").attrib['address'] = mac

    return ET.tostring(vm_root)


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
            net_map = {}
            for net in conn.listAllNetworks():
                net_name = net.name()
                for i in net.DHCPLeases():
                    mac = i.get("mac")
                    ipaddr = i.get("ipaddr")
                    key = "{}/{}".format(net_name, mac)
                    net_map[key] = ipaddr
            for domain in domains:
                vmXml = domain.XMLDesc(0)
                root = ET.fromstring(vmXml)
                port = root.find('./devices/graphics').get('port')
                description = root.find('./description')
                if description is not None:
                    description = description.text
                else:
                    description = ""
                if port:
                    port = int(port)
                    if port < 0:
                        port = ""
                else:
                    port = ""
                disks_xml = root.findall("./devices/disk")
                disks = []
                for xml_node in disks_xml:
                    device = xml_node.attrib['device']
                    dev = xml_node.find("./target").attrib['dev']
                    file_name = xml_node.find("./source").attrib['file']
                    disks.append(
                        {"dev": dev, 'file': file_name, 'device': device})
                interface_xml = root.findall("./devices/interface")
                ipaddrs = []
                for xml_node in interface_xml:
                    net_name = xml_node.find("./source").get("network")
                    mac = xml_node.find("./mac").get("address")
                    key = "{}/{}".format(net_name, mac)
                    ip = net_map.get(key)
                    if ip:
                        ipaddrs.append(ip)

                info = domain.info()
                item = {
                    "uuid": domain.UUIDString(),
                    "description": description,
                    "name": domain.name(),
                    "state": status_map[info[0]],
                    "mem_kb": info[1],
                    "cpu": info[3],
                    "vnc_port": port,
                    "disks": disks,
                    "ipaddrs": ipaddrs,
                }
                result.append(item)
        return Response(data=result)

    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:

            name = self.request.data.get("name")
            try:
                conn.lookupByName(name)
            except Exception:
                pass
            else:
                raise exceptions.ValidationError("名称已存在")
            description = self.request.data.get("description")
            memory = self.request.data.get("memory")
            cpu = self.request.data.get("cpu")
            disk_name = self.request.data.get("disk_name")
            is_from_iso = self.request.data.get("is_from_iso")
            iso_names = self.request.data.get("iso_names")
            disk_size = self.request.data.get("disk_size")
            if disk_size:
                try:
                    disk_size = float(disk_size)
                except Exception:
                    raise exceptions.ValidationError('disk_size 应为数字')
                if disk_size < 0:
                    raise exceptions.ValidationError('disk_size 应为大于0的数字数字')
            res = new_define(name=name, description=description, memory=memory,
                             cpu=cpu, disk_name=disk_name,
                             is_from_iso=is_from_iso,
                             iso_names=iso_names, disk_size=disk_size)
            conn.defineXML(res)
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


def domain_action(uuid, action):
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(uuid)
        except libvirt.libvirtError:
            return
        info = domain.info()
        state = info[0]
        if action == 'shutdown':
            if state == 1:
                domain.shutdown()
        elif action == 'destroy':
            if state != 5:
                domain.destroy()
        elif action == 'delete':
            vmXml = domain.XMLDesc(0)
            if state == 1:
                domain.destroy()
            domain.undefine()
            root = ET.fromstring(vmXml)
            disks_xml = root.findall("./devices/disk")
            for xml_node in disks_xml:
                device = xml_node.attrib['device']
                if device == 'disk':
                    file_name = xml_node.find("./source").attrib['file']
                    if os.path.exists(file_name):
                        os.remove(file_name)
        elif action == 'reboot':
            domain.reboot()
        elif action == 'start':
            domain.create()


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


class ActionDomainsView(APIView):
    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            try:
                conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
            action = self.request.data.get("action")
        # create_immediate_task(func=domain_action, args=(uuid, action))
        domain_action(uuid, action)

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


class TaskView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, *args, **kwargs):
        task_id = kwargs.get("task_id")
        if not task_id:
            task = add.delay(2, 2)

            def callback(*args, **kwargs):
                print ("in")
                print(args)
                print(kwargs)

            result = AsyncResult(task.id)
            result.then(callback)
            # task_id = task.id
            # result = AsyncResult(task_id)
            print ("out")
            return Response(data={
                # "result": result.get(timeout=1),
                "task_id": task.id,
                # "status": result.state
            })
        else:
            result = AsyncResult(task_id)
            data = {
                "state": result.state,
            }
            if result.state == 'SUCCESS':
                data['result'] = result.get(timeout=1)
            return Response(data=data)


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