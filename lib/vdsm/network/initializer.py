# Copyright 2017 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
from __future__ import absolute_import

from vdsm.network import dhclient_monitor
from vdsm.network import sourceroute
from vdsm.network.nm import networkmanager


def init_privileged_network_components():
    _init_sourceroute()
    dhclient_monitor.start()
    networkmanager.init()


def _init_sourceroute():
    # These proxy funcs are defined to assure correct func signature.
    def _add_sourceroute(iface, ip, mask, route):
        sourceroute.add(iface, ip, mask, route)

    def _remove_sourceroute(iface):
        sourceroute.remove(iface)

    dhclient_monitor.register_action_handler(
        action_type=dhclient_monitor.ActionType.CONFIGURE,
        action_function=_add_sourceroute,
        required_fields=(dhclient_monitor.ResponseField.IFACE,
                         dhclient_monitor.ResponseField.IPADDR,
                         dhclient_monitor.ResponseField.IPMASK,
                         dhclient_monitor.ResponseField.IPROUTE))
    dhclient_monitor.register_action_handler(
        action_type=dhclient_monitor.ActionType.REMOVE,
        action_function=_remove_sourceroute,
        required_fields=(dhclient_monitor.ResponseField.IFACE,))