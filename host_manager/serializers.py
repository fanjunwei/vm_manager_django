#!/usr/bin/python
# -*- coding: utf-8 -*-
import libvirt
from celery.result import AsyncResult
from django.conf import settings
from django.db import transaction
from rest_framework import serializers
from xml.etree import ElementTree as ET
from host_manager.models import Host
from host_manager.tasks import create_host

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

    def get_disks(self, obj):
        result = []
        for i in obj.hoststorage_set.filter(is_delete=False):
            result.append({"dev": i.dev, 'file': i.path, 'device': i.device})
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
            iso_names = data.get("iso_names")
            init_disk_size_gb = data.get("init_disk_size_gb")
            task = create_host.delay(host_id, is_from_iso, base_disk_name, iso_names, init_disk_size_gb)
            instance.last_task_id = task.id
            instance.last_task_name = "创建虚拟机"
            instance.save()

        transaction.on_commit(callback)
        return instance

    class Meta:
        model = Host
        exclude = ('is_delete',)
        extra_kwargs = {
            'create_time': {'read_only': True},
            'modify_time': {'read_only': True},
            'delete_time': {'read_only': True},
        }
