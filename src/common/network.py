"""Common network code"""

from __future__ import annotations
import ipaddress
import subprocess
import socket
import sys
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    as_completed,
)
from logging import Logger
import time
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen
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

# Captive-portal probes: plaintext HTTP endpoints with predictable responses.
# Anything else (login HTML, 302 to portal, cert error after redirect, timeout)
# means we have a DHCP lease but no real internet. HTTP (not HTTPS) on purpose,
# so portals can't transparently MITM us.
# Format: (url, expected_status, expected_body_prefix or None).
_CONNECTIVITY_PROBES: list[tuple[str, int, bytes | None]] = [
    ('http://connectivitycheck.gstatic.com/generate_204', 204, None),
    ('http://detectportal.firefox.com/success.txt', 200, b'success'),
    ('http://www.msftconnecttest.com/connecttest.txt', 200, b'Microsoft Connect Test'),
]
_PROBE_TIMEOUT = 3  # seconds, per probe
_CONFIRM_DELAY = 2  # seconds, wait before re-probing after a first failure

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
    def _probe(url: str, expected_status: int, expected_body: bytes | None) -> bool:
        """Hits one captive-portal probe URL. True only if status matches and
        (when set) body starts with the expected prefix. Portal hijacks return
        login HTML / wrong status / cert errors after redirect → False."""
        try:
            req = Request(url, headers={'User-Agent': 'SharlyChess-Connectivity'})
            with urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
                if resp.status != expected_status:
                    return False
                if expected_body is None:
                    return True
                return resp.read(len(expected_body)).startswith(expected_body)
        except (URLError, OSError, ValueError):
            return False

    @classmethod
    def _run_probes(cls) -> bool:
        """Fires all probes in parallel — True if any returns OK within
        _PROBE_TIMEOUT. Different vendors so one blocked endpoint doesn't
        kill detection. Returns on first success without waiting for
        stragglers; their threads finish in the background and self-close.

        Outer timeout is essential: urlopen's timeout only bounds the socket
        connect/read — it does NOT bound socket.getaddrinfo. When offline, the
        system DNS resolver can hang ~30s before giving up. as_completed's
        timeout caps the total wall-time regardless."""
        pool = ThreadPoolExecutor(max_workers=len(_CONNECTIVITY_PROBES))
        futures = [pool.submit(cls._probe, *probe) for probe in _CONNECTIVITY_PROBES]
        ok = False
        try:
            for fut in as_completed(futures, timeout=_PROBE_TIMEOUT):
                try:
                    if fut.result(timeout=0):
                        ok = True
                        break
                except Exception:
                    continue
        except FutureTimeoutError:
            pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return ok

    @classmethod
    def _test_for_internet_connection(cls, confirm: bool = True):
        from web.server_engine import ServerEngine

        ok = cls._run_probes()
        if not ok and confirm:
            # Same-cycle confirmation: a single fail might be a Wi-Fi blip or
            # transient DNS hiccup. Wait briefly and re-probe before flipping.
            # Skipped on sync paths (use_cached=False) to keep blocking short.
            time.sleep(_CONFIRM_DELAY)
            ok = cls._run_probes()

        if ok:
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
    def connected(cls, use_cached=True) -> bool:
        """Checks if the program is connected to the internet.
        This relies on a background thread checking every few seconds,
        and so the returned value isn't 100% sure"""

        if not use_cached:
            # Skip the 2s confirm delay on the sync path — caller is blocked.
            cls._test_for_internet_connection(confirm=False)
        return cls.connected_status
