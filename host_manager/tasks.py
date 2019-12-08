from __future__ import absolute_import, unicode_literals

import os
from xml.etree import ElementTree as ET

import libvirt
from celery import shared_task
from django.conf import settings
from rest_framework import exceptions

from host_manager.models import Host, HostStorage, HOST_STORAGE_DEVICE_DISK, HOST_STORAGE_DEVICE_CDROM, HostNetwork


class TaskError(Exception):
    pass


@shared_task
def define_host(host_id):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")
    vm_data_dir = os.path.join(settings.VM_DATA_DIR, host.instance_name)
    if not os.path.exists(vm_data_dir):
        os.makedirs(vm_data_dir)

    host_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/host.xml')
    disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/storage/disk.xml')
    cdrom_disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/storage/cdrom.xml')

    with open(host_xml_path, 'r') as f:
        host_root = ET.fromstring(f.read())
    host_root.find("./uuid").text = host.instance_uuid
    host_root.find("./name").text = host.instance_name
    host_root.find("./description").text = host.desc
    host_root.find("./memory").attrib['unit'] = 'KiB'
    host_root.find("./memory").text = str(host.mem_size_kb)
    host_root.find("./currentMemory").attrib['unit'] = 'KiB'
    host_root.find("./currentMemory").text = str(host.mem_size_kb)
    host_root.find("./vcpu").text = str(host.cpu_core)
    host_root.find("./devices/graphics").attrib['port'] = str(host.vnc_port)
    for storage in HostStorage.objects.filter(host=host, is_delete=False):
        if storage.device == HOST_STORAGE_DEVICE_DISK:
            with open(disk_xml_path, 'r') as f:
                disk_root = ET.fromstring(f.read())
                disk_root.find("./source").attrib['file'] = storage.path
                disk_root.find("./target").attrib['dev'] = storage.dev
                disk_root.find("./target").attrib['bus'] = storage.bus
                host_root.find("./devices").append(disk_root)
        elif storage.device == HOST_STORAGE_DEVICE_CDROM:
            with open(cdrom_disk_xml_path, 'r') as f:
                disk_root = ET.fromstring(f.read())
                disk_root.find("./source").attrib['file'] = storage.path
                disk_root.find("./target").attrib['dev'] = storage.dev
                disk_root.find("./target").attrib['bus'] = storage.bus
                host_root.find("./devices").append(disk_root)
    for network in HostNetwork.objects.filter(host=host, is_delete=False):
        with open(disk_xml_path, 'r') as f:
            network_root = ET.fromstring(f.read())
            network_root.find("./mac").attrib['address'] = network.mac
            network_root.find("./source").attrib['network'] = network.network_name
            host_root.find("./devices").append(disk_root)
    host_xml = ET.tostring(host_root)
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        conn.defineXML(host_xml)
        domain = conn.lookupByUUIDString(host.instance_uuid)
        host.xml = domain.XMLDesc(0)
        host.save()


@shared_task
def add(x, y):
    raise exceptions.NotFound()
