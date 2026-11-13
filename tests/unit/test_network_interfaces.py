"""Filtering of the LAN interfaces offered for the server address."""

import socket
import sys
from types import SimpleNamespace

import psutil
import pytest

from common import network


def _lan_ifaces(
    monkeypatch: pytest.MonkeyPatch, platform: str, names: list[str]
) -> list[str]:
    addrs = {
        name: [SimpleNamespace(family=socket.AF_INET, address=f'192.168.1.{i + 10}')]
        for i, name in enumerate(names)
    }
    monkeypatch.setattr(sys, 'platform', platform)
    monkeypatch.setattr(psutil, 'net_if_addrs', lambda: addrs)
    monkeypatch.setattr(psutil, 'net_if_stats', dict)
    monkeypatch.setattr(network, '_win_adapter_info', dict)
    monkeypatch.setattr(network, '_linux_iface_type', lambda name: 'Ethernet')
    monkeypatch.setattr(network, '_default_route_ip', lambda: None)
    return [d['iface'] for d in network.find_lan_interfaces()]


def test_windows_keeps_external_hyper_v_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _lan_ifaces(
        monkeypatch,
        'win32',
        [
            'Ethernet',
            'vEthernet (External)',
            'vEthernet (Default Switch)',
            'vEthernet (WSL (Hyper-V firewall))',
            'vEthernet (nat)',
        ],
    ) == ['Ethernet', 'vEthernet (External)']


def test_linux_drops_veth_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _lan_ifaces(monkeypatch, 'linux', ['eth0', 'veth1a2b3c', 'docker0']) == [
        'eth0'
    ]
