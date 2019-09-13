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


def new_define(name, memory, cpu, disk_name, is_from_iso, iso_name, disk_size):
    mac = new_mac()
    vm_data_dir = os.path.join(settings.VM_DATA_DIR, name)
    if not os.path.exists(vm_data_dir):
        os.makedirs(vm_data_dir)
    if not is_from_iso:
        disk_path = os.path.join(vm_data_dir, disk_name)
        shutil.copyfile(os.path.join(settings.VM_BASE_DISKS_DIR, disk_name), disk_path)
    else:
        disk_path = ""
        for i in range(100):
            disk_path = os.path.join(vm_data_dir, "root_disk{}.qcow2".format(i))
            if not os.path.exists(disk_path):
                break
        os.system("qemu-img create -f qcow2 '{}' {}G".format(disk_path, disk_size))

    memory = str(memory)
    cpu = str(cpu)
    vm_xml_path = os.path.join(settings.BASE_DIR, 'assets/vm.xml')
    disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/disk.xml')
    iso_disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/ios_disk.xml')
    with open(disk_xml_path, 'r') as f:
        disk_root = ET.fromstring(f.read())
        disk_root.find("./source").attrib['file'] = disk_path
    if is_from_iso:
        with open(iso_disk_xml_path, 'r') as f:
            iso_disk_root = ET.fromstring(f.read())
            iso_disk_root.find("./source").attrib['file'] = os.path.join(settings.VM_ISO_DIR, iso_name)

    with open(vm_xml_path, 'r') as f:
        vm_root = ET.fromstring(f.read())
        vm_root.find("./uuid").text = str(uuid.uuid4())
        vm_root.find("./name").text = name
        vm_root.find("./memory").text = memory
        vm_root.find("./currentMemory").text = memory
        vm_root.find("./vcpu").text = cpu
        vm_root.find("./devices").append(disk_root)
        if is_from_iso:
            vm_root.find("./devices").append(iso_disk_root)
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
                disks_xml = root.findall("./devices/disk")
                disks = []
                for xml_node in disks_xml:
                    device = xml_node.attrib['device']
                    dev = xml_node.find("./target").attrib['dev']
                    file_name = xml_node.find("./source").attrib['file']
                    disks.append({"dev": dev, 'file': file_name, 'device': device})
                info = domain.info()
                item = {
                    "uuid": domain.UUIDString(),
                    "name": domain.name(),
                    "state": status_map[info[0]],
                    "mem_kb": info[1],
                    "cpu": info[3],
                    "vnc_port": port,
                    "disks": disks,
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
            is_from_iso = self.request.data.get("is_from_iso")
            iso_name = self.request.data.get("iso_name")
            disk_size = self.request.data.get("disk_size")
            if disk_size:
                try:
                    disk_size = float(disk_size)
                except:
                    raise exceptions.ValidationError('disk_size 应为数字')
                if disk_size < 0:
                    raise exceptions.ValidationError('disk_size 应为大于0的数字数字')
            res = new_define(name=name, memory=memory, cpu=cpu, disk_name=disk_name, is_from_iso=is_from_iso,
                             iso_name=iso_name, disk_size=disk_size)
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


class AttachDiskView(APIView):
    def post(self, request, *args, **kwargs):
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            uuid = self.kwargs.get("uuid")
            size = self.request.data.get("size")
            try:
                size = float(size)
            except:
                raise exceptions.ValidationError("size应为数字")
            if size < 0:
                raise exceptions.ValidationError("size应为大于0的数字")
            try:
                conn.lookupByUUIDString(uuid)
            except libvirt.libvirtError:
                raise exceptions.ValidationError("不存在此虚拟机")
        create_immediate_task(func=attach_disk, args=(uuid, size))

        return Response()
