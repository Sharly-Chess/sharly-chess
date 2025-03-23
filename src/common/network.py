"""Common network code"""
import socket
import random
from logging import Logger
import time

from common import get_logger, CONNECTION_LOCK_FILE

logger: Logger = get_logger()


def test_dns_server(ip: str) -> bool:
    """Tries to connect to a given DNS over TCP server (port 53).
    Returns True if it connected, False otherwise"""
    # https://stackoverflow.com/questions/3764291/how-can-i-see-if-theres-an-available-and-active-network-connection-in-python
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 53))
        return True
    except socket.error:
        return False


def connected() -> bool:
    """Checks if the program is connected to the internet.
    This relies on a background thread checking every few seconds, and assumes
    no other process messes with the file.
    If the public check happens between the start of the undelying check
    and its first success, this function may erreneously assume the internet
    is not available."""
    return CONNECTION_LOCK_FILE.exists()


def check_connected(sleep_time: int = 15) -> None:
    """This function is supposed to be ran in a thread or process, or it will
    hog all the caller's time.
    Tries to connect to root DNS servers, as shit has already hit the fan if
    they are not reachable"""
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
    while True:
        CONNECTION_LOCK_FILE.unlink(missing_ok=True)
        # NOTE(Amaras): if you need to prioritize servers, use the `counts`
        # keyword argument to specify integer weights for each server.
        selected_servers: str = random.sample(root_dns_servers, 2)
        if any(test_dns_server(server) for server in selected_servers):
            CONNECTION_LOCK_FILE.touch(exist_ok=True)
        time.sleep(sleep_time)
