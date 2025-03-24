"""Common network code"""
from contextlib import suppress
import socket
import random
from logging import Logger
import time
from threading import Thread

from common import get_logger

logger: Logger = get_logger()

SLEEP_TIME = 15

# We assume we're connected to the internet on startup
connected_status = [True]

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

def _test_for_internet_connection(connected_status_list: list[bool]):
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
    if any(_test_dns_server(server) for server in selected_servers):
        print("Connected")
        connected_status_list[0] = True
    else:
        print("Disconnected")
        connected_status_list[0] = False

def _check_connected(connected_status_list: list[bool]) -> None:
    """This function is supposed to be run in a thread or process, or it will
    hog all the caller's time.
    Tries to connect to root DNS servers, as shit has already hit the fan if
    they are not reachable"""

    while True:
        _test_for_internet_connection(connected_status_list)
        time.sleep(SLEEP_TIME)

# ---------------------------------------------------------------------------------
# Main thread functions
# ---------------------------------------------------------------------------------

def start_network_connection_thread():
    """Starts a thread to test for internet connectivity every few seconds"""
    # NOTE(Amaras): The entire Python program exits when only daemon threads
    # are left, and those threads will be stopped abruptly on program shutdown
    # See https://docs.python.org/3.12/library/threading.html#thread-objects
    # for more documentation
    #
    # By passing connected_status as an arg, we can share it with the main thread.

    connection_checker = Thread(target=_check_connected, args=(connected_status, ), daemon=True)
    connection_checker.start()


def can_resolve_host(host: str, timeout=2):
    """Tests if we can at least resolve an IP address
    This will will fail if no internet connection
    We can't control the timeout on this, so we use threads instead"""
    ans = {"success": False}

    def _is_host_connected(host, ans):
        with suppress(Exception):
            socket.gethostbyname(host)
            ans["success"] = True

    time_thread = Thread(target=time.sleep, args=(timeout,), daemon=True)
    host_thread = Thread(target=_is_host_connected,  kwargs={"host": host, "ans": ans}, daemon=True)

    time_thread.start()
    host_thread.start()

    while time_thread.is_alive() and host_thread.is_alive():
        pass

    return ans["success"]

def set_connected(connection_status: bool):
    """Sets the connected status from the main thread"""
    print("Setting connected from main thread", connection_status)
    connection_status[0] = connection_status

def connected(use_cached = True) -> bool:
    """Checks if the program is connected to the internet.
    This relies on a background thread checking every few seconds.
    If the public check happens between the start of the underlying check
    and its first success, this function may erroneously assume the internet
    is available."""

    if not use_cached:
        _test_for_internet_connection(connected_status)
    return connected_status[0]
