#!/usr/bin/python
# -*- coding: utf-8 -*-
import libvirt
from django.conf import settings
from rest_framework import serializers
from xml.etree import ElementTree as ET
from host_manager.models import Host

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

    def get_disks(self, obj):
        result = []
        for i in obj.hoststorage_set.filter(is_delete=False):
            result.append({"dev": i.dev, 'file': i.path, 'device': i.device})
        return result

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

    class Meta:
        model = Host
        exclude = ('is_delete',)
        extra_kwargs = {
            'create_time': {'read_only': True},
            'modify_time': {'read_only': True},
            'delete_time': {'read_only': True},
        }
