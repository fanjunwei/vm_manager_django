# coding=utf-8
from __future__ import absolute_import, unicode_literals

import datetime
import os
import shutil
from xml.etree import ElementTree as ET

import libvirt
from celery import shared_task
from django.conf import settings

from common.utils import new_mac
from host_manager.models import Host, HostStorage, HOST_STORAGE_DEVICE_DISK, HOST_STORAGE_DEVICE_CDROM, HostNetwork, \
    HostSnapshot, VncPorts


class TaskError(Exception):
    pass


@shared_task
def define_host(host_id):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")
    host_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/host.xml')
    disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/storage/disk.xml')
    cdrom_disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/storage/cdrom.xml')
    network_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/network.xml')

    with open(host_xml_path, 'r') as f:
        host_root = ET.fromstring(f.read())
    host_root.find("./uuid").text = host.instance_uuid
    host_root.find("./name").text = host.instance_name
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
        with open(network_xml_path, 'r') as f:
            network_root = ET.fromstring(f.read())
            network_root.find("./mac").attrib['address'] = network.mac
            network_root.find("./source").attrib['network'] = network.network_name
            host_root.find("./devices").append(network_root)
    host_xml = ET.tostring(host_root)
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        conn.defineXML(host_xml)
        domain = conn.lookupByUUIDString(host.instance_uuid)
        host.xml = domain.XMLDesc(0)
        host.save()


@shared_task
def create_host(host_id, is_from_iso, base_disk_name, iso_names, init_disk_size_gb):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")

    vm_data_dir = os.path.join(settings.VM_DATA_DIR, host.instance_name)
    if not os.path.exists(vm_data_dir):
        os.makedirs(vm_data_dir)
    if not is_from_iso:
        disk_path = os.path.join(vm_data_dir, base_disk_name)
        shutil.copyfile(os.path.join(settings.VM_BASE_DISKS_DIR, base_disk_name), disk_path)
    else:
        disk_path = ""
        for i in range(100):
            disk_path = os.path.join(vm_data_dir,
                                     "root_disk{}.qcow2".format(i))
            if not os.path.exists(disk_path):
                break
        os.system(
            "qemu-img create -f qcow2 '{}' {}G".format(disk_path, init_disk_size_gb))

    host_disk = HostStorage()
    host_disk.host_id = host_id
    host_disk.device = HOST_STORAGE_DEVICE_DISK
    host_disk.path = disk_path
    host_disk.dev = 'vda'
    host_disk.bus = 'virtio'
    host_disk.save()

    if is_from_iso:
        for index, item in enumerate(iso_names):
            dev = "hd{}".format(chr(0x61 + index))
            host_cdrom = HostStorage()
            host_cdrom.host_id = host_id
            host_cdrom.device = HOST_STORAGE_DEVICE_CDROM
            host_cdrom.path = os.path.join(settings.VM_ISO_DIR, item)
            host_cdrom.dev = dev
            host_cdrom.bus = 'ide'
            host_cdrom.save()

    host_net = HostNetwork()
    host_net.host_id = host_id
    host_net.mac = new_mac()
    host_net.network_name = "default"
    host_net.save()
    define_host(host_id)


@shared_task
def host_action(host_id, action):
    if action == 'sync':
        define_host(host_id)
        return
    host = Host.objects.filter(id=host_id).first()
    if not host:
        raise TaskError("not found host")
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            domain = None
        if action == 'shutdown':
            info = domain.info()
            state = info[0]
            if state == 1:
                domain.shutdown()
        elif action == 'destroy':
            info = domain.info()
            state = info[0]
            if state != 5:
                domain.destroy()
        elif action == 'delete':
            if domain:
                for snap in domain.listAllSnapshots():
                    snap.delete()
                info = domain.info()
                state = info[0]
                if state == 1:
                    domain.destroy()
                domain.undefine()
            for storage in HostStorage.objects.filter(host=host, is_delete=False, device=HOST_STORAGE_DEVICE_DISK):
                if os.path.exists(storage.path):
                    os.remove(storage.path)
            host.is_delete = True
            host.delete_time = datetime.datetime.now()
            host.save()
            VncPorts.objects.filter(value=host.vnc_port).delete()

        elif action == 'reboot':
            domain.reboot()
        elif action == 'start':
            domain.create()


@shared_task
def attach_disk(host_id, disk_size_gb):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            return
        vm_data_dir = os.path.join(settings.VM_DATA_DIR, host.instance_name)
        if not os.path.exists(vm_data_dir):
            os.makedirs(vm_data_dir)
        for i in range(100):
            disk_path = os.path.join(vm_data_dir, "disk{}.qcow2".format(i))
            if not os.path.exists(disk_path):
                break
        os.system("qemu-img create -f qcow2 '{}' {}G".format(disk_path, disk_size_gb))
        disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/storage/disk.xml')
        info = domain.info()
        state = info[0]
        devs = HostStorage.objects.filter(host=host, is_delete=False).values_list('dev', flat=True)
        devs = list(devs)
        for i in range(26):
            new_dev = "vd{}".format(chr(0x61 + i))
            if new_dev not in devs:
                break

        if state == 1:
            with open(disk_xml_path, 'r') as f:
                disk_node = ET.fromstring(f.read())

                disk_node.find("./source").attrib['file'] = disk_path
                disk_node.find("./target").attrib['dev'] = new_dev
                disk_node.find("./target").attrib['bus'] = 'virtio'
            domain.attachDevice(ET.tostring(disk_node))
    host_storage = HostStorage()
    host_storage.host_id = host_id
    host_storage.path = disk_path
    host_storage.device = HOST_STORAGE_DEVICE_DISK
    host_storage.dev = new_dev
    host_storage.bus = 'virtio'
    host_storage.save()
    define_host(host_id)


@shared_task
def detach_disk(host_id, disk_id):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")
    disk_obj = HostStorage.objects.filter(host_id=host_id, id=disk_id).first()
    if not disk_obj:
        raise TaskError("not found disk")
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            domain = None
        if domain:
            info = domain.info()
            state = info[0]
            if state == 1:
                if disk_obj.device == HOST_STORAGE_DEVICE_CDROM:
                    raise TaskError("卸载CDROM需要关闭虚拟机")
                vm_root = ET.fromstring(domain.XMLDesc(0))
                disks = vm_root.findall("./devices/disk")
                find_disk = None
                for disk in disks:
                    if disk.find('./target').get("dev") == disk_obj.dev:
                        find_disk = disk
                        break
                if find_disk:
                    domain.detachDevice(ET.tostring(find_disk))
    if disk_obj.device == HOST_STORAGE_DEVICE_DISK:
        if os.path.exists(disk_obj.path):
            os.remove(disk_obj.path)
    disk_obj.is_delete = True
    disk_obj.save()
    define_host(host_id)


@shared_task
def save_disk_to_base(host_id, disk_id, name):
    host = Host.objects.filter(id=host_id, is_delete=False).first()
    if not host:
        raise TaskError("not found host")
    disk_obj = HostStorage.objects.filter(host_id=host_id, id=disk_id).first()
    if not disk_obj:
        raise TaskError("not found disk")
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            raise TaskError("not found domain")
        name = os.path.splitext(name)[0] + ".qcow2"
        path = os.path.join(settings.VM_BASE_DISKS_DIR, name)
        if os.path.exists(path):
            raise TaskError("文件已存在")
        info = domain.info()
        state = info[0]
        if state == 1:
            is_running = True
        else:
            is_running = False
        if is_running:
            domain.suspend()
        try:
            shutil.copyfile(disk_obj.path, path)
        finally:
            if is_running:
                domain.resume()


@shared_task
def snapshot_create(snapshot_id):
    snapshot_obj = HostSnapshot.objects.filter(id=snapshot_id).first()
    if not snapshot_obj:
        raise TaskError("not found snapshot")
    host = snapshot_obj.host
    try:
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            try:
                domain = conn.lookupByUUIDString(host.instance_uuid)
            except libvirt.libvirtError:
                raise TaskError("not found domain")
            snapshot_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/snapshot/snapshot.xml')
            snapshot_disk_xml_path = os.path.join(settings.BASE_DIR, 'assets/xml_templete/snapshot/disk.xml')
            with open(snapshot_xml_path, 'r') as f:
                snapshot_root = ET.fromstring(f.read())
            info = domain.info()
            state = info[0]
            if state == 1:
                snapshot_root.find("./memory").attrib['snapshot'] = 'internal'
            else:
                snapshot_root.find("./memory").attrib['snapshot'] = 'no'
            snapshot_root.find("./name").text = snapshot_obj.instance_name
            snapshot_root.find("./description").text = snapshot_obj.desc
            for storage in HostStorage.objects.filter(host=host, device=HOST_STORAGE_DEVICE_DISK, is_delete=False):
                with open(snapshot_disk_xml_path, 'r') as f:
                    disk_root = ET.fromstring(f.read())
                    disk_root.attrib['name'] = storage.dev
                    # path_args = os.path.splitext(storage.path)
                    # new_path = "{}_snapshot_{}{}".format(path_args[0], snapshot_obj.instance_name, path_args[1])
                    # disk_root.find("./source").attrib['file'] = new_path
                    snapshot_root.find("./disks").append(disk_root)
            new_snapshot = domain.snapshotCreateXML(ET.tostring(snapshot_root))
            new_xml = new_snapshot.getXMLDesc()
            new_xml_root = ET.fromstring(new_xml)
            parent = new_xml_root.find("./parent/name")
            if parent:
                snapshot_obj.parent_instance_name = parent.text
            snapshot_obj.state = new_xml_root.find("./state").text
            snapshot_obj.save()

    except Exception:
        snapshot_obj.is_delete = True
        snapshot_obj.save()
        raise


@shared_task
def snapshot_revert(snapshot_id):
    snapshot_obj = HostSnapshot.objects.filter(id=snapshot_id).first()
    if not snapshot_obj:
        raise TaskError("not found snapshot")
    host = snapshot_obj.host
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            raise TaskError("not found domain")
        snap = domain.snapshotLookupByName(snapshot_obj.instance_name)
        domain.revertToSnapshot(snap)


@shared_task
def snapshot_delete(snapshot_id):
    snapshot_obj = HostSnapshot.objects.filter(id=snapshot_id).first()
    if not snapshot_obj:
        raise TaskError("not found snapshot")
    host = snapshot_obj.host
    with libvirt.open(settings.LIBVIRT_URI) as conn:
        try:
            domain = conn.lookupByUUIDString(host.instance_uuid)
        except libvirt.libvirtError:
            raise TaskError("not found domain")
        snap = domain.snapshotLookupByName(snapshot_obj.instance_name)
        snap.delete()
    snapshot_obj.is_delete = True
    snapshot_obj.save()
