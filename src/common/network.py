"""Common network code"""

from __future__ import annotations
import ipaddress
import subprocess
import socket
import sys
import random
from logging import Logger
import time
from typing import Optional
import psutil
import pathlib
import ctypes
from ctypes import wintypes
from threading import Thread

from common.logger import get_logger

IP_V4_ADDR_REGEX: str = r'^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[0-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[0-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[0-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|0?[1-9][0-9]|0?0?[1-9])$'

LOCALHOST_IP: str = '127.0.0.1'
LOCALHOST_NAME: str = 'localhost'

logger: Logger = get_logger()

SLEEP_TIME = 15

# ---------------- Common helpers ----------------

_EXCLUDE_IFACE_NAME_SUBSTR = (
    'awdl',
    'llw',  # Apple aux Wi-Fi
    'bridge',
    'br-',  # bridges (incl. docker)
    'docker',
    'veth',
    'vmnet',
    'vbox',
    'ham',
    'hamachi',
)


def _is_private_ipv4(s: str) -> bool:
    """
    Return True if the IPv4 address is considered "usable for local networking":
      - RFC1918 private ranges (10/8, 172.16/12, 192.168/16)
      - Carrier-Grade NAT / Tailscale range (100.64/10)
    Excludes:
      - Loopback (127/8)
      - Link-local (169.254/16)
    """
    try:
        ip = ipaddress.IPv4Address(s)

        if ip.is_loopback or ip.is_link_local:
            return False

        if ip.is_private:  # RFC1918
            return True

        if ip in ipaddress.IPv4Network('100.64.0.0/10'):  # CGNAT/Tailscale
            return True

        return False
    except Exception:
        return False


def _default_route_ip() -> Optional[str]:
    """Local IP selected by OS for outbound traffic (no packets sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:
        return None


# ---------------- macOS ----------------


def _mac_hwport_map() -> dict[str, str]:
    """en0 -> 'Wi-Fi', en7 -> 'Studio Display', etc."""
    if sys.platform != 'darwin':
        return {}
    try:
        out = subprocess.check_output(
            ['networksetup', '-listallhardwareports'], text=True
        )
    except Exception:
        return {}
    mapping: dict[str, str] = {}
    current: str = 'Unknown'
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('Hardware Port:'):
            current = line.split(':', 1)[1].strip()
        elif line.startswith('Device:'):
            dev = line.split(':', 1)[1].strip()
            mapping[dev] = current
            current = 'Unknown'
    return mapping


def _mac_want_iface(name: str, hwport: Optional[str]) -> bool:
    lname = name.lower()
    if any(tag in lname for tag in _EXCLUDE_IFACE_NAME_SUBSTR):
        return False
    if hwport:
        h = hwport.lower()
        # filter Studio Display, Thunderbolt Bridge, Bluetooth PAN, iPhone USB
        if (
            'display' in h
            or 'thunderbolt bridge' in h
            or 'bluetooth' in h
            or 'iphone' in h
        ):
            return False
    return True


# ---------------- Linux ----------------


def _linux_iface_type(name: str) -> str:
    wifi_dir = pathlib.Path(f'/sys/class/net/{name}/wireless')
    if wifi_dir.exists():
        return 'Wi-Fi'
    tfile = pathlib.Path(f'/sys/class/net/{name}/type')
    try:
        code = int(tfile.read_text().strip())
        if code == 1:
            return 'Ethernet'
        if code == 772:
            return 'Wi-Fi'
    except Exception:
        pass
    if name.startswith(('lo',)):
        return 'Loopback'
    if any(x in name.lower() for x in ('tun', 'tap', 'wg')):
        return 'VPN/Tunnel'
    return 'Unknown'


# ---------------- Windows ----------------

# IfType constants (subset)
_IFTYPE_MAP = {
    6: 'Ethernet',
    71: 'Wi-Fi',  # IF_TYPE_IEEE80211
    23: 'PPP',
    24: 'Loopback',
    131: 'Tunnel',  # IF_TYPE_TUNNEL
    53: 'Slip',
    243: 'WWAN',
}


class _IP_ADAPTER_ADDRESSES(ctypes.Structure):
    # we only need a few fields; define partial with offsets
    pass


# Minimal fields (layout matches Windows; 64-bit safe for our usage)
# See IP_ADAPTER_ADDRESSES docs if you need more fields.
_PIP_ADAPTER_ADDRESSES = ctypes.POINTER(_IP_ADAPTER_ADDRESSES)
_IP_ADAPTER_ADDRESSES._fields_ = [
    ('Length', wintypes.ULONG),
    ('IfIndex', wintypes.DWORD),
    ('Next', _PIP_ADAPTER_ADDRESSES),
    ('AdapterName', ctypes.c_char_p),
    ('FirstUnicastAddress', ctypes.c_void_p),
    ('FirstAnycastAddress', ctypes.c_void_p),
    ('FirstMulticastAddress', ctypes.c_void_p),
    ('FirstDnsServerAddress', ctypes.c_void_p),
    ('DnsSuffix', wintypes.LPWSTR),
    ('Description', wintypes.LPWSTR),
    ('FriendlyName', wintypes.LPWSTR),
    ('PhysicalAddress', ctypes.c_ubyte * 8),
    ('PhysicalAddressLength', wintypes.ULONG),
    ('Flags', wintypes.ULONG),
    ('Mtu', wintypes.ULONG),
    ('IfType', wintypes.ULONG),
    ('OperStatus', wintypes.ULONG),
    # ... (we don't need the rest)
]


def _win_adapter_info() -> dict[str, tuple[str, str]]:
    """
    Return {iface_name: (friendly_name, type)} using GetAdaptersAddresses.
    iface_name matches psutil keys (e.g., 'Ethernet', 'Wi-Fi').
    """
    if sys.platform != 'win32':
        return {}

    GetAdaptersAddresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
    GetAdaptersAddresses.restype = wintypes.ULONG

    AF_UNSPEC = 0
    GAA_FLAG_SKIP_ANYCAST = 0x2
    GAA_FLAG_SKIP_MULTICAST = 0x4
    GAA_FLAG_SKIP_DNS_SERVER = 0x8

    size = wintypes.ULONG(15_000)
    buf = ctypes.create_string_buffer(size.value)
    ret = GetAdaptersAddresses(
        AF_UNSPEC,
        GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER,
        None,
        ctypes.cast(buf, _PIP_ADAPTER_ADDRESSES),
        ctypes.byref(size),
    )
    if ret == 111:  # ERROR_BUFFER_OVERFLOW
        buf = ctypes.create_string_buffer(size.value)
        ret = GetAdaptersAddresses(
            AF_UNSPEC,
            GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER,
            None,
            ctypes.cast(buf, _PIP_ADAPTER_ADDRESSES),
            ctypes.byref(size),
        )
    if ret != 0:
        return {}

    result: dict[str, tuple[str, str]] = {}
    p = ctypes.cast(buf, _PIP_ADAPTER_ADDRESSES)
    while p:
        fa = p.contents
        fname = fa.FriendlyName or ''
        iname = fa.Description or ''  # psutil often uses FriendlyName as key; fallback
        if not iname:
            iname = fname or ''
        itype = _IFTYPE_MAP.get(int(fa.IfType), 'Unknown')
        key = fname or iname
        if key:
            result[key] = (fname or iname, itype)
        p = fa.Next
    return result


# ---------------- Public API ----------------


def find_lan_interfaces() -> list[dict[str, str]]:
    """
    Returns a list of dicts:
      { "ip": "192.168.1.23", "iface": "en0", "type": "Wi-Fi", "label": "Wi-Fi" (mac) or "Ethernet 2" (Windows) }
    Primary route IP (if any) is first.
    """
    stats = psutil.net_if_stats()
    addrs = psutil.net_if_addrs()

    results: list[dict[str, str]] = []

    if sys.platform == 'darwin':
        hwmap = _mac_hwport_map()
        for iface, infos in addrs.items():
            st = stats.get(iface)
            if st and not st.isup:
                continue
            label = hwmap.get(iface)
            if not _mac_want_iface(iface, label):
                continue
            for a in infos:
                if (
                    getattr(a.family, 'name', None) == 'AF_INET'
                    or a.family == socket.AF_INET
                ):
                    ip = a.address
                    if _is_private_ipv4(ip):
                        # Special-case VPNs
                        if iface.startswith('utun'):
                            if ipaddress.ip_address(ip) in ipaddress.ip_network(
                                '100.64.0.0/10'
                            ):
                                results.append(
                                    {
                                        'ip': ip,
                                        'iface': iface,
                                        'type': 'Tailscale',
                                        'label': 'Tailscale',
                                    }
                                )
                            else:
                                results.append(
                                    {
                                        'ip': ip,
                                        'iface': iface,
                                        'type': 'VPN/Tunnel',
                                        'label': iface,
                                    }
                                )
                        else:
                            results.append(
                                {
                                    'ip': ip,
                                    'iface': iface,
                                    'type': (label or 'Unknown'),
                                    'label': (label or iface),
                                }
                            )

    elif sys.platform == 'linux':
        for iface, infos in addrs.items():
            st = stats.get(iface)
            if st and not st.isup:
                continue
            lname = iface.lower()
            if any(
                tag in lname for tag in _EXCLUDE_IFACE_NAME_SUBSTR
            ) or iface.startswith('lo'):
                continue
            itype = _linux_iface_type(iface)
            for a in infos:
                if (
                    getattr(a.family, 'name', None) == 'AF_INET'
                    or a.family == socket.AF_INET
                ):
                    ip = a.address
                    if _is_private_ipv4(ip):
                        results.append(
                            {
                                'ip': ip,
                                'iface': iface,
                                'type': itype,
                                'label': iface,
                            }
                        )

    elif sys.platform == 'win32':
        winmap = _win_adapter_info()  # {iface_name: (friendly, type)}
        for iface, infos in addrs.items():
            st = stats.get(iface)
            if st and not st.isup:
                continue
            # psutil's iface keys on Windows are typically FriendlyName already
            friendly, itype = winmap.get(iface, (iface, 'Unknown'))
            lname = iface.lower()
            if any(tag in lname for tag in _EXCLUDE_IFACE_NAME_SUBSTR):
                continue
            for a in infos:
                if (
                    getattr(a.family, 'name', None) == 'AF_INET'
                    or a.family == socket.AF_INET
                ):
                    ip = a.address
                    if _is_private_ipv4(ip):
                        results.append(
                            {
                                'ip': ip,
                                'iface': iface,
                                'type': itype,
                                'label': friendly,
                            }
                        )

    # Prefer primary route first
    primary = _default_route_ip()
    if primary:
        results.sort(key=lambda d: d['ip'] != primary)

    return results


class NetworkMonitor:
    """Class for monitoring internet connectivity"""

    # We assume we're connected to the internet on startup
    connected_status = True

    @staticmethod
    def _test_dns_server(ip: str) -> bool:
        """Tries to connect to a given DNS over TCP server (port 53).
        Returns True if it connected, False otherwise"""
        # https://stackoverflow.com/questions/3764291/how-can-i-see-if-theres-an-available-and-active-network-connection-in-python
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 53))
            return True
        except socket.error:
            return False

    @classmethod
    def _test_for_internet_connection(cls):
        from web.server_engine import ServerEngine

        # https://www.iana.org/domains/root/servers
        root_dns_servers: list[str] = [
            '198.41.0.4',
            '170.247.170.2',
            '192.33.4.12',
            '199.7.91.13',
            '192.203.230.10',
            '192.5.5.241',
            '192.112.36.4',
            '198.97.190.53',
            '192.36.148.17',
            '192.58.128.30',
            '193.0.14.129',
            '199.7.83.42',
            '202.12.27.33',
        ]

        # NOTE(Amaras): if you need to prioritize servers, use the `counts`
        # keyword argument to specify integer weights for each server.
        selected_servers: list[str] = random.sample(root_dns_servers, 2)
        if any(cls._test_dns_server(server) for server in selected_servers):
            if not cls.connected_status:
                logger.info('Internet connection established')
                if ServerEngine.app:
                    ServerEngine.app.emit('connected')
            cls.connected_status = True
        else:
            if cls.connected_status:
                logger.info('Internet connection lost')
                # NOTE(Molrn) 'disconnected' event not emitted as an event without listeners raises
            cls.connected_status = False

    # ---------------------------------------------------------------------------------
    # Main thread functions
    # ---------------------------------------------------------------------------------

    @classmethod
    def start_monitoring(cls):
        """Starts a thread to test for internet connectivity every few seconds"""
        # NOTE(Amaras): The entire Python program exits when only daemon threads
        # are left, and those threads will be stopped abruptly on program shutdown
        # See https://docs.python.org/3.13/library/threading.html#thread-objects
        # for more documentation
        #
        # By passing cls as an arg, we can share it with the main thread.

        def _check_connected(cls_) -> None:
            """This function is supposed to be run in a thread or process, or it will
            hog all the caller's time.
            Tries to connect to root DNS servers, as shit has already hit the fan if
            they are not reachable"""

            while True:
                cls_._test_for_internet_connection()
                time.sleep(SLEEP_TIME)

        connection_checker = Thread(target=_check_connected, args=(cls,), daemon=True)
        connection_checker.start()

    @classmethod
    def set_connected(cls, status: bool):
        """Sets the connected status from the main thread"""
        cls.connected_status = status

    @classmethod
    def connected(cls, use_cached=True) -> bool:
        """Checks if the program is connected to the internet.
        This relies on a background thread checking every few seconds,
        and so the returned value isn't 100% sure"""

        if not use_cached:
            cls._test_for_internet_connection()
        return cls.connected_status
