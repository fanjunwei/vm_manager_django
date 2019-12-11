#!/usr/bin/python
# -*- coding: utf-8 -*-
import libvirt
from celery.result import AsyncResult
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from xml.etree import ElementTree as ET

from common.utils import new_mac
from host_manager.models import Host, HostSnapshot, HostNetwork
from host_manager.tasks import create_host, define_host, snapshot_create

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


class HostSerializer(serializers.ModelSerializer):
    info = serializers.SerializerMethodField()
    disks = serializers.SerializerMethodField()
    networks = serializers.SerializerMethodField()
    last_task = serializers.SerializerMethodField()
    network_names = serializers.SerializerMethodField()

    def get_network_names(self, obj):
        result = []
        for i in obj.hostnetwork_set.filter(is_delete=False):
            result.append(i.network_name)
        return result

    def get_disks(self, obj):
        result = []
        for i in obj.hoststorage_set.filter(is_delete=False):
            result.append({'id': i.id, "dev": i.dev, 'file': i.path, 'device': i.device})
        return result

    def get_last_task(self, obj):
        """The tasks current state.

        Possible values includes:

            *PENDING*

                The task is waiting for execution.

            *STARTED*

                The task has been started.

            *RETRY*

                The task is to be retried, possibly because of failure.

            *FAILURE*

                The task raised an exception, or has exceeded the retry limit.
                The :attr:`result` attribute then contains the
                exception raised by the task.

            *SUCCESS*

                The task executed successfully.  The :attr:`result` attribute
                then contains the tasks return value.
        """
        last_task_id = obj.last_task_id
        if last_task_id:
            result = AsyncResult(last_task_id)
            data = {
                "state": result.state,
                "name": obj.last_task_name
            }
            if result.state == 'SUCCESS':
                return None
            elif result.state == 'FAILURE':
                data['result'] = str(result.result)
            return data

    def get_networks(self, obj):
        result = []
        for i in obj.hostnetwork_set.filter(is_delete=False):
            result.append({"mac": i.mac, 'network_name': i.network_name, 'ip': i.ip})
        return result

    def get_info(self, obj):
        instance_uuid = obj.instance_uuid
        with libvirt.open(settings.LIBVIRT_URI) as conn:
            net_map = {}
            for net in conn.listAllNetworks():
                net_name = net.name()
                for i in net.DHCPLeases():
                    mac = i.get("mac")
                    ipaddr = i.get("ipaddr")
                    key = "{}/{}".format(net_name, mac)
                    net_map[key] = ipaddr
            try:
                domain = conn.lookupByUUIDString(instance_uuid)
            except libvirt.libvirtError:
                return {}
            vmXml = domain.XMLDesc(0)
            root = ET.fromstring(vmXml)
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
            return {
                "state": status_map[info[0]],
                "ipaddrs": ipaddrs,
            }

    def create(self, validated_data):
        instance = super(HostSerializer, self).create(validated_data)

        def callback():
            data = self.initial_data
            host_id = instance.id
            is_from_iso = data.get("is_from_iso")
            base_disk_name = data.get("base_disk_name")
            network_names = data.get("network_names")
            network_names = [x for x in network_names if x]
            iso_names = data.get("iso_names")
            init_disk_size_gb = data.get("init_disk_size_gb")
            task = create_host.delay(host_id, is_from_iso, base_disk_name, iso_names, init_disk_size_gb, network_names)
            instance.last_task_id = task.id
            instance.last_task_name = "创建虚拟机"
            instance.save()

        transaction.on_commit(callback)
        return instance

    def update(self, instance, validated_data):
        if 'network_names' in self.initial_data:
            network_names = self.initial_data.get("network_names")
            network_names = [x for x in network_names if x]
            HostNetwork.objects.filter(host_id=instance.id, is_delete=False).exclude(
                network_name__in=network_names).update(is_delete=True)
            for net_name in network_names:
                host_net = HostNetwork.objects.filter(host_id=instance.id, network_name=net_name).first()
                if not host_net:
                    host_net = HostNetwork()
                host_net.host_id = instance.id
                if not host_net.mac:
                    host_net.mac = new_mac()
                host_net.network_name = net_name
                host_net.is_delete = False
                host_net.save()
        if 'cpu_core' in validated_data or 'mem_size_kb' in validated_data or 'network_names' in self.initial_data:
            def callback():
                task = define_host.delay(instance.id)
                instance.last_task_id = task.id
                instance.last_task_name = "修改配额"
                instance.save()

            transaction.on_commit(callback)

        return super(HostSerializer, self).update(instance, validated_data)

    class Meta:
        model = Host
        exclude = ('is_delete',)
        extra_kwargs = {
            'create_time': {'read_only': True},
            'modify_time': {'read_only': True},
            'delete_time': {'read_only': True},
        }


class SnapshotSerializer(serializers.ModelSerializer):
    parent = serializers.SerializerMethodField()
    last_task = serializers.SerializerMethodField()

    class Meta:
        model = HostSnapshot
        exclude = ('is_delete',)
        extra_kwargs = {
            'create_time': {'read_only': True},
            'modify_time': {'read_only': True},
            'delete_time': {'read_only': True},
        }

    def get_last_task(self, obj):
        """The tasks current state.

        Possible values includes:

            *PENDING*

                The task is waiting for execution.

            *STARTED*

                The task has been started.

            *RETRY*

                The task is to be retried, possibly because of failure.

            *FAILURE*

                The task raised an exception, or has exceeded the retry limit.
                The :attr:`result` attribute then contains the
                exception raised by the task.

            *SUCCESS*

                The task executed successfully.  The :attr:`result` attribute
                then contains the tasks return value.
        """
        last_task_id = obj.last_task_id
        if last_task_id:
            result = AsyncResult(last_task_id)
            data = {
                "state": result.state,
                "name": obj.last_task_name
            }
            if result.state == 'SUCCESS':
                return None
            elif result.state == 'FAILURE':
                data['result'] = str(result.result)
            return data

    def get_parent(self, obj):
        if obj.parent_instance_name:
            parent = HostSnapshot.objects.filter(is_delete=False, instance_name=obj.parent_instance_name)
            if parent:
                return parent.name

    def create(self, validated_data):
        instance = super(SnapshotSerializer, self).create(validated_data)
        host_id = instance.host_id

        def callback():
            task = snapshot_create.delay(instance.id)
            host_instance = Host.objects.filter(id=host_id).first()
            host_instance.last_task_id = task.id
            host_instance.last_task_name = "创建快照"
            host_instance.save()
            instance.last_task_id = task.id
            instance.last_task_name = "创建快照"
            instance.save()

        transaction.on_commit(callback)
        return instance
